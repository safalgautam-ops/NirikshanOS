from __future__ import annotations

# ContextVar is a magic sticky note that somehow shows a different message depending on
# which request you're currently handling.
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Sequence

import asyncmy

# fetching rows from a database comes back as dictionary (value by names) - not older tuples
from asyncmy.cursors import DictCursor

_pool: asyncmy.Pool | None = None
# _current_con is the note that holds either None or a specific connection
# example: a note is up -- "reuse this one for everything right now"
_current_conn: ContextVar[Any | None] = ContextVar("_current_db_conn", default=None)


# error with something wrong with the database
class DatabaseError(Exception):
    pass  # nothing here, move on


# you tried to add a duplicate
class DuplicateKeyError(DatabaseError):
    pass


# you broke a link between tables
class ForeignKeyError(DatabaseError):
    pass


# you left a required field empty
class NotNullError(DatabaseError):
    pass


# some other database problem
class QueryExecutionError(DatabaseError):
    pass


# shortcut that writes all the boring code while making a class in Python automatically
@dataclass(slots=True)
# slots = True means Python will only ever hold these two specific things, nothing more (less memory usage and faster)
class ExecuteResult:
    # listing what we want to store, and Python handles the rest
    lastrowid: int | None
    rowcount: int


# a function takes one input, exc -- raw ugly error MySQL threw
def clean_db_error(exc: Exception) -> DatabaseError:
    # dig the numeric code out of the raw error (cryptic numbers of errors)
    code = exc.args[0] if exc.args else None
    # grab the error's text message as a string
    message = str(exc)

    # 1062: MySQL's way of saying "the problem is a duplicate"
    if code == 1062:
        return DuplicateKeyError(message)

    if code in {1451, 1452}:
        return ForeignKeyError(message)

    if code == 1048:
        return NotNullError(message)

    # anything else, just the generic database error
    return QueryExecutionError(message)


# async lets the program do other work while waiting instead of freezing
# * means every argument should be passed by name, instead of position
async def init_pool(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    db: str,
    minsize: int = 1,  # minimum 1 connection ready
    maxsize: int = 10,  # maximum 10 connections ready
) -> asyncmy.Pool:  # the function gives a pool object
    # : marks the end of the header and the start of the function body
    global _pool  # file-level _pool

    # actually builds the rack of connections, using the address/login detailes passed in
    # await means "pause here until the connection pool is ready"
    _pool = await asyncmy.create_pool(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db,
        minsize=minsize,
        maxsize=maxsize,
        autocommit=False,  # database does not save your changes automatically.
        charset="utf8mb4",  # text format that supports all characters
    )

    return _pool


# runs once at shutdown, close every connection cleanly and reset _pool to None
async def close_pool() -> None:
    global _pool

    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


# getting and checking the pool
def get_pool() -> asyncmy.Pool:
    if _pool is None:
        raise RuntimeError("Database pool has not been initialized.")

    return _pool


# run a query, get all matching rows
async def fetch_all(query: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    # is there any connection i should reuse?
    conn = _current_conn.get()

    try:
        # a note is up -- resuse that connection
        if conn is not None:
            # make a cursor (the little worker that runs query) in dictionary style
            async with conn.cursor(DictCursor) as cur:
                # run the query passing params separately
                await cur.execute(query, params)
                # returns all the rows in plain list
                return list(await cur.fetchall())

        # no note -> normal behaviour
        pool = get_pool()

        async with pool.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                await cur.execute(query, params)
                rows = list(await cur.fetchall())
                # autocommit is off, so MySQL opened an implicit transaction for
                # this SELECT (REPEATABLE READ snapshot). End it before the
                # connection goes back to the pool, or the next borrower reuses
                # this same stale snapshot and misses commits made elsewhere.
                await conn.commit()
                return rows

    # if anything inside the try raised an error, catch it as exc
    except Exception as exc:
        raise clean_db_error(exc) from exc


# read the note, two branches (reuse vs. borrow), error translation
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
                # see the matching comment in fetch_all - don't leave this
                # connection's implicit read transaction open in the pool.
                await conn.commit()
                return row

    except Exception as exc:
        raise clean_db_error(exc) from exc


async def execute(query: str, params: Sequence[Any] = ()) -> ExecuteResult:
    conn = _current_conn.get()

    try:  # joined an operation someone else is running --> don't commit
        if conn is not None:
            async with conn.cursor() as cur:
                await cur.execute(query, params)

                return ExecuteResult(
                    # INSERTING a row, the database auto-assigns it an id; the new id is shown
                    lastrowid=cur.lastrowid,
                    # how many rows the query affected (e.g. UPDATE that changed 3 rows)
                    rowcount=cur.rowcount,
                )

        pool = get_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                # it grabbed a standalone, one-off operation with nobody else managing it,
                # this function is responsible for saving its own work
                await conn.commit()  # save the data permanently

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

    # runs when the async with block begins
    async def __aenter__(self):
        self.pool = get_pool()  # get the connection rack
        self.conn = (
            await self.pool.acquire()
        )  # borrow one connection, carry every query inside the block
        await self.conn.begin()  # tell DB: a transaction starts now -- track my changes as a pending group; don't save them yet
        self.token = _current_conn.set(
            self.conn
        )  # put up the sticky note pointing at this connection (every execute/fetch_all/fetch_one called inside the block will read the note)
        return self

    # runs when the block ends, success or failure
    async def __aexit__(self, exc_type, exc, tb):
        try:
            # if the block finished cleanly (no error)
            if exc_type is None:
                await (
                    self.conn.commit()
                )  # save all the grouped writes together, in one go
            else:  # error happened inside the block
                await (
                    self.conn.rollback()
                )  # undo every changes since begin(), as if the transaction never ran
        finally:
            _current_conn.reset(self.token)  # take the sticky note down
            self.pool.release(self.conn)  # return the borrowed connection to the rack
