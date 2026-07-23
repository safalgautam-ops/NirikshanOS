"""Organization-scoped permission registry - the org-RBAC equivalent of app/core/security/permission_registry.py."""

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
