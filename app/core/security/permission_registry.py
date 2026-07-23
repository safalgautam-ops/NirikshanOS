"""Permission registry — the single source of truth for what permissions exist."""

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

    registered = {(p.resource, p.action) for p in all_permissions()}
    existing = await db.table("permissions").all(allow_full_table=True)
    for row in existing:
        if (row["resource"], row["action"]) not in registered:
            await db.table("permissions").where("id", row["id"]).delete()

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
            await (
                db.table("permissions")
                .where("id", permission_id)
                .patch(
                    {
                        "category": permission.category,
                        "description": permission.description,
                    }
                )
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
