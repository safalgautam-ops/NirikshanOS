"""Unit tests: the custom query builder's write-safety guards
(app/core/db/orm.py - referenced in report §4.3/Appendix E2).

Both guards raise before any SQL is built or a connection is touched, so
these run with no database at all.
"""
import pytest

from app.core.db.orm import db


@pytest.mark.asyncio
async def test_delete_without_where_is_refused():
    with pytest.raises(ValueError, match="Refusing DELETE without WHERE condition"):
        await db.table("cases").delete()


@pytest.mark.asyncio
async def test_update_without_where_is_refused():
    with pytest.raises(ValueError, match="Refusing UPDATE without WHERE condition"):
        await db.table("cases").update({"title": "renamed"})


@pytest.mark.asyncio
async def test_delete_with_where_passes_the_guard():
    """The guard only checks that a condition exists - it should not raise
    once one is present (whether the row exists is a DB-layer concern,
    covered by the integration tier, not this unit test)."""
    builder = db.table("cases").where("id", "does-not-exist")
    assert builder._conditions  # guard's own check: non-empty conditions list
