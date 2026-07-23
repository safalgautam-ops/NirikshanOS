from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Sequence

import asyncmy

from asyncmy.cursors import DictCursor

_pool: asyncmy.Pool | None = None
_current_conn: ContextVar[Any | None] = ContextVar("_current_db_conn", default=None)


class DatabaseError(Exception):
    pass


class DuplicateKeyError(DatabaseError):
    pass


class ForeignKeyError(DatabaseError):
    pass


class NotNullError(DatabaseError):
    pass


class QueryExecutionError(DatabaseError):
    pass


@dataclass(slots=True)
class ExecuteResult:
    lastrowid: int | None
    rowcount: int


def clean_db_error(exc: Exception) -> DatabaseError:
    code = exc.args[0] if exc.args else None
    message = str(exc)

    if code == 1062:
        return DuplicateKeyError(message)

    if code in {1451, 1452}:
        return ForeignKeyError(message)

    if code == 1048:
        return NotNullError(message)

    return QueryExecutionError(message)


async def init_pool(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    db: str,
    minsize: int = 1,
    maxsize: int = 10,
) -> asyncmy.Pool:
    global _pool

    _pool = await asyncmy.create_pool(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db,
        minsize=minsize,
        maxsize=maxsize,
        autocommit=False,
        charset="utf8mb4",
    )

    return _pool


async def close_pool() -> None:
    global _pool

    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


def get_pool() -> asyncmy.Pool:
    if _pool is None:
        raise RuntimeError("Database pool has not been initialized.")

    return _pool


async def fetch_all(query: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    conn = _current_conn.get()

    try:
        if conn is not None:
            async with conn.cursor(DictCursor) as cur:
                await cur.execute(query, params)
                return list(await cur.fetchall())

        pool = get_pool()

        async with pool.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                await cur.execute(query, params)
                rows = list(await cur.fetchall())
                await conn.commit()
                return rows

    except Exception as exc:
        raise clean_db_error(exc) from exc


async def fetch_one(query: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    conn = _current_conn.get()

    try:
        if conn is not None:
            async with conn.cursor(DictCursor) as cur:
                await cur.execute(query, params)
                return await cur.fetchone()

        pool = get_pool()

        async with pool.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                await cur.execute(query, params)
                row = await cur.fetchone()
                await conn.commit()
                return row

    except Exception as exc:
        raise clean_db_error(exc) from exc


async def execute(query: str, params: Sequence[Any] = ()) -> ExecuteResult:
    conn = _current_conn.get()

    try:
        if conn is not None:
            async with conn.cursor() as cur:
                await cur.execute(query, params)

                return ExecuteResult(
                    lastrowid=cur.lastrowid,
                    rowcount=cur.rowcount,
                )

        pool = get_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                await conn.commit()

                return ExecuteResult(
                    lastrowid=cur.lastrowid,
                    rowcount=cur.rowcount,
                )

    except Exception as exc:
        raise clean_db_error(exc) from exc


"""
A transaction prevents flaw in banking transaction.
It says: "Treat these two writes as ONE inseparable unit.
Either both succeed and save together, or — if anything goes wrong — undo everything,
as if neither happened." All-or-nothing. The "undo everything" part is called a rollback.
"""


class transaction:
    def __init__(self):
        self.pool: asyncmy.Pool | None = None
        self.conn = None
        self.token = None

    async def __aenter__(self):
        self.pool = get_pool()
        self.conn = await self.pool.acquire()
        await self.conn.begin()
        self.token = _current_conn.set(self.conn)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                await self.conn.commit()
            else:
                await self.conn.rollback()
        finally:
            _current_conn.reset(self.token)
            self.pool.release(self.conn)
