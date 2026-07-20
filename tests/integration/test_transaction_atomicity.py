"""Integration test: db.transaction()'s all-or-nothing guarantee
(app/core/db/pool.py::transaction - report §4.3/§7, the fix already applied
to organisation creation). Reproduces the exact shape of that bug directly:
a valid first write followed by a second write that violates a foreign key,
and proves the first write does not survive outside the transaction.

Uses run_async (the app's own persistent loop), like the other integration
tests - not pytest-asyncio's separate loop, since this test needs the real
DB pool that was created on the app's loop.
"""
import pytest

from app.core.db.orm import db
from app.core.db.pool import ForeignKeyError
from app.core.utils.ids import new_id


async def _attempt_two_writes_second_one_invalid(org_id: str, user_id: str) -> None:
    async with db.transaction():
        await db.table("organizations").create(
            {
                "id": org_id,
                "name": "Rollback Test Org",
                "slug": f"rollback-test-{org_id[:8]}",
                "status": "active",
                "created_by": user_id,
            }
        )
        # Guaranteed to fail: no organization with this id exists, and
        # cases.organization_id has a real foreign key (migrations/008).
        await db.table("cases").create(
            {
                "id": new_id(),
                "organization_id": "00000000-0000-0000-0000-000000000000",
                "case_number": "CASE-ROLLBACK",
                "title": "Should never persist",
                "description": "",
                "classification": "internal",
                "severity": "low",
                "forensic_status": "not_started",
                "created_by": user_id,
            }
        )


def test_first_write_does_not_survive_when_the_second_write_fails(run_async, make_user):
    user = make_user()
    org_id = new_id()

    with pytest.raises(ForeignKeyError):
        run_async(_attempt_two_writes_second_one_invalid(org_id, user["id"]))

    # The organization insert happened first and would have succeeded on
    # its own - if it's still gone after the failure, the transaction
    # really did roll back both writes together, not just the second one.
    row = run_async(db.table("organizations").where("id", org_id).first())
    assert row is None


def test_two_valid_writes_in_one_transaction_both_commit(run_async):
    """The positive case: when nothing fails, both writes really do persist
    together - atomicity isn't just "rollback on error", it's also "commit
    together on success"."""
    org_id = new_id()

    async def _two_valid_writes():
        async with db.transaction():
            await db.table("organizations").create(
                {
                    "id": org_id,
                    "name": "Commit Test Org",
                    "slug": f"commit-test-{org_id[:8]}",
                    "status": "active",
                    "created_by": None,
                }
            )
            await db.table("organizations").where("id", org_id).update({"description": "second write"})

    run_async(_two_valid_writes())

    row = run_async(db.table("organizations").where("id", org_id).first())
    assert row is not None
    assert row["description"] == "second write"
