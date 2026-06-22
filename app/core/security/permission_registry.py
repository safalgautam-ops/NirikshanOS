"""Permission registry — the single source of truth for what permissions exist.

Mirrors the NAV_KEYS pattern in permissions.py: each feature declares its own
permissions (see app/features/users/permissions.py for an example) by calling
register_permissions() once at import time. sync_to_db(), run at app startup,
upserts every registered permission into the `permissions` table and grants
it to the System Admin role — so adding a permission to a feature is the only
step needed; no hand-written migration/seed SQL required.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.db.orm import db
from app.core.utils.ids import new_id


@dataclass(frozen=True)
class Permission:
    resource: str
    action: str
    category: str
    description: str

    @property
    def name(self) -> str:
        return f"{self.resource}.{self.action}"


_registry: dict[tuple[str, str], Permission] = {}


def register_permissions(*permissions: Permission) -> None:
    for permission in permissions:
        _registry[(permission.resource, permission.action)] = permission


def all_permissions() -> list[Permission]:
    return list(_registry.values())


async def sync_to_db() -> None:
    """Upsert every registered permission into the DB, and grant each one to
    System Admin — keeps that role's "gets everything" guarantee true as new
    permissions get added in code, without ever needing a manual migration."""
    system_admin = await db.table("roles").where("name", "System Admin").first()

    for permission in all_permissions():
        row = await (
            db.table("permissions")
            .where("resource", permission.resource)
            .where("action", permission.action)
            .first()
        )
        if row is None:
            permission_id = new_id()
            await db.table("permissions").create(
                {
                    "id": permission_id,
                    "resource": permission.resource,
                    "action": permission.action,
                    "category": permission.category,
                    "description": permission.description,
                }
            )
        else:
            permission_id = row["id"]
            await db.table("permissions").where("id", permission_id).patch(
                {"category": permission.category, "description": permission.description}
            )

        if system_admin is not None:
            already_granted = await (
                db.table("role_permissions")
                .where("role_id", system_admin["id"])
                .where("permission_id", permission_id)
                .first()
            )
            if already_granted is None:
                await db.table("role_permissions").create(
                    {"role_id": system_admin["id"], "permission_id": permission_id}
                )
