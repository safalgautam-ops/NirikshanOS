"""It's a query builder — a tool for building and running SQL without writing SQL by hand."""

from __future__ import annotations

import copy
import re
from dataclasses import (
    dataclass,
    field,
)
from typing import Any, Callable, Literal, Sequence

from app.core.db.pool import (
    execute,
    fetch_all,
    fetch_one,
)
from app.core.db.pool import (
    transaction as db_transaction,
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_ALLOWED_OPERATORS = {
    "=",
    "!=",
    "<>",
    ">",
    ">=",
    "<",
    "<=",
    "LIKE",
    "NOT LIKE",
    "IN",
    "NOT IN",
    "IS",
    "IS NOT",
}

Direction = Literal["asc", "desc", "ASC", "DESC"]
JoinType = Literal["INNER", "LEFT", "RIGHT"]


class Row(dict):
    """A Row is just a normal dictionary with one extra convenience: dot-style access."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


@dataclass(slots=True)
class Page:
    """Holds one 'page' of results plus all the numbers needed for page-by-page navigation."""

    items: list[Row]
    page: int
    per_page: int
    total: int
    pages: int
    has_next: bool
    has_prev: bool


@dataclass(slots=True)
class CursorPage:
    """An alternative paging style ('cursor'-based) — instead of page numbers, it remembers a 'bookmark' pointing to where the next batch should start."""

    items: list[Row]
    per_page: int
    has_next: bool
    next_cursor: dict[str, Any] | None


@dataclass(slots=True)
class SafeSQL:
    """A small bundle holding a piece of SQL text plus the values that go into it."""

    sql: str
    params: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class Condition:
    """One WHERE condition: a bit of SQL text plus its values."""

    sql: str
    params: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class ConditionGroup:
    """A group of conditions joined by AND or OR."""

    connector: str
    items: list[Condition | ConditionGroup] = field(default_factory=list)


@dataclass(slots=True)
class Join:
    """All the info needed to join (combine) another table onto the main one."""

    join_type: str
    table: str
    alias: str | None
    left: str
    right: str


@dataclass(slots=True)
class Prefetch:
    """Settings for the 'prefetch' feature: after fetching the main rows, load their related rows in ONE extra query (instead of one query per row, which is slow)."""

    name: str
    table: str
    local_key: str
    foreign_key: str
    many: bool = True
    fields: Sequence[str] | None = None
    where: dict[str, Any] | None = None
    order_by: tuple[str, str] | None = None
    limit: int = 1000


def raw_sql(sql: str, params: Sequence[Any] = ()) -> SafeSQL:
    """An explicit, deliberate wrapper for raw SQL."""

    cleaned = sql.strip()

    if not cleaned:
        raise ValueError("Raw SQL cannot be empty")

    dangerous_tokens = [";", "--", "/*", "*/", "\x00"]

    if any(token in cleaned for token in dangerous_tokens):
        raise ValueError("Unsafe raw SQL token detected")

    return SafeSQL(sql=cleaned, params=list(params))


def _to_row(value: Any) -> Any:
    """Recursively turn plain dicts (and any nested dicts/lists) into Row objects, so the whole result tree gets the convenient dot-access (row.field)."""
    if isinstance(value, Row):
        return value

    if isinstance(value, dict):
        return Row({key: _to_row(item) for key, item in value.items()})

    if isinstance(value, list):
        return [_to_row(item) for item in value]

    return value


def _nest_double_underscore(row: dict[str, Any]) -> dict[str, Any]:
    """When a query joins tables, columns get labeled like "analyzer__name" to show which table they came from."""

    output: dict[str, Any] = {}
    nested_keys: set[str] = set()

    for key, value in row.items():
        if "__" not in key:
            output[key] = value
            continue

        parent, child = key.split("__", 1)
        nested_keys.add(parent)

        if parent not in output or output[parent] is None:
            output[parent] = {}

        output[parent][child] = value

    for parent in nested_keys:
        nested = output.get(parent)

        if isinstance(nested, dict) and all(value is None for value in nested.values()):
            output[parent] = None

    return output


def _rows(rows: list[dict[str, Any]]) -> list[Row]:
    """Convert a LIST of flat dictionaries into a list of nice nested Row objects."""
    return [_to_row(_nest_double_underscore(row)) for row in rows]


def _row(row: dict[str, Any] | None) -> Row | None:
    """Convert a SINGLE flat dictionary (or None) into a nested Row (or None)."""
    if row is None:
        return None
    return _to_row(_nest_double_underscore(row))


def _check_identifier(value: str) -> None:
    """Raise an error if 'value' is NOT a safe, simple name (letters/numbers/underscores)."""
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid SQL identifier: {value}")


def _quote_identifier(value: str) -> str:
    """Validate a name, then wrap it in backticks like `email`."""
    _check_identifier(value)
    return f"`{value}`"


def _quote_column(value: str) -> str:
    """Safely quote a column reference, handling the different shapes a column can take: - "*"            -> all columns - "email"        -> `email` - "users.email"  -> `users`.`email`   (table.column) - "users.*"      -> `users`.*"""
    value = value.strip()

    if value == "*":
        return "*"

    parts = value.split(".")

    if len(parts) == 1:
        return _quote_identifier(parts[0])

    if len(parts) == 2:
        table, column = parts

        if column == "*":
            return f"{_quote_identifier(table)}.*"

        return f"{_quote_identifier(table)}.{_quote_identifier(column)}"

    raise ValueError(f"Invalid column: {value}")


def _select_expr(value: str) -> str:
    """Build one item of a SELECT list, supporting the "X AS alias" renaming form."""
    raw = value.strip()
    lower = raw.lower()

    if " as " in lower:
        left, alias = re.split(r"\s+as\s+", raw, flags=re.IGNORECASE, maxsplit=1)
        left = left.strip()
        alias = alias.strip()

        if left.isdigit():
            return f"{left} AS {_quote_identifier(alias)}"

        return f"{_quote_column(left)} AS {_quote_identifier(alias)}"

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
    """Given a column reference like "users.createdAt", return just the final piece "createdAt", because that's the key name the value will appear under in the result row."""
    return column.split(".")[-1]


def _make_condition(column: str, value: Any = None, op: str = "=") -> Condition:
    """Build one Condition (SQL text + params) from a column, a value, and an operator."""
    op = _safe_operator(op)

    if op in {"IN", "NOT IN"}:
        values = list(value or [])

        if not values and op == "IN":
            return Condition("1 = 0")

        if not values and op == "NOT IN":
            return Condition("1 = 1")

        placeholders = ", ".join(["%s"] * len(values))
        return Condition(f"{_quote_column(column)} {op} ({placeholders})", values)

    if value is None and op in {"=", "IS"}:
        return Condition(f"{_quote_column(column)} IS NULL")

    if value is None and op in {"!=", "<>", "IS NOT"}:
        return Condition(f"{_quote_column(column)} IS NOT NULL")

    return Condition(f"{_quote_column(column)} {op} %s", [value])


class FilterGroup:
    """A helper for building a GROUP of conditions joined by AND or OR."""

    def __init__(self, connector: Literal["AND", "OR"] = "AND"):
        self.group = ConditionGroup(connector=connector.upper())

        if self.group.connector not in {"AND", "OR"}:
            raise ValueError("Filter group connector must be AND or OR")

    def where(self, column: str, value: Any = None, op: str = "=") -> FilterGroup:
        """Add one condition like `column = value`."""
        self.group.items.append(_make_condition(column, value, op))
        return self

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
        """Create a NESTED group (the parentheses part of SQL), e.g. (A OR B)."""
        child = FilterGroup(connector)
        callback(child)

        if child.group.items:
            self.group.items.append(child.group)

        return self


class Query:
    """The main builder."""

    def __init__(self, table: str, alias: str | None = None):
        _check_identifier(table)

        if alias is not None:
            _check_identifier(alias)

        self.table = table
        self.alias = alias

        self._selects: list[str] = []
        self._conditions: list[Condition | ConditionGroup] = []
        self._joins: list[Join] = []
        self._orders: list[tuple[str, str]] = []
        self._groups: list[str] = []

        self._limit: int | None = None
        self._offset: int | None = None
        self._distinct = False
        self._for_update = False

        self._prefetches: list[Prefetch] = []

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
        self._selects.extend(columns)
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
            self.where(column, value)

        return self

    def or_where(self, conditions: Sequence[tuple]) -> Query:
        """Add a group of OR conditions from a list of tuples."""
        group = FilterGroup("OR")

        for item in conditions:
            if len(item) == 2:
                column, value = item
                group.where(column, value)
            elif len(item) == 3:
                column, op, value = item
                group.where(column, value, op)
            else:
                raise ValueError("OR condition must be (column, value) or (column, op, value)")

        if group.group.items:
            self._conditions.append(group.group)

        return self

    def where_group(
        self,
        callback: Callable[[FilterGroup], None],
        *,
        connector: Literal["AND", "OR"] = "AND",
    ) -> Query:
        """Add a nested condition group built by your callback function."""
        group = FilterGroup(connector)
        callback(group)

        if group.group.items:
            self._conditions.append(group.group)

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
                [start, end],
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
        """Search for 'term' across SEVERAL columns at once, matching if ANY of them contain it."""
        if not columns:
            return self

        return self.where_group(
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
        """Combine another table into the query."""
        join_type = join_type.upper()

        if join_type not in {"INNER", "LEFT", "RIGHT"}:
            raise ValueError("join_type must be INNER, LEFT, or RIGHT")

        _check_identifier(table)

        if alias is not None:
            _check_identifier(alias)

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
        """Load a related row by JOINING it in and selecting its columns with a 'name__' prefix (so _nest_double_underscore can later turn them into row.name.field)."""
        alias = alias or name

        self.left_join(
            table,
            f"{self.main_ref}.{local_key}",
            f"{alias}.{foreign_key}",
            alias=alias,
        )

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
        """Schedule loading of related rows in a SEPARATE follow-up query (run after the main one)."""
        final_fields = list(fields or ["*"])

        if fields and foreign_key not in final_fields:
            final_fields.append(foreign_key)

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

    def _build_condition_item(self, item: Condition | ConditionGroup) -> tuple[str, list[Any]]:
        """Turn one condition OR one nested group into SQL text + params."""
        if isinstance(item, Condition):
            return item.sql, list(item.params)

        parts: list[str] = []
        params: list[Any] = []

        for child in item.items:
            sql, child_params = self._build_condition_item(child)

            if sql:
                parts.append(sql)
                params.extend(child_params)

        if not parts:
            return "", []

        joined = f" {item.connector} ".join(parts)
        return f"({joined})", params

    def _build_where(self) -> tuple[str, list[Any]]:
        """Build the full WHERE clause text + params from all collected conditions."""
        if not self._conditions:
            return "", []

        parts: list[str] = []
        params: list[Any] = []

        for condition in self._conditions:
            sql, condition_params = self._build_condition_item(condition)

            if sql:
                parts.append(sql)
                params.extend(condition_params)

        if not parts:
            return "", []

        return " WHERE " + " AND ".join(parts), params

    def _build_joins(self) -> str:
        """Build the JOIN portion of the SQL from all collected joins."""
        if not self._joins:
            return ""

        parts = []

        for join in self._joins:
            table = _quote_identifier(join.table)

            if join.alias:
                table = f"{table} AS {_quote_identifier(join.alias)}"

            parts.append(
                f" {join.join_type} JOIN {table}"
                f" ON {_quote_column(join.left)} = {_quote_column(join.right)}"
            )

        return "".join(parts)

    def _build_select_sql(
        self,
        *,
        count: bool = False,
        count_column: str = "*",
        distinct_count: bool = False,
    ) -> tuple[str, list[Any]]:
        """Build a complete SELECT statement (text + params)."""
        if count:
            if distinct_count:
                select_part = f"COUNT(DISTINCT {_quote_column(count_column)}) AS total"
            else:
                select_part = f"COUNT({_quote_column(count_column)}) AS total"
        else:
            selected = self._selects or [f"{self.main_ref}.*"]
            select_part = ", ".join(_select_expr(column) for column in selected)

        distinct = "DISTINCT " if self._distinct and not count else ""

        sql = f"SELECT {distinct}{select_part} FROM {self.table_ref}"
        sql += self._build_joins()

        where_sql, params = self._build_where()
        sql += where_sql

        if self._groups and not count:
            sql += " GROUP BY " + ", ".join(_quote_column(column) for column in self._groups)

        if self._orders and not count:
            order_sql = ", ".join(
                f"{_quote_column(column)} {direction}" for column, direction in self._orders
            )
            sql += " ORDER BY " + order_sql

        if self._limit is not None and not count:
            sql += " LIMIT %s"
            params.append(self._limit)

        if self._offset is not None and not count:
            sql += " OFFSET %s"
            params.append(self._offset)

        if self._for_update and not count:
            sql += " FOR UPDATE"

        return sql, params

    async def all(self, *, allow_full_table: bool = False) -> list[Row]:
        """Run the query and return ALL matching rows."""
        if self._limit is None and not allow_full_table:
            raise ValueError(
                "Use .paginate(), .cursor_paginate(), .limit(), " "or all(allow_full_table=True)"
            )

        sql, params = self._build_select_sql()
        result = _rows(await fetch_all(sql, params))

        if self._prefetches:
            await self._apply_prefetches(result)

        return result

    async def first(self) -> Row | None:
        """Run the query but return only the FIRST matching row (or None if none)."""
        query = self.clone()
        query.limit(1)

        sql, params = query._build_select_sql()
        return _row(await fetch_one(sql, params))

    async def count(self, column: str = "*") -> int:
        """Return how many rows match (ignoring limit/offset/ordering)."""
        query = self.clone()
        query._limit = None
        query._offset = None
        query._orders = []

        sql, params = query._build_select_sql(count=True, count_column=column)
        row = await fetch_one(sql, params)

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
        query._selects = ["1 as found"]
        query.limit(1)

        sql, params = query._build_select_sql()
        row = await fetch_one(sql, params)

        return row is not None

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
        page = max(page, 1)
        per_page = max(1, min(per_page, max_per_page))

        if count_distinct:
            total = await self.count_distinct(count_distinct)
        else:
            total = await self.count()

        query = self.clone()
        query.limit(per_page)
        query.offset((page - 1) * per_page)

        items = await query.all()

        pages = (total + per_page - 1) // per_page if total else 0

        return Page(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1,
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
        """'Cursor' pagination: instead of page numbers, you pass a bookmark (the cursor) pointing just past the last row you saw, and get the next batch after it."""
        per_page = max(1, min(per_page, max_per_page))
        direction = _safe_direction(direction)

        query = self.clone()
        query._orders = []

        if query._selects:
            needed_columns = [cursor_column]

            if cursor_id_column:
                needed_columns.append(cursor_id_column)

            selected_names = {item.split(" as ")[-1].split(".")[-1].strip("` ") for item in query._selects}

            for column in needed_columns:
                key = _result_key(column)

                if key not in selected_names:
                    query.select(column)

        if cursor_value is not None:
            compare = "<" if direction == "DESC" else ">"

            if cursor_id_column and cursor_id_value is not None:
                id_compare = "<" if direction == "DESC" else ">"

                query.where_group(
                    lambda group: group.where(cursor_column, cursor_value, compare).group_by(
                        "AND",
                        lambda inner: inner.where(cursor_column, cursor_value).where(
                            cursor_id_column, cursor_id_value, id_compare
                        ),
                    ),
                    connector="OR",
                )
            else:
                query.where(cursor_column, cursor_value, compare)

        query.order_by(cursor_column, direction)

        if cursor_id_column:
            query.order_by(cursor_id_column, direction)

        query.limit(per_page + 1)

        rows = await query.all()
        has_next = len(rows) > per_page
        items = rows[:per_page]

        next_cursor = None

        if has_next and items:
            last = items[-1]
            cursor_key = _result_key(cursor_column)

            next_cursor = {
                "cursor_value": last.get(cursor_key),
            }

            if cursor_id_column:
                id_key = _result_key(cursor_id_column)
                next_cursor["cursor_id_value"] = last.get(id_key)

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

        columns = list(data.keys())
        values = list(data.values())

        column_sql = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))

        sql = f"INSERT INTO {_quote_identifier(self.table)} ({column_sql}) VALUES ({placeholders})"
        result = await execute(sql, values)

        return result.lastrowid

    async def create(self, data: dict[str, Any]) -> int | None:
        """Friendly alias for insert()."""
        return await self.insert(data)

    async def bulk_insert(self, rows: list[dict[str, Any]]) -> int:
        """Insert MANY rows in a single statement. Returns how many rows were inserted."""
        if not rows:
            return 0

        columns = list(rows[0].keys())

        for row in rows:
            if list(row.keys()) != columns:
                raise ValueError("All bulk_insert rows must have the same columns")

        column_sql = ", ".join(_quote_identifier(column) for column in columns)
        row_placeholder = "(" + ", ".join(["%s"] * len(columns)) + ")"
        placeholders = ", ".join([row_placeholder] * len(rows))

        values: list[Any] = []

        for row in rows:
            values.extend(row.values())

        sql = f"INSERT INTO {_quote_identifier(self.table)} ({column_sql}) VALUES {placeholders}"
        result = await execute(sql, values)

        return result.rowcount

    async def create_many(self, rows: list[dict[str, Any]]) -> int:
        """Friendly alias for bulk_insert()."""
        return await self.bulk_insert(rows)

    async def update(self, data: dict[str, Any]) -> int:
        """Update matching rows with new values. Returns how many rows changed."""
        if not data:
            raise ValueError("update data cannot be empty")

        if not self._conditions:
            raise ValueError("Refusing UPDATE without WHERE condition")

        assignments = ", ".join(f"{_quote_identifier(column)} = %s" for column in data.keys())

        where_sql, where_params = self._build_where()

        sql = f"UPDATE {_quote_identifier(self.table)} SET {assignments}{where_sql}"
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
        """Update many rows with DIFFERENT values each, in a single statement, using a SQL CASE expression keyed on each row's 'key' (e.g. its id)."""
        if not rows:
            return 0

        if not update_columns:
            raise ValueError("update_columns cannot be empty")

        _check_identifier(key)

        for row in rows:
            if key not in row:
                raise ValueError(f"Missing bulk update key: {key}")

            for column in update_columns:
                if column not in row:
                    raise ValueError(f"Missing bulk update column: {column}")

        key_values = [row[key] for row in rows]

        set_parts = []
        params: list[Any] = []

        for column in update_columns:
            _check_identifier(column)

            case_sql = f"{_quote_identifier(column)} = CASE {_quote_identifier(key)}"

            for row in rows:
                case_sql += " WHEN %s THEN %s"
                params.extend([row[key], row[column]])

            case_sql += f" ELSE {_quote_identifier(column)} END"
            set_parts.append(case_sql)

        placeholders = ", ".join(["%s"] * len(key_values))
        params.extend(key_values)

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
            raise ValueError("Refusing DELETE without WHERE condition")

        where_sql, params = self._build_where()

        sql = f"DELETE FROM {_quote_identifier(self.table)}{where_sql}"
        result = await execute(sql, params)

        return result.rowcount

    async def bulk_delete(self, column: str, values: Sequence[Any]) -> int:
        """Delete all rows where 'column' is one of the given values."""
        return await self.where_in(column, values).delete()

    async def upsert(
        self,
        data: dict[str, Any],
        *,
        update_columns: Sequence[str],
    ) -> int | None:
        """Insert a row, but if it would collide with an existing one (duplicate key), UPDATE the listed columns instead."""
        if not data:
            raise ValueError("upsert data cannot be empty")

        if not update_columns:
            raise ValueError("update_columns cannot be empty")

        columns = list(data.keys())
        values = list(data.values())

        column_sql = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))

        update_sql = ", ".join(
            f"{_quote_identifier(column)} = VALUES({_quote_identifier(column)})" for column in update_columns
        )

        sql = (
            f"INSERT INTO {_quote_identifier(self.table)} ({column_sql}) "
            f"VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_sql}"
        )

        result = await execute(sql, values)
        return result.lastrowid

    async def _apply_prefetches(self, rows: list[Row]) -> None:
        """For each scheduled prefetch, load the related rows in one query and attach them onto the parent rows under the prefetch's 'name'."""
        if not rows:
            return

        for prefetch in self._prefetches:
            parent_ids = [
                row.get(prefetch.local_key) for row in rows if row.get(prefetch.local_key) is not None
            ]

            if not parent_ids:
                for row in rows:
                    row[prefetch.name] = [] if prefetch.many else None
                continue

            child_query = Query(prefetch.table)

            if prefetch.fields:
                child_query.select(*prefetch.fields)

            child_query.where_in(prefetch.foreign_key, parent_ids)

            if prefetch.where:
                child_query.where_dict(prefetch.where)

            if prefetch.order_by:
                child_query.order_by(prefetch.order_by[0], prefetch.order_by[1])

            child_query.limit(prefetch.limit)

            children = await child_query.all()

            grouped: dict[Any, list[Row]] = {}

            for child in children:
                key = child.get(prefetch.foreign_key)
                grouped.setdefault(key, []).append(child)

            for row in rows:
                local_value = row.get(prefetch.local_key)

                if prefetch.many:
                    row[prefetch.name] = grouped.get(local_value, [])
                else:
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


db = Database()


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
