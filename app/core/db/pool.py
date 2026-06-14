"""MySQL connection pool.

This module wraps the raw asyncmy driver behind a small module-level
pool object. It is the ONLY place that talks to the asyncmy driver
directly - Model and QueryBuilder both go through get_pool() to borrow
a ready-connection, run a query, and return it to the pool so that everything feel faster.
"""

# The driver (asyncmy) -- a ready made library that actually knows how to speak MySQL's language over the network.
import asyncmy

# Holds the single shared pool for the whole app. Starts as None until
# init_pool() runs in the Quart before_serving hook.
# _ is a Python convetion meaning this is private -- don't reach in and try to touch from outside this file
_pool: asyncmy.Pool | None = None


async def init_pool(
    *, host: str, port: int, user: str, password: str, db: str
) -> asyncmy.Pool:
    global _pool
    # minsize/maxsize keep a small pool of reusable connections instead of
    # opening a new MySQL connection per request.
    # global __pool means file level __pool, not a new local one. Without global, the pool would be created and then thrown away the instant the function returned.
    _pool = await asyncmy.create_pool(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db,
        minsize=1,
        maxsize=10,
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        # Closes every pooled connection cleanly on app shutdown.
        _pool.close()
        await _pool.wait_closed()
        _pool = None


def get_pool() -> asyncmy.Pool:
    if _pool is None:
        # Fails loudly if Model/QueryBuilder is used before startup ran.
        raise RuntimeError(
            "Database pool has not been initialized. Call init_pool() first."
        )
    return _pool


# got the pool, now a way to actually borrow a connection and run a query with it
# query: str — the SQL text, like "SELECT email FROM users WHERE id = %s". The %s is a placeholder — a blank to be filled in safely.
# params: list | tuple = () — the actual values to fill into those %s blanks.
# The = () means "if the caller gives no values, default to an empty tuple" (a tuple is just an ordered group of items; () is an empty one).
# This is the SQL-injection defense: the values are passed separately here, never glued into the query string, so the database treats them strictly as data, never as commands.
# Returns a list of rows, where each row is a tuple of column values (returns every matching rows)
async def fetchall(query: str, params: list | tuple = ()) -> list[tuple]:
    # Borrow a connection + cursor, run a SELECT, return every row, and
    # release the connection back to the pool - callers never touch
    # pool.acquire()/cursor() directly.
    pool = get_pool()
    # Borrow a connection from the pool, call it conn, use it inside this block, and automatically return it to the pool the instant the block ends
    async with pool.acquire() as conn:
        # borrow a cursor (cur) -- the worker who runs the query
        async with conn.cursor() as cur:
            # the worker runs the query: feeds the params into the query %s
            await cur.execute(query, params)
            return await cur.fetchall()


# either one row (a tuple), or None if nothing matched
async def fetchone(query: str, params: list | tuple = ()) -> tuple | None:
    # Same as fetchall(), but for queries that return at most one row
    # (COUNT(*), SELECT ... WHERE id = %s).
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return (
                await cur.fetchone()
            )  # asking the cursor for just one row (the first one)


# for writing data
async def execute(query: str, params: list | tuple = ()) -> int:
    # For INSERT/UPDATE/DELETE - commits (asyncmy connections don't
    # autocommit) and returns lastrowid, the auto-generated id from an
    # INSERT (0 for UPDATE/DELETE).
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            # save the changes permanently; without it, the change would be thrown away ("rolled back")
            await conn.commit()
            # lastrowid is that freshly created it(for insert). But for UPDATE and DELETE there's no new row created, so this comes back as 0
            return cur.lastrowid
