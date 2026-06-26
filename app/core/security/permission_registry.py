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


@dataclass(frozen=True)  # dataclass objects become immutable after creation
class Permission:
    resource: str  # what it's about
    action: str  # what you can do
    category: str  # heading for grouping it in the UI
    description: str  # human-readable description of the permission

    # computed property that returns the permission name as "resource.action"
    # This glues the two together into a readable name: "user" + "delete" → "user.delete".
    @property
    def name(self) -> str:
        return f"{self.resource}.{self.action}"


# registry of all permissions, keyed by (resource, action) tuple
_registry: dict[tuple[str, str], Permission] = {}


# how a feature writes its permission into the registry
# using this pair (resource, action) as the key means the same permission can't be written twice; if written, overwrites
def register_permissions(*permissions: Permission) -> None:
    for permission in permissions:
        _registry[(permission.resource, permission.action)] = permission


def all_permissions() -> list[Permission]:
    return list(_registry.values())


async def sync_to_db() -> None:

    registered = {
        (p.resource, p.action) for p in all_permissions()
    }  # everything the code knows
    existing = await db.table("permissions").all(
        allow_full_table=True
    )  # everything in the DB
    # go through each existing permission and delete it if it's not registered in code
    for row in existing:
        if (row["resource"], row["action"]) not in registered:
            await db.table("permissions").where("id", row["id"]).delete()

    system_admin = await db.table("roles").where("name", "System Admin").first()

    for permission in all_permissions():  # for each permission the CODE knows
        row = await (
            db.table("permissions")
            .where("resource", permission.resource)
            .where("action", permission.action)
            .first()  # is it already in the DB?
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

        # check if the system admin role is assigned this permission
        # if not, grant it now so the role always has this permission
        # (this avoids needing to manually grant permissions to the system admin role)
        # one permission can belong to many roles
        # one role can have many permissions
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
