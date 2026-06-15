"""Query builder for queries beyond Model.find()/where().

Used for case listing/filtering and pagination: ordering, multiple
conditions, limits, and counts - composed from a fixed set of clause
templates plus column names taken from a Model's fields() whitelist, with
all values passed to the driver as parameters. Same SQL-injection
guarantees as Model.

Example:
    # build a query on the case table where status is open, sorted by craeted_at newest-first; then fetch 20 of them; and separately, count the total
    builder = QueryBuilder(Case).where("status", "open").order_by("created_at", "DESC")
    page_of_cases = await builder.limit(20, 0).all() #produces the real sql query at this point and runs that query against the database
    total_open = await builder.count()

    "Box-filling" methods (where, where_in, order_by, limit)
    "Assemble-and-run" methods (_build, all, count)

Also includes prefetch_one()/prefetch_many() - Django select_related /
prefetch_related style helpers that batch-load related rows in a single
extra query, instead of one query per item (the N+1 problem). There is no
relationship/foreign-key registry on Model, so the caller names the FK
column and related Model explicitly each time.

Example (avoids one User query per Case):

    cases = await QueryBuilder(Case).all()
    await prefetch_one(cases, fk_field="created_by", related_model=User, attr="creator")
    cases[0].creator  # -> User instance (or None)
"""

# fetching a base class
from app.core.db.model import Model

# run a query, get all rows and run a query, get one row
from app.core.db.pool import fetchall, fetchone


class QueryBuilder:
    def __init__(self, model: type[Model]):
        # The Model subclass this builder queries - supplies __table__,
        # _columns(), and the fields() whitelist used below.
        self.model = model
        # an empty list for simply equality conditons like status="open"
        # each entry will be a (field,value) pair
        self._where: list[tuple[str, object]] = []
        # Separate from _where because "IN (...)" needs a variable number of
        # placeholders, one per value, instead of a single "= %s".
        # matching against a list of values like id IN (1,5,9)
        self._where_in: list[tuple[str, list]] = []
        self._order_by: str | None = None
        self._limit: int | None = None
        self._offset: int | None = None

    def where(self, field: str, value) -> "QueryBuilder":
        # Same column whitelist as Model.where() - reject unknown fields
        # before they could ever reach the SQL string.
        if field not in self.model.fields():
            raise ValueError(f"Unknown field '{field}' on {self.model.__name__}")
        self._where.append((field, value))
        # Returning self lets calls chain: QueryBuilder(Case).where(...).order_by(...).
        return self

    def where_in(self, field: str, values) -> "QueryBuilder":
        # Same whitelist check as where() - field must be a declared column.
        if field not in self.model.fields():
            raise ValueError(f"Unknown field '{field}' on {self.model.__name__}")
        # Used by prefetch helpers to batch-load related rows in one query
        # instead of one query per item (the N+1 problem).
        self._where_in.append((field, list(values)))
        return self

    def order_by(self, field: str, direction: str = "ASC") -> "QueryBuilder":
        if field not in self.model.fields():
            raise ValueError(f"Unknown field '{field}' on {self.model.__name__}")
        # direction is restricted to a fixed set, so it's safe to interpolate
        # directly (it can never contain attacker-controlled SQL).
        if direction.upper() not in {"ASC", "DESC"}:
            raise ValueError("direction must be 'ASC' or 'DESC'")
        self._order_by = f"{field} {direction.upper()}"
        return self

    def limit(self, limit: int, offset: int = 0) -> "QueryBuilder":
        self._limit = limit
        self._offset = offset
        return self

    # helper that turns both condition boxes (_where and _where_in) into one WHERE clause.
    def _build_where(self) -> tuple[str, list]:
        # Shared by _build() (for SELECT ... / all()) and count() - the
        # WHERE clause is identical, only the surrounding SQL differs.
        clauses: list[str] = []
        params: list = []

        # Column names go straight into the string (already whitelisted
        # in where()); the actual values go into `params`.
        for field, value in self._where:
            clauses.append(f"{field} = %s")
            params.append(value)

        for field, values in self._where_in:
            # match against nothing
            if not values:
                # "field IN ()" is invalid SQL and would mean "match
                # nothing" anyway, so short-circuit to a clause that
                # always evaluates false.
                # protects from invalid syntax and would crash
                clauses.append("1 = 0")
                continue
            # One %s placeholder per value, e.g. "id IN (%s, %s, %s)".
            placeholders = ", ".join(["%s"] * len(values))
            # make the fragment, e.g., id IN (%s, %s, %s)
            clauses.append(f"{field} IN ({placeholders})")
            # .extend adds each item of the list individually, unlike .append which would add the whole list as one item
            # three ids get queued up to fill those three placeholders
            params.extend(values)

            # clauses = ["status = %s", "id IN (%s, %s)"]
            # params = ["open", 5, 9]

        # if there were no conditions at all, there's no WHERE clause: return an empty string and an empty params list
        if not clauses:
            return "", []
        # join all the fragments with AND
        # fragments ["status = %s", "id IN (%s, %s)"] become " WHERE status = %s AND id IN (%s, %s)"
        return " WHERE " + " AND ".join(clauses), params

    #
    def _build(self) -> tuple[str, list]:
        # comma-separated column names from the whitelist ("id, status, created_at, ..")
        columns = ", ".join(self.model._columns())
        # the base query
        query = f"SELECT {columns} FROM {self.model.__table__}"

        # get the WHERE clause + its params from the helper and tack the WHERE text on
        where_sql, params = self._build_where()
        query += where_sql

        # if sorting requested, append it
        if self._order_by:
            query += f" ORDER BY {self._order_by}"

        # if limit was set, append it
        if self._limit is not None:
            # LIMIT/OFFSET are passed as parameters too, not formatted in.
            query += " LIMIT %s OFFSET %s"
            params.extend([self._limit, self._offset])

        # handback the finished query text and matching values
        return query, params

    # run the query, get all matching rows
    async def all(self) -> list[Model]:
        # assemble the full query + values
        query, params = self._build()
        # fetchall() handles acquiring/releasing the connection.
        rows = await fetchall(query, params)
        # Turn each raw row tuple back into a Model instance so that values are reattached to their names
        # case.id, case.status, case.created_at in Case object
        return [self.model._from_row(row) for row in rows]

    async def first(self) -> "Model | None":
        # Reuses all() but caps the result set to one row - cheaper than
        # fetching everything and indexing [0].
        self._limit, self._offset = 1, 0
        rows = await self.all()
        # return rows[0] if rows else NONE
        return rows[0] if rows else None

    async def count(self) -> int:
        # COUNT(*) with the same WHERE clause but no columns/order/limit -
        # this is what paginate() uses to compute total_pages without
        # fetching every matching row.
        where_sql, params = self._build_where()
        query = f"SELECT COUNT(*) FROM {self.model.__table__}" + where_sql

        # fetchone() handles acquiring/releasing the connection.
        row = await fetchone(query, params)
        # the count comes back as a one-item row like (137,0)
        return row[0]


