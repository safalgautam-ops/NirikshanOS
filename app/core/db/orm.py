"""
It's a query builder — a tool for building and running SQL without writing SQL by hand.

Instead of writing raw SQL strings (which is clumsy and unsafe), you write Python like:

    users = (
        await db.table("users")        # pick the table
        .where("status", "active")     # add a filter
        .order_by("created_at", "DESC")# sort
        .limit(20)                     # cap how many rows
        .all()                         # actually run it and get the rows
    )

Each method returns the query object back, so you can chain calls one after another.
"""

# `from __future__ import annotations` makes all type hints be treated as plain text.
# Practical benefit: a method can say "-> Query" even though the Query class isn't
# fully defined yet at that point in the file. Avoids "name not defined" errors.
from __future__ import annotations

import copy  # used to make a deep (fully independent) copy of a query
import re  # regular expressions — used to validate/scan text like column names
from dataclasses import (  # shortcuts for making simple data-holder classes
    dataclass,
    field,
)
from typing import Any, Callable, Literal, Sequence  # type-hint helpers

# Import the low-level database functions from another file (the connection pool layer).
# These are the actual "talk to the database" functions; this file builds the SQL,
# then hands it to these to run.
from app.core.db.pool import (
    execute,  # run a query that CHANGES data (INSERT/UPDATE/DELETE), returns row counts/ids
    fetch_all,  # run a SELECT and get back ALL matching rows (a list)
    fetch_one,  # run a SELECT and get back just ONE row (or None)
)
from app.core.db.pool import (
    transaction as db_transaction,  # the "do several things as one all-or-nothing unit" helper
)

# A regex pattern meaning: "a letter or underscore, followed by any letters/numbers/underscores".
# In plain words: a valid, safe name like `email` or `user_id` — no spaces, no punctuation, no tricks.
# We use this to reject anything that could be an SQL-injection attempt in a column/table name.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# The only comparison operators we allow in a WHERE condition.
# Using a fixed allow-list means a caller can't sneak in dangerous SQL through the operator slot.
_ALLOWED_OPERATORS = {
    "=",  # equal
    "!=",  # not equal
    "<>",  # not equal (alternative spelling)
    ">",  # greater than
    ">=",  # greater than or equal
    "<",  # less than
    "<=",  # less than or equal
    "LIKE",  # text pattern match (e.g. "%bob%")
    "NOT LIKE",  # text pattern does NOT match
    "IN",  # value is in a given list
    "NOT IN",  # value is NOT in a given list
    "IS",  # used for IS NULL
    "IS NOT",  # used for IS NOT NULL
}

# Type hints describing allowed text values (these don't enforce anything at runtime,
# they just document intent and help editors catch mistakes).
Direction = Literal["asc", "desc", "ASC", "DESC"]  # sort directions we accept
JoinType = Literal["INNER", "LEFT", "RIGHT"]  # kinds of table joins we accept


class Row(dict):
    """
    A Row is just a normal dictionary with one extra convenience: dot-style access.

    Normally a dict only lets you do user["email"].
    A Row also lets you do user.email — which reads more naturally.

    Both of these work and mean the same thing:
        user["email"]
        user.email
    """

    # __getattr__ runs when you do `row.something` and `something` isn't a real attribute.
    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]  # try to read it like a dictionary key
        except KeyError as exc:
            # If the key doesn't exist, raise the "proper" error type for attribute access.
            raise AttributeError(key) from exc

    # __setattr__ runs when you do `row.something = value`.
    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value  # store it as a dictionary key instead of a normal attribute


# @dataclass auto-writes __init__/__repr__/etc. for us.
# slots=True makes instances use less memory and forbids adding undeclared fields.
@dataclass(slots=True)
class Page:
    """Holds one 'page' of results plus all the numbers needed for page-by-page navigation."""

    items: list[Row]  # the rows on this page
    page: int  # which page number this is
    per_page: int  # how many rows per page
    total: int  # total rows across ALL pages
    pages: int  # total number of pages
    has_next: bool  # is there a page after this one?
    has_prev: bool  # is there a page before this one?


@dataclass(slots=True)
class CursorPage:
    """
    An alternative paging style ('cursor'-based) — instead of page numbers,
    it remembers a 'bookmark' pointing to where the next batch should start.
    Better for very large or constantly-changing data sets.
    """

    items: list[Row]  # the rows in this batch
    per_page: int  # how many rows per batch
    has_next: bool  # is there more data after this batch?
    next_cursor: (
        dict[str, Any] | None
    )  # the bookmark for the next batch (or None if no more)


@dataclass(slots=True)
class SafeSQL:
    """A small bundle holding a piece of SQL text plus the values that go into it."""

    sql: str  # the SQL text, e.g. "createdAt > %s"
    params: list[Any] = field(default_factory=list)  # the values, e.g. [some_date]
    # NOTE: field(default_factory=list) means "default to a NEW empty list each time".
    # We can't just write `= []` because that would share one list across all instances (a classic bug).


@dataclass(slots=True)
class Condition:
    """
    One WHERE condition: a bit of SQL text plus its values.
    Example: sql = "email = %s", params = ["a@b.com"]
    """

    sql: str
    params: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class ConditionGroup:
    """
    A group of conditions joined by AND or OR.
    'items' can contain plain Conditions OR other ConditionGroups (groups inside groups),
    which is how parentheses like (A OR B) get represented.
    """

    connector: str  # "AND" or "OR"
    items: list[Condition | ConditionGroup] = field(default_factory=list)


@dataclass(slots=True)
class Join:
    """All the info needed to join (combine) another table onto the main one."""

    join_type: str  # "INNER", "LEFT", or "RIGHT"
    table: str  # the other table's name
    alias: str | None  # an optional short nickname for that table
    left: str  # left side of the ON ... = ... matching condition
    right: str  # right side of the matching condition


@dataclass(slots=True)
class Prefetch:
    """
    Settings for the 'prefetch' feature: after fetching the main rows, load their
    related rows in ONE extra query (instead of one query per row, which is slow).
    """

    name: str  # what to call the attached related data on each row
    table: str  # the related table
    local_key: str  # the column on THIS row used to match
    foreign_key: str  # the column on the OTHER table used to match
    many: bool = True  # True = a list of related rows; False = a single one
    fields: Sequence[str] | None = None  # which columns of the related table to load
    where: dict[str, Any] | None = None  # optional extra filters on the related rows
    order_by: tuple[str, str] | None = None  # optional sorting of the related rows
    limit: int = 1000  # safety cap on how many related rows to load


