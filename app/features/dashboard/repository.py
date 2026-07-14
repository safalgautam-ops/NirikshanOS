"""DB access for dashboard widgets - platform-wide (admin) aggregates.

Every query here pulls only the columns a widget needs and aggregates in
Python (Counter/manual grouping) rather than SQL GROUP BY/SUM: the query
builder's select() quotes every entry as a plain identifier (see
orm.py's _quote_column), so it can't safely carry aggregate expressions
like COUNT(*)/SUM(...), and this platform's data volumes are small enough
that pulling raw rows and summing in Python is not a real cost.

Org-scoped widgets (members, cases, subscriptions) reuse each owning
feature's own repository instead of duplicating queries here - see
dashboard/service.py.
"""

from __future__ import annotations

from app.core.db.orm import db


async def count_users() -> int:
    return await db.table("user").count()


async def count_organizations() -> dict:
    rows = await db.table("organizations").select("verification_status").all(allow_full_table=True)
    pending = sum(1 for row in rows if row["verification_status"] == "pending")
    return {"total": len(rows), "pending": pending}


async def count_active_subscriptions() -> int:
    return await db.table("org_subscriptions").where_in("status", ["active", "grandfathered"]).count()


async def list_completed_transaction_amounts() -> list[dict]:
    """created_at + total_amount for every completed payment - enough to
    compute both the all-time revenue total and a monthly trend."""
    return await (
        db.table("payment_transactions")
        .where("status", "completed")
        .select("created_at", "total_amount")
        .all(allow_full_table=True)
    )


async def list_session_created_dates(since) -> list[dict]:
    return await (
        db.table("session")
        .where("createdAt", since, ">=")
        .select("createdAt")
        .all(allow_full_table=True)
    )


async def list_task_module_names() -> list[dict]:
    return await db.table("analysis_tasks").select("module_name").all(allow_full_table=True)


async def list_active_subscription_plan_ids() -> list[dict]:
    return await (
        db.table("org_subscriptions")
        .where_in("status", ["active", "grandfathered"])
        .select("plan_id")
        .all(allow_full_table=True)
    )


async def list_recent_organizations(limit: int = 5) -> list[dict]:
    return await (
        db.table("organizations")
        .select("id", "name", "status", "verification_status", "created_at")
        .order_by("created_at", "desc")
        .limit(limit)
        .all()
    )