# prefetch_one - each item has one related thing (each case --> one creator). "Many-to-one"
# prefetch_many - each item has many related thing (each case --> many notes). "One-to-many"
# solving N+1 problems while mirroring Django select_related/prefetch_related concepts


async def prefetch_one(
    items: list[Model],  # the list you already have
    *,
    fk_field: str,  # the name of the column on each item that holds the related id
    related_model: type[Model],  # the model to load from
    attr: str,  # the attribute name to attach the result under (e.g. case.creator)
    related_key: str = "id",  # which colulmn on the related model the FK points at.
) -> list[Model]:
    """select_related-style: attach one related row per item (many-to-one).

    Example: each Case has a created_by user id - load all the referenced
    Users in a single query and set case.creator on every Case, instead of
    calling User.find(case.created_by) once per case.
    """
    # Collect the distinct, non-None FK values across all items - this set
    # is the "batch" that replaces N separate per-item queries.
    fk_values = {getattr(item, fk_field) for item in items}
    fk_values.discard(None)

    if not fk_values:
        for item in items:
            setattr(item, attr, None)
        return items

    # One query: every related row whose key is in the batch.
    related_rows = (
        await QueryBuilder(related_model).where_in(related_key, fk_values).all()
    )

    # Index by the related key for O(1) lookup while attaching below.
    related_by_key = {getattr(row, related_key): row for row in related_rows}

    # Attach the matching related object (or None if the FK points nowhere).
    for item in items:
        setattr(item, attr, related_by_key.get(getattr(item, fk_field)))

    return items


async def prefetch_many(
    items: list[Model],
    *,
    local_key: str = "id",
    fk_field: str,
    related_model: type[Model],
    attr: str,
) -> list[Model]:
    """prefetch_related-style: attach a list of related rows per item (one-to-many).

    Example: each Case has many Notes (notes.case_id) - load all the Notes
    for this page of Cases in a single query and group them onto
    case.notes, instead of one Note query per Case.
    """
    # Collect the distinct, non-None local keys (e.g. case.id values).
    keys = {getattr(item, local_key) for item in items}
    keys.discard(None)

    if not keys:
        for item in items:
            setattr(item, attr, [])
        return items

    # One query: every related row whose FK points at one of these items.
    related_rows = await QueryBuilder(related_model).where_in(fk_field, keys).all()

    # Group related rows by their FK value, so each item gets its own list.
    grouped: dict[object, list[Model]] = {}
    for row in related_rows:
        grouped.setdefault(getattr(row, fk_field), []).append(row)

    # Attach each item's group (or an empty list if it has no related rows).
    for item in items:
        setattr(item, attr, grouped.get(getattr(item, local_key), []))

    return items