def raw_sql(sql: str, params: Sequence[Any] = ()) -> SafeSQL:
    """
    An explicit, deliberate wrapper for raw SQL. You must use THIS to pass raw SQL anywhere,
    which forces you to think about safety and makes it easy to spot in code reviews.

    Correct (safe) usage:
        raw_sql("expiresAt > UTC_TIMESTAMP()")     # no user input
        raw_sql("createdAt > %s", [date])          # user value passed as a parameter

    Wrong (dangerous) usage:
        raw_sql(f"email = '{user_input}'")         # pasting user input straight into SQL = injection risk
    """

    cleaned = sql.strip()  # remove leading/trailing whitespace

    if not cleaned:
        # An empty string is never valid SQL — reject it immediately.
        raise ValueError("Raw SQL cannot be empty")

    # Characters/sequences that are commonly used in SQL-injection attacks:
    # ";" ends a statement, "--" and "/* */" start comments, "\x00" is a null byte.
    dangerous_tokens = [";", "--", "/*", "*/", "\x00"]

    # If ANY of those appear, refuse — better safe than sorry.
    if any(token in cleaned for token in dangerous_tokens):
        raise ValueError("Unsafe raw SQL token detected")

    # Wrap it up as a SafeSQL bundle (params turned into a real list).
    return SafeSQL(sql=cleaned, params=list(params))


def _to_row(value: Any) -> Any:
    """
    Recursively turn plain dicts (and any nested dicts/lists) into Row objects,
    so the whole result tree gets the convenient dot-access (row.field).
    """
    if isinstance(value, Row):
        return value  # already a Row — nothing to do

    if isinstance(value, dict):
        # It's a plain dict: build a Row, converting each value too (in case of nesting).
        return Row({key: _to_row(item) for key, item in value.items()})

    if isinstance(value, list):
        # It's a list: convert each element individually.
        return [_to_row(item) for item in value]

    return value  # anything else (numbers, strings, None) is returned unchanged


def _nest_double_underscore(row: dict[str, Any]) -> dict[str, Any]:
    """
    When a query joins tables, columns get labeled like "analyzer__name" to show
    which table they came from. This function reshapes that flat dictionary into a
    nested one, so you can later write job.analyzer.name.

    Turns:   { "id": 5, "analyzer__name": "Bob", "analyzer__email": "bob@x.com" }
    Into:    { "id": 5, "analyzer": { "name": "Bob", "email": "bob@x.com" } }
    """

    output: dict[str, Any] = {}  # the new, reshaped dictionary we're building
    nested_keys: set[str] = (
        set()
    )  # remember which parent names (like "analyzer") we created

    # Go through every column name/value in the flat row.
    for key, value in row.items():
        # If the name has no "__", it's a plain top-level column — copy it straight over.
        if "__" not in key:
            output[key] = value
            continue  # move on to the next column

        # Otherwise split at the FIRST "__": "analyzer__name" -> parent="analyzer", child="name".
        # The "1" means split only once (protects names that contain more than one "__").
        parent, child = key.split("__", 1)
        nested_keys.add(parent)  # note that we made an "analyzer" group

        # If we haven't started this parent's sub-dictionary yet (or it's currently None), create it.
        if parent not in output or output[parent] is None:
            output[parent] = {}

        # Put the value inside the parent's sub-dictionary: output["analyzer"]["name"] = "Bob".
        output[parent][child] = value

    # Cleanup pass: handle the "no matching related row" case from LEFT JOINs.
    for parent in nested_keys:
        nested = output.get(parent)

        # If the whole sub-dictionary is present but EVERY value inside it is None,
        # that really means "there was no related row" — so collapse it to a single None.
        if isinstance(nested, dict) and all(value is None for value in nested.values()):
            output[parent] = None

    return output  # hand back the reshaped dictionary


def _rows(rows: list[dict[str, Any]]) -> list[Row]:
    """Convert a LIST of flat dictionaries into a list of nice nested Row objects."""
    # For each raw row: first nest the "__" columns, then wrap it as a Row.
    return [_to_row(_nest_double_underscore(row)) for row in rows]


def _row(row: dict[str, Any] | None) -> Row | None:
    """Convert a SINGLE flat dictionary (or None) into a nested Row (or None)."""
    if row is None:
        return None  # nothing found — pass the None straight through
    # Same pipeline as above, just for one row: nest the "__" columns, then wrap as a Row.
    return _to_row(_nest_double_underscore(row))


def _check_identifier(value: str) -> None:
    """Raise an error if 'value' is NOT a safe, simple name (letters/numbers/underscores)."""
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid SQL identifier: {value}")


def _quote_identifier(value: str) -> str:
    """
    Validate a name, then wrap it in backticks like `email`.
    Backticks are MySQL's way of saying "treat this exactly as a name" (so reserved
    words and such don't break). Validating first blocks injection through the name.
    """
    _check_identifier(value)  # make sure it's a safe name
    return f"`{value}`"  # wrap it: email -> `email`


def _quote_column(value: str) -> str:
    """
    Safely quote a column reference, handling the different shapes a column can take:
      - "*"            -> all columns
      - "email"        -> `email`
      - "users.email"  -> `users`.`email`   (table.column)
      - "users.*"      -> `users`.*
    """
    value = value.strip()

    if value == "*":
        return "*"  # special "all columns" symbol — leave as-is

    parts = value.split(
        "."
    )  # split on the dot, e.g. "users.email" -> ["users", "email"]

    if len(parts) == 1:
        # Just a plain column name.
        return _quote_identifier(parts[0])

    if len(parts) == 2:
        table, column = parts

        if column == "*":
            # "users.*" -> `users`.*
            return f"{_quote_identifier(table)}.*"

        # "users.email" -> `users`.`email`
        return f"{_quote_identifier(table)}.{_quote_identifier(column)}"

    # More than one dot is not a shape we support — reject it.
    raise ValueError(f"Invalid column: {value}")


