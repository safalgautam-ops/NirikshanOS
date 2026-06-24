"""Organization-scoped permission registry - the org-RBAC equivalent of
app/core/security/permission_registry.py.

Same idea, different scope: a feature declares the org-level permissions it
needs (see app/features/onboarding/permissions.py) by calling
register_org_permissions() once at import time. sync_to_db(), run at app
startup, upserts every registered permission into the
`organization_permissions` table.

Unlike the system registry, this does NOT auto-grant anything here - there
is no single "Org Admin" row to grant to (every organization has its own,
and orgs start with no roles at all - the owner creates and grants whatever
roles they want from the Roles page).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.db.orm import db
from app.core.utils.ids import new_id


@dataclass(frozen=True)
class OrgPermission:
    resource: str
    action: str
    category: str
    description: str

    @property
    def name(self) -> str:
        return f"{self.resource}.{self.action}"


_registry: dict[tuple[str, str], OrgPermission] = {}


def register_org_permissions(*permissions: OrgPermission) -> None:
    for permission in permissions:
        _registry[(permission.resource, permission.action)] = permission


def all_org_permissions() -> list[OrgPermission]:
    return list(_registry.values())


async def sync_to_db() -> None:
    """Upsert every registered org permission into the catalog table."""
    for permission in all_org_permissions():
        row = await (
            db.table("organization_permissions")
            .where("resource", permission.resource)
            .where("action", permission.action)
            .first()
        )
        if row is None:
            await db.table("organization_permissions").create(
                {
                    "id": new_id(),
                    "resource": permission.resource,
                    "action": permission.action,
                    "category": permission.category,
                    "description": permission.description,
                }
            )
        else:
            await db.table("organization_permissions").where("id", row["id"]).patch(
                {"category": permission.category, "description": permission.description}
            )