def _select_expr(value: str) -> str:
    """
    Build one item of a SELECT list, supporting the "X AS alias" renaming form.
      - "email"             -> `email`
      - "email as contact"  -> `email` AS `contact`
      - "1 as found"        -> 1 AS `found`   (a literal number, allowed on the left)
    """
    raw = value.strip()
    lower = (
        raw.lower()
    )  # lowercase copy so we can find " as " regardless of capitalization

    if " as " in lower:
        # Split into the left side and the alias, on the word "as" (case-insensitive, once).
        left, alias = re.split(r"\s+as\s+", raw, flags=re.IGNORECASE, maxsplit=1)
        left = left.strip()
        alias = alias.strip()

        if left.isdigit():
            # The left side is a literal number like "1" — keep it as a number, just quote the alias.
            return f"{left} AS {_quote_identifier(alias)}"

        # Otherwise the left side is a column — quote both sides.
        return f"{_quote_column(left)} AS {_quote_identifier(alias)}"

    # No "as" — it's just a plain column reference.
    return _quote_column(raw)


def _safe_direction(direction: str) -> str:
    """Make sure a sort direction is exactly ASC or DESC (and uppercase it)."""
    upper = direction.upper()

    if upper not in {"ASC", "DESC"}:
        raise ValueError("Order direction must be ASC or DESC")

    return upper


def _safe_operator(op: str) -> str:
    """Make sure a comparison operator is one we allow (and uppercase it)."""
    upper = op.upper()

    if upper not in _ALLOWED_OPERATORS:
        raise ValueError(f"Unsupported SQL operator: {op}")

    return upper


def _result_key(column: str) -> str:
    """
    Given a column reference like "users.createdAt", return just the final piece "createdAt",
    because that's the key name the value will appear under in the result row.
    """
    return column.split(".")[-1]  # take the part after the last dot


def _make_condition(column: str, value: Any = None, op: str = "=") -> Condition:
    """
    Build one Condition (SQL text + params) from a column, a value, and an operator.
    Handles several special cases so the resulting SQL is correct and safe.
    """
    op = _safe_operator(op)  # validate/normalize the operator first

    # --- Special case: IN / NOT IN (matching against a list of values) ---
    if op in {"IN", "NOT IN"}:
        values = list(
            value or []
        )  # turn the value into a list (None becomes empty list)

        if not values and op == "IN":
            # "x IN ()" is invalid SQL and logically matches nothing.
            # "1 = 0" is always false — a safe way to say "match no rows".
            return Condition("1 = 0")

        if not values and op == "NOT IN":
            # "NOT IN ()" logically matches everything; "1 = 1" is always true.
            return Condition("1 = 1")

        # Build the right number of "%s" placeholders, one per value: e.g. "%s, %s, %s".
        placeholders = ", ".join(["%s"] * len(values))
        # e.g. `status` IN (%s, %s) with params [...]
        return Condition(f"{_quote_column(column)} {op} ({placeholders})", values)

    # --- Special case: comparing to None means NULL, not "= NULL" (which never works in SQL) ---
    if value is None and op in {"=", "IS"}:
        return Condition(f"{_quote_column(column)} IS NULL")

    if value is None and op in {"!=", "<>", "IS NOT"}:
        return Condition(f"{_quote_column(column)} IS NOT NULL")

    # --- Normal case: column OP %s, with the value supplied as a parameter ---
    return Condition(f"{_quote_column(column)} {op} %s", [value])


class FilterGroup:
    """
    A helper for building a GROUP of conditions joined by AND or OR.
    Every method returns 'self', so you can chain calls: .where(...).like(...).where_in(...)
    """

    def __init__(self, connector: Literal["AND", "OR"] = "AND"):
        # Create the underlying container, normalizing the connector to uppercase.
        self.group = ConditionGroup(connector=connector.upper())

        # Safety check: only AND/OR are valid ways to join conditions.
        if self.group.connector not in {"AND", "OR"}:
            raise ValueError("Filter group connector must be AND or OR")

    def where(self, column: str, value: Any = None, op: str = "=") -> FilterGroup:
        """Add one condition like `column = value`."""
        self.group.items.append(_make_condition(column, value, op))
        return self  # return self so calls can be chained

    def like(self, column: str, value: str) -> FilterGroup:
        """Shortcut: find rows where 'column' CONTAINS 'value' (wraps it in % signs)."""
        return self.where(column, f"%{value}%", "LIKE")

    def where_in(self, column: str, values: Sequence[Any]) -> FilterGroup:
        """Add a condition like `column IN (v1, v2, ...)`."""
        self.group.items.append(_make_condition(column, list(values), "IN"))
        return self

    def where_raw(self, condition: SafeSQL) -> FilterGroup:
        """Add a raw (custom) condition — but only a SafeSQL bundle is allowed, never a plain string."""
        if not isinstance(condition, SafeSQL):
            raise TypeError("where_raw() requires raw_sql(...)")

        self.group.items.append(Condition(condition.sql, condition.params))
        return self

    def group_by(
        self,
        connector: Literal["AND", "OR"],
        callback: Callable[[FilterGroup], None],
    ) -> FilterGroup:
        """
        Create a NESTED group (the parentheses part of SQL), e.g. (A OR B).
        'callback' is a function you provide that fills the inner group.
        """
        child = FilterGroup(connector)  # make a fresh empty sub-group
        callback(child)  # let your function add conditions into it

        if child.group.items:
            # Only attach the sub-group if it actually got some conditions
            # (don't add empty parentheses).
            self.group.items.append(child.group)

        return self


class Query:
    """
    The main builder. You create one per table, chain methods to describe what you want,
    then call a terminal method (.all(), .first(), .insert(), etc.) to actually run it.
    """

    def __init__(self, table: str, alias: str | None = None):
        _check_identifier(table)  # make sure the table name is safe

        if alias is not None:
            _check_identifier(alias)  # and the alias too, if given

        self.table = table  # the table this query is about
        self.alias = alias  # optional short nickname for the table

        # These lists/flags accumulate the pieces of the query as you chain methods.
        self._selects: list[str] = []  # which columns to SELECT
        self._conditions: list[Condition | ConditionGroup] = []  # the WHERE conditions
        self._joins: list[Join] = []  # tables to JOIN in
        self._orders: list[tuple[str, str]] = []  # ORDER BY (column, direction) pairs
        self._groups: list[str] = []  # GROUP BY columns

        self._limit: int | None = None  # LIMIT (max rows), None = not set
        self._offset: int | None = None  # OFFSET (skip first N rows), None = not set
        self._distinct = False  # whether to add DISTINCT
        self._for_update = False  # whether to add FOR UPDATE (row locking)

        self._prefetches: list[Prefetch] = []  # related-data loading instructions

    def clone(self) -> Query:
        """Make a fully independent copy of this query (so modifying the copy can't affect the original)."""
        return copy.deepcopy(self)

    @property
    def table_ref(self) -> str:
        """The table part for the FROM clause, e.g. `users` or `users` AS `u`."""
        if self.alias:
            return f"{_quote_identifier(self.table)} AS {_quote_identifier(self.alias)}"

        return _quote_identifier(self.table)

    @property
    def main_ref(self) -> str:
        """The name to use when referring to the main table elsewhere (alias if set, else table name)."""
        return self.alias or self.table

    def select(self, *columns: str) -> Query:
        """Choose which columns to return. Accepts any number of column names."""
        self._selects.extend(columns)  # add them to the running list
        return self

    def distinct(self) -> Query:
        """Ask for DISTINCT (remove duplicate rows)."""
        self._distinct = True
        return self

    def where(self, column: str, value: Any = None, op: str = "=") -> Query:
        """Add a WHERE condition like `column = value`."""
        self._conditions.append(_make_condition(column, value, op))
        return self

    def where_dict(self, values: dict[str, Any]) -> Query:
        """Convenience: add several equality conditions at once from a dictionary."""
        for column, value in values.items():
            self.where(column, value)  # one `column = value` per entry

        return self

    def or_where(self, conditions: Sequence[tuple]) -> Query:
        """
        Add a group of OR conditions from a list of tuples.
        Each tuple is either (column, value) or (column, op, value).
        Produces: (cond1 OR cond2 OR ...)
        """
        group = FilterGroup("OR")  # build an OR group

        for item in conditions:
            if len(item) == 2:
                # (column, value) — operator defaults to "="
                column, value = item
                group.where(column, value)
            elif len(item) == 3:
                # (column, op, value) — explicit operator
                column, op, value = item
                group.where(column, value, op)
            else:
                raise ValueError(
                    "OR condition must be (column, value) or (column, op, value)"
                )

        if group.group.items:
            self._conditions.append(group.group)  # attach the OR group (if non-empty)

        return self

    def where_group(
        self,
        callback: Callable[[FilterGroup], None],
        *,
        connector: Literal["AND", "OR"] = "AND",
    ) -> Query:
        """
        Add a nested condition group built by your callback function.
        Lets you express things like: ... AND (A OR B).
        """
        group = FilterGroup(connector)  # fresh group with the chosen connector
        callback(group)  # your function fills it with conditions

        if group.group.items:
            self._conditions.append(group.group)  # attach it (if non-empty)

        return self

    def where_in(self, column: str, values: Sequence[Any]) -> Query:
        """Add a `column IN (...)` condition."""
        self._conditions.append(_make_condition(column, list(values), "IN"))
        return self

    def where_not_in(self, column: str, values: Sequence[Any]) -> Query:
        """Add a `column NOT IN (...)` condition."""
        self._conditions.append(_make_condition(column, list(values), "NOT IN"))
        return self

    def where_between(self, column: str, start: Any, end: Any) -> Query:
        """Add a `column BETWEEN start AND end` condition (inclusive range)."""
        self._conditions.append(
            Condition(
                f"{_quote_column(column)} BETWEEN %s AND %s",
                [start, end],  # the two boundary values, passed safely as parameters
            )
        )
        return self

    def like(self, column: str, value: str) -> Query:
        """Find rows where 'column' CONTAINS 'value' (e.g. %bob%)."""
        return self.where(column, f"%{value}%", "LIKE")

    def startswith(self, column: str, value: str) -> Query:
        """Find rows where 'column' STARTS WITH 'value' (e.g. bob%)."""
        return self.where(column, f"{value}%", "LIKE")

    def endswith(self, column: str, value: str) -> Query:
        """Find rows where 'column' ENDS WITH 'value' (e.g. %bob)."""
        return self.where(column, f"%{value}", "LIKE")

    def search(self, columns: Sequence[str], term: str) -> Query:
        """
        Search for 'term' across SEVERAL columns at once, matching if ANY of them contain it.
        Produces: (col1 LIKE %term% OR col2 LIKE %term% OR ...)
        """
        if not columns:
            return self  # nothing to search in — do nothing

        return self.where_group(
            # For each column, add a LIKE condition; connector="OR" joins them with OR.
            lambda group: [group.like(column, term) for column in columns],
            connector="OR",
        )

    def where_raw(self, condition: SafeSQL) -> Query:
        """Add a raw custom condition — only a SafeSQL bundle is allowed."""
        if not isinstance(condition, SafeSQL):
            raise TypeError("where_raw() requires raw_sql(...)")

        self._conditions.append(Condition(condition.sql, condition.params))
        return self

    def join(
        self,
        table: str,
        left: str,
        right: str,
        *,
        join_type: JoinType = "INNER",
        alias: str | None = None,
    ) -> Query:
        """
        Combine another table into the query.
        'left' and 'right' are the two columns that must match (the ON ... = ... part).
        """
        join_type = join_type.upper()  # normalize to uppercase

        if join_type not in {"INNER", "LEFT", "RIGHT"}:
            raise ValueError("join_type must be INNER, LEFT, or RIGHT")

        _check_identifier(table)  # safety-check the table name

        if alias is not None:
            _check_identifier(alias)  # and the alias, if any

        # Record this join; the SQL text gets built later in _build_joins().
        self._joins.append(
            Join(
                join_type=join_type,
                table=table,
                alias=alias,
                left=left,
                right=right,
            )
        )

        return self

    def left_join(
        self,
        table: str,
        left: str,
        right: str,
        *,
        alias: str | None = None,
    ) -> Query:
        """Shortcut for a LEFT JOIN (keeps main rows even when there's no match)."""
        return self.join(table, left, right, join_type="LEFT", alias=alias)

    def select_related(
        self,
        name: str,
        *,
        table: str,
        local_key: str,
        foreign_key: str = "id",
        fields: Sequence[str],
        alias: str | None = None,
    ) -> Query:
        """
        Load a related row by JOINING it in and selecting its columns with a 'name__' prefix
        (so _nest_double_underscore can later turn them into row.name.field).
        Good for one-to-one / many-to-one relationships fetched in a single query.
        """
        alias = alias or name  # use the relation name as the table alias by default

        # Join the related table: main.local_key = alias.foreign_key
        self.left_join(
            table,
            f"{self.main_ref}.{local_key}",
            f"{alias}.{foreign_key}",
            alias=alias,
        )

        # Select each requested field, aliased as name__field (e.g. analyzer__email).
        for field in fields:
            self.select(f"{alias}.{field} as {name}__{field}")

        return self

    def prefetch_related(
        self,
        name: str,
        *,
        table: str,
        local_key: str,
        foreign_key: str,
        many: bool = True,
        fields: Sequence[str] | None = None,
        where: dict[str, Any] | None = None,
        order_by: tuple[str, str] | None = None,
        limit: int = 1000,
    ) -> Query:
        """
        Schedule loading of related rows in a SEPARATE follow-up query (run after the main one).
        Avoids the slow "one query per row" problem for one-to-many relationships.
        """
        final_fields = list(fields or ["*"])  # default to all columns if none specified

        # We must include the foreign_key in the loaded columns, otherwise we can't match
        # the related rows back to their parents. Add it if it's missing.
        if fields and foreign_key not in final_fields:
            final_fields.append(foreign_key)

        # Record the instruction; it's actually carried out later in _apply_prefetches().
        self._prefetches.append(
            Prefetch(
                name=name,
                table=table,
                local_key=local_key,
                foreign_key=foreign_key,
                many=many,
                fields=final_fields,
                where=where,
                order_by=order_by,
                limit=limit,
            )
        )

        return self

    def order_by(self, column: str, direction: Direction = "ASC") -> Query:
        """Add a sort instruction: by 'column', ascending or descending."""
        self._orders.append((column, _safe_direction(direction)))
        return self

    def group_by(self, *columns: str) -> Query:
        """Add GROUP BY columns (used with aggregate functions like COUNT)."""
        self._groups.extend(columns)
        return self

    def limit(self, value: int) -> Query:
        """Set the maximum number of rows to return."""
        if value <= 0:
            raise ValueError("limit must be greater than 0")

        self._limit = value
        return self

    def offset(self, value: int) -> Query:
        """Set how many rows to skip from the start (used for paging)."""
        if value < 0:
            raise ValueError("offset cannot be negative")

        self._offset = value
        return self

    def for_update(self) -> Query:
        """Add FOR UPDATE — locks the selected rows until the transaction finishes."""
        self._for_update = True
        return self

    def _build_condition_item(
        self, item: Condition | ConditionGroup
    ) -> tuple[str, list[Any]]:
        """
        Turn one condition OR one nested group into SQL text + params.
        This calls itself for nested groups (recursion), which is how it handles
        groups inside groups inside groups, to any depth.
        Returns: (sql_text, list_of_params)
        """
        if isinstance(item, Condition):
            # Base case: a single condition already has its sql + params.
            return item.sql, list(item.params)

        # Otherwise it's a group: build each child, then join them with the group's connector.
        parts: list[str] = []  # the child SQL snippets
        params: list[Any] = []  # all the child params, collected together

        for child in item.items:
            sql, child_params = self._build_condition_item(
                child
            )  # recurse into the child

            if sql:  # skip empty snippets
                parts.append(sql)
                params.extend(child_params)

        if not parts:
            return "", []  # the group ended up empty — produce nothing

        # Join children with " AND " or " OR " and wrap in parentheses, e.g. "(A OR B)".
        joined = f" {item.connector} ".join(parts)
        return f"({joined})", params

    def _build_where(self) -> tuple[str, list[Any]]:
        """Build the full WHERE clause text + params from all collected conditions."""
        if not self._conditions:
            return "", []  # no conditions -> no WHERE clause at all

        parts: list[str] = []
        params: list[Any] = []

        for condition in self._conditions:
            sql, condition_params = self._build_condition_item(condition)

            if sql:
                parts.append(sql)
                params.extend(condition_params)

        if not parts:
            return "", []  # everything was empty

        # Top-level conditions are always joined with AND. Prepend the " WHERE " keyword.
        return " WHERE " + " AND ".join(parts), params

    def _build_joins(self) -> str:
        """Build the JOIN portion of the SQL from all collected joins."""
        if not self._joins:
            return ""  # nothing to join

        parts = []

        for join in self._joins:
            table = _quote_identifier(join.table)  # safely quote the joined table name

            if join.alias:
                table = f"{table} AS {_quote_identifier(join.alias)}"  # add its alias

            # e.g. " LEFT JOIN `analyzer` AS `a` ON `j`.`analyzerId` = `a`.`id`"
            parts.append(
                f" {join.join_type} JOIN {table}"
                f" ON {_quote_column(join.left)} = {_quote_column(join.right)}"
            )

        return "".join(parts)  # stick them all together

    def _build_select_sql(
        self,
        *,
        count: bool = False,
        count_column: str = "*",
        distinct_count: bool = False,
    ) -> tuple[str, list[Any]]:
        """
        Build a complete SELECT statement (text + params).
        Can also build a COUNT(...) version when 'count' is True (used by .count()/.paginate()).
        Returns: (sql_text, params)
        """
        # --- Decide what goes right after SELECT ---
        if count:
            if distinct_count:
                # Count how many DISTINCT values of the column there are.
                select_part = f"COUNT(DISTINCT {_quote_column(count_column)}) AS total"
            else:
                # Plain count of rows.
                select_part = f"COUNT({_quote_column(count_column)}) AS total"
        else:
            # Normal select: use the chosen columns, or default to "main_table.*" (all columns).
            selected = self._selects or [f"{self.main_ref}.*"]
            select_part = ", ".join(_select_expr(column) for column in selected)

        # Add "DISTINCT " only for normal (non-count) selects when requested.
        distinct = "DISTINCT " if self._distinct and not count else ""

        # Start assembling: SELECT ... FROM table ...
        sql = f"SELECT {distinct}{select_part} FROM {self.table_ref}"
        sql += self._build_joins()  # add any JOINs

        # Add the WHERE clause (and collect its params).
        where_sql, params = self._build_where()
        sql += where_sql

        # GROUP BY only makes sense on a normal select, and only if groups were set.
        if self._groups and not count:
            sql += " GROUP BY " + ", ".join(
                _quote_column(column) for column in self._groups
            )

        # ORDER BY only on a normal select, if any sorts were set.
        if self._orders and not count:
            order_sql = ", ".join(
                f"{_quote_column(column)} {direction}"
                for column, direction in self._orders
            )
            sql += " ORDER BY " + order_sql

        # LIMIT (max rows) — pass the number as a parameter, not inline text.
        if self._limit is not None and not count:
            sql += " LIMIT %s"
            params.append(self._limit)

        # OFFSET (skip rows) — also passed as a parameter.
        if self._offset is not None and not count:
            sql += " OFFSET %s"
            params.append(self._offset)

        # FOR UPDATE (row locking) on a normal select if requested.
        if self._for_update and not count:
            sql += " FOR UPDATE"

        return sql, params

    async def all(self, *, allow_full_table: bool = False) -> list[Row]:
        """
        Run the query and return ALL matching rows.
        Safety guard: refuses to run without a limit unless you explicitly allow a full-table read.
        """
        if self._limit is None and not allow_full_table:
            # Prevent accidentally loading an entire huge table by mistake.
            raise ValueError(
                "Use .paginate(), .cursor_paginate(), .limit(), "
                "or all(allow_full_table=True)"
            )

        sql, params = self._build_select_sql()  # build the SQL
        result = _rows(
            await fetch_all(sql, params)
        )  # run it and turn results into Rows

        if self._prefetches:
            # If related data was requested, load and attach it now.
            await self._apply_prefetches(result)

        return result

    async def first(self) -> Row | None:
        """Run the query but return only the FIRST matching row (or None if none)."""
        query = self.clone()  # work on a copy so we don't change the original's limit
        query.limit(1)  # we only need one row

        sql, params = query._build_select_sql()
        return _row(await fetch_one(sql, params))  # fetch one, wrap as Row (or None)

    async def count(self, column: str = "*") -> int:
        """Return how many rows match (ignoring limit/offset/ordering)."""
        query = self.clone()
        query._limit = None  # counting shouldn't be limited
        query._offset = None  # or offset
        query._orders = []  # or ordered (pointless for a count)

        sql, params = query._build_select_sql(count=True, count_column=column)
        row = await fetch_one(sql, params)

        # The count comes back under the "total" alias; return 0 if somehow nothing came back.
        return int(row["total"]) if row else 0

    async def count_distinct(self, column: str) -> int:
        """Return how many DISTINCT values of 'column' match."""
        query = self.clone()
        query._limit = None
        query._offset = None
        query._orders = []

        sql, params = query._build_select_sql(
            count=True,
            count_column=column,
            distinct_count=True,
        )

        row = await fetch_one(sql, params)

        return int(row["total"]) if row else 0

    async def exists(self) -> bool:
        """Return True if at least one matching row exists (efficiently — selects just '1')."""
        query = self.clone()
        query._selects = ["1 as found"]  # we don't need real columns, just a marker
        query.limit(1)  # one row is enough to prove existence

        sql, params = query._build_select_sql()
        row = await fetch_one(sql, params)

        return row is not None  # got a row -> it exists

    async def paginate(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        max_per_page: int = 100,
        count_distinct: str | None = None,
    ) -> Page:
        """
        Classic page-number pagination: returns one page of rows plus navigation info.
        """
        page = max(page, 1)  # page can't be less than 1
        per_page = max(
            1, min(per_page, max_per_page)
        )  # clamp per_page between 1 and max

        # Get the total number of matching rows (used to compute number of pages).
        if count_distinct:
            total = await self.count_distinct(count_distinct)
        else:
            total = await self.count()

        # Build a copy that fetches just this page's slice of rows.
        query = self.clone()
        query.limit(per_page)
        query.offset((page - 1) * per_page)  # skip the rows belonging to earlier pages

        items = await query.all()  # fetch this page's rows

        # Total pages = ceiling(total / per_page). The "+ per_page - 1" trick rounds up.
        pages = (total + per_page - 1) // per_page if total else 0

        return Page(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            pages=pages,
            has_next=page < pages,  # there's a next page if we're not on the last one
            has_prev=page > 1,  # there's a previous page if we're past page 1
        )

    async def cursor_paginate(
        self,
        *,
        cursor_column: str = "createdAt",
        cursor_value: Any | None = None,
        cursor_id_column: str | None = "id",
        cursor_id_value: Any | None = None,
        direction: Direction = "DESC",
        per_page: int = 20,
        max_per_page: int = 100,
    ) -> CursorPage:
        """
        'Cursor' pagination: instead of page numbers, you pass a bookmark (the cursor)
        pointing just past the last row you saw, and get the next batch after it.
        The id column is used as a tie-breaker when two rows share the same cursor value.
        """
        per_page = max(1, min(per_page, max_per_page))  # clamp batch size
        direction = _safe_direction(direction)  # validate ASC/DESC

        query = self.clone()
        query._orders = []  # we'll set our own ordering below

        # If specific columns were selected, make sure the cursor columns are included,
        # otherwise we won't be able to read the values needed for the next cursor.
        if query._selects:
            needed_columns = [cursor_column]

            if cursor_id_column:
                needed_columns.append(cursor_id_column)

            # Figure out which result-key names are already selected (handling "x as y" and "t.c").
            selected_names = {
                item.split(" as ")[-1].split(".")[-1].strip("` ")
                for item in query._selects
            }

            # Add any missing needed columns.
            for column in needed_columns:
                key = _result_key(column)

                if key not in selected_names:
                    query.select(column)

        # If we were given a cursor (a starting point), add the "after this point" condition.
        if cursor_value is not None:
            # Going DESC means "older/smaller next", so we want values LESS than the cursor.
            compare = "<" if direction == "DESC" else ">"

            if cursor_id_column and cursor_id_value is not None:
                # Tie-breaker logic so rows with equal cursor_value don't get skipped/repeated.
                id_compare = "<" if direction == "DESC" else ">"

                # Condition: cursor_column past the value, OR (equal value AND id past the id).
                query.where_group(
                    lambda group: group.where(
                        cursor_column, cursor_value, compare
                    ).group_by(
                        "AND",
                        lambda inner: inner.where(cursor_column, cursor_value).where(
                            cursor_id_column, cursor_id_value, id_compare
                        ),
                    ),
                    connector="OR",
                )
            else:
                # No tie-breaker — simple comparison on the cursor column.
                query.where(cursor_column, cursor_value, compare)

        # Order by the cursor column (and id as tie-breaker) so paging is consistent.
        query.order_by(cursor_column, direction)

        if cursor_id_column:
            query.order_by(cursor_id_column, direction)

        # Fetch ONE extra row beyond per_page — its presence tells us if there's a next batch.
        query.limit(per_page + 1)

        rows = await query.all()
        has_next = (
            len(rows) > per_page
        )  # got the extra row? then there's more after this
        items = rows[:per_page]  # but only hand back per_page rows

        next_cursor = None

        # Build the bookmark for the next batch, taken from the last row we're returning.
        if has_next and items:
            last = items[-1]
            cursor_key = _result_key(cursor_column)

            next_cursor = {
                "cursor_value": last.get(cursor_key),  # value to start after next time
            }

            if cursor_id_column:
                id_key = _result_key(cursor_id_column)
                next_cursor["cursor_id_value"] = last.get(id_key)  # tie-breaker id too

        return CursorPage(
            items=items,
            per_page=per_page,
            has_next=has_next,
            next_cursor=next_cursor,
        )

    async def insert(self, data: dict[str, Any]) -> int | None:
        """Insert one new row from a dict of {column: value}. Returns the new row's id."""
        if not data:
            raise ValueError("insert data cannot be empty")

        columns = list(data.keys())  # the column names
        values = list(data.values())  # the matching values

        # Build "`col1`, `col2`" and "%s, %s" of the right length.
        column_sql = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))

        # e.g. INSERT INTO `users` (`name`, `email`) VALUES (%s, %s)
        sql = f"INSERT INTO {_quote_identifier(self.table)} ({column_sql}) VALUES ({placeholders})"
        result = await execute(sql, values)  # run it, passing the values safely

        return result.lastrowid  # the auto-generated id of the inserted row

    async def create(self, data: dict[str, Any]) -> int | None:
        """Friendly alias for insert()."""
        return await self.insert(data)

    async def bulk_insert(self, rows: list[dict[str, Any]]) -> int:
        """Insert MANY rows in a single statement. Returns how many rows were inserted."""
        if not rows:
            return 0  # nothing to do

        columns = list(rows[0].keys())  # use the first row's columns as the template

        # Every row must have exactly the same columns, or the SQL would be inconsistent.
        for row in rows:
            if list(row.keys()) != columns:
                raise ValueError("All bulk_insert rows must have the same columns")

        column_sql = ", ".join(_quote_identifier(column) for column in columns)
        row_placeholder = (
            "(" + ", ".join(["%s"] * len(columns)) + ")"
        )  # "(%s, %s, ...)"
        placeholders = ", ".join([row_placeholder] * len(rows))  # one group per row

        # Flatten every row's values into a single list, in order.
        values: list[Any] = []

        for row in rows:
            values.extend(row.values())

        # e.g. INSERT INTO `t` (`a`, `b`) VALUES (%s, %s), (%s, %s)
        sql = f"INSERT INTO {_quote_identifier(self.table)} ({column_sql}) VALUES {placeholders}"
        result = await execute(sql, values)

        return result.rowcount  # number of rows affected (inserted)

    async def create_many(self, rows: list[dict[str, Any]]) -> int:
        """Friendly alias for bulk_insert()."""
        return await self.bulk_insert(rows)

    async def update(self, data: dict[str, Any]) -> int:
        """Update matching rows with new values. Returns how many rows changed."""
        if not data:
            raise ValueError("update data cannot be empty")

        if not self._conditions:
            # Safety: an UPDATE with no WHERE would change EVERY row — refuse it.
            raise ValueError("Refusing UPDATE without WHERE condition")

        # Build "`col1` = %s, `col2` = %s".
        assignments = ", ".join(
            f"{_quote_identifier(column)} = %s" for column in data.keys()
        )

        where_sql, where_params = self._build_where()  # build the WHERE part

        # e.g. UPDATE `users` SET `name` = %s WHERE `id` = %s
        sql = f"UPDATE {_quote_identifier(self.table)} SET {assignments}{where_sql}"
        # The params are: first the new values, then the WHERE values, in that order.
        params = list(data.values()) + where_params

        result = await execute(sql, params)
        return result.rowcount

    async def patch(self, data: dict[str, Any]) -> int:
        """Friendly alias for update()."""
        return await self.update(data)

    async def bulk_update(
        self,
        rows: list[dict[str, Any]],
        *,
        key: str = "id",
        update_columns: Sequence[str],
    ) -> int:
        """
        Update many rows with DIFFERENT values each, in a single statement,
        using a SQL CASE expression keyed on each row's 'key' (e.g. its id).
        """
        if not rows:
            return 0

        if not update_columns:
            raise ValueError("update_columns cannot be empty")

        _check_identifier(key)  # the key column name must be safe

        # Validate that every row has the key and every column we intend to update.
        for row in rows:
            if key not in row:
                raise ValueError(f"Missing bulk update key: {key}")

            for column in update_columns:
                if column not in row:
                    raise ValueError(f"Missing bulk update column: {column}")

        key_values = [
            row[key] for row in rows
        ]  # the key values of all rows (for the WHERE IN)

        set_parts = []  # one "col = CASE ... END" piece per column
        params: list[
            Any
        ] = []  # collected parameters, in the exact order they appear in SQL

        for column in update_columns:
            _check_identifier(column)  # each updated column name must be safe

            # Start a CASE that switches on the key column.
            case_sql = f"{_quote_identifier(column)} = CASE {_quote_identifier(key)}"

            # For each row: "WHEN <key> THEN <new value>".
            for row in rows:
                case_sql += " WHEN %s THEN %s"
                params.extend([row[key], row[column]])

            # ELSE keep the existing value (so rows not listed are unaffected for this column).
            case_sql += f" ELSE {_quote_identifier(column)} END"
            set_parts.append(case_sql)

        # WHERE key IN (%s, %s, ...) — limit the update to just the listed rows.
        placeholders = ", ".join(["%s"] * len(key_values))
        params.extend(key_values)  # these go last, matching the IN placeholders

        sql = (
            f"UPDATE {_quote_identifier(self.table)} "
            f"SET {', '.join(set_parts)} "
            f"WHERE {_quote_identifier(key)} IN ({placeholders})"
        )

        result = await execute(sql, params)
        return result.rowcount

    async def delete(self) -> int:
        """Delete matching rows. Returns how many were deleted."""
        if not self._conditions:
            # Safety: a DELETE with no WHERE would wipe the whole table — refuse it.
            raise ValueError("Refusing DELETE without WHERE condition")

        where_sql, params = self._build_where()

        # e.g. DELETE FROM `users` WHERE `id` = %s
        sql = f"DELETE FROM {_quote_identifier(self.table)}{where_sql}"
        result = await execute(sql, params)

        return result.rowcount

    async def bulk_delete(self, column: str, values: Sequence[Any]) -> int:
        """Delete all rows where 'column' is one of the given values."""
        # Adds a `column IN (...)` filter, then runs delete().
        return await self.where_in(column, values).delete()

    async def upsert(
        self,
        data: dict[str, Any],
        *,
        update_columns: Sequence[str],
    ) -> int | None:
        """
        Insert a row, but if it would collide with an existing one (duplicate key),
        UPDATE the listed columns instead. ("insert-or-update" = upsert.)
        """
        if not data:
            raise ValueError("upsert data cannot be empty")

        if not update_columns:
            raise ValueError("update_columns cannot be empty")

        columns = list(data.keys())
        values = list(data.values())

        column_sql = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))

        # The "on conflict, update these" part: `col` = VALUES(`col`) means
        # "set it to the value we tried to insert".
        update_sql = ", ".join(
            f"{_quote_identifier(column)} = VALUES({_quote_identifier(column)})"
            for column in update_columns
        )

        # e.g. INSERT INTO `t` (...) VALUES (...) ON DUPLICATE KEY UPDATE `x` = VALUES(`x`)
        sql = (
            f"INSERT INTO {_quote_identifier(self.table)} ({column_sql}) "
            f"VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_sql}"
        )

        result = await execute(sql, values)
        return result.lastrowid

    async def _apply_prefetches(self, rows: list[Row]) -> None:
        """
        For each scheduled prefetch, load the related rows in one query and attach them
        onto the parent rows under the prefetch's 'name'.
        """
        if not rows:
            return  # no parent rows -> nothing to attach to

        for prefetch in self._prefetches:
            # Collect the parent rows' local_key values (skipping any that are None).
            parent_ids = [
                row.get(prefetch.local_key)
                for row in rows
                if row.get(prefetch.local_key) is not None
            ]

            if not parent_ids:
                # No usable keys -> attach an empty list/None to every parent and move on.
                for row in rows:
                    row[prefetch.name] = [] if prefetch.many else None
                continue

            # Build a query against the related table.
            child_query = Query(prefetch.table)

            if prefetch.fields:
                child_query.select(*prefetch.fields)

            # Only load children whose foreign_key is one of our parent ids.
            child_query.where_in(prefetch.foreign_key, parent_ids)

            if prefetch.where:
                child_query.where_dict(prefetch.where)  # extra filters, if any

            if prefetch.order_by:
                child_query.order_by(prefetch.order_by[0], prefetch.order_by[1])

            child_query.limit(prefetch.limit)  # safety cap

            children = await child_query.all()  # fetch all related rows at once

            # Group the children by their foreign_key, so we can quickly find each parent's matches.
            grouped: dict[Any, list[Row]] = {}

            for child in children:
                key = child.get(prefetch.foreign_key)
                grouped.setdefault(key, []).append(
                    child
                )  # start a list if needed, then append

            # Attach the matching children onto each parent row.
            for row in rows:
                local_value = row.get(prefetch.local_key)

                if prefetch.many:
                    # one-to-many: attach the whole list (empty list if none matched)
                    row[prefetch.name] = grouped.get(local_value, [])
                else:
                    # one-to-one: attach just the first match (or None if none matched)
                    matches = grouped.get(local_value, [])
                    row[prefetch.name] = matches[0] if matches else None


class Database:
    """The top-level entry point. You start every query from here, e.g. db.table('users')."""

    def table(self, table: str, alias: str | None = None) -> Query:
        """Begin a new query against the given table."""
        return Query(table, alias)

    async def raw(self, statement: SafeSQL) -> list[Row]:
        """Run a raw SELECT (wrapped in SafeSQL) and return all rows as Rows."""
        if not isinstance(statement, SafeSQL):
            raise TypeError("raw() requires raw_sql(...)")

        return _rows(await fetch_all(statement.sql, statement.params))

    async def raw_one(self, statement: SafeSQL) -> Row | None:
        """Run a raw SELECT and return just the first row (or None)."""
        if not isinstance(statement, SafeSQL):
            raise TypeError("raw_one() requires raw_sql(...)")

        return _row(await fetch_one(statement.sql, statement.params))

    async def raw_execute(self, statement: SafeSQL) -> int:
        """Run a raw data-changing statement (INSERT/UPDATE/DELETE). Returns rows affected."""
        if not isinstance(statement, SafeSQL):
            raise TypeError("raw_execute() requires raw_sql(...)")

        result = await execute(statement.sql, statement.params)
        return result.rowcount

    def transaction(self):
        """Start a transaction (a group of operations that all succeed or all roll back)."""
        return db_transaction()


# A single shared Database instance the rest of the app imports and uses.
db = Database()


# ---------------------------------------------------------------------------
# Convenience top-level functions — short wrappers so simple operations are
# one call instead of a chain. Each just builds a Query under the hood.
# ---------------------------------------------------------------------------


async def db_get(
    table: str,
    *,
    where: dict[str, Any],
    columns: Sequence[str] | None = None,
) -> Row | None:
    """Fetch a single row matching 'where' (optionally selecting only 'columns')."""
    query = db.table(table)

    if columns:
        query.select(*columns)

    return await query.where_dict(where).first()


async def db_insert(table: str, data: dict[str, Any]) -> int | None:
    """Insert one row and return its new id."""
    return await db.table(table).create(data)


async def db_create(table: str, data: dict[str, Any]) -> int | None:
    """Alias for db_insert."""
    return await db.table(table).create(data)


async def db_create_many(table: str, rows: list[dict[str, Any]]) -> int:
    """Insert many rows at once; returns how many were inserted."""
    return await db.table(table).create_many(rows)


async def db_update(table: str, data: dict[str, Any], *, where: dict[str, Any]) -> int:
    """Update rows matching 'where' with 'data'; returns how many changed."""
    return await db.table(table).where_dict(where).update(data)


async def db_patch(table: str, data: dict[str, Any], *, where: dict[str, Any]) -> int:
    """Alias for db_update."""
    return await db.table(table).where_dict(where).patch(data)


async def db_delete(table: str, *, where: dict[str, Any]) -> int:
    """Delete rows matching 'where'; returns how many were deleted."""
    return await db.table(table).where_dict(where).delete()


async def db_exists(table: str, *, where: dict[str, Any]) -> bool:
    """Return True if any row matches 'where'."""
    return await db.table(table).where_dict(where).exists()
