"""RBAC business logic — guards system-role protections, groups permissions for the UI."""

from __future__ import annotations

from itertools import groupby

from app.core.security.permissions import NAV_KEYS
from app.features.rbac import repository


class RBACError(Exception):
    """A user-visible RBAC failure — safe to display directly."""


async def get_roles_page(*, search: str, page: int):
    result = await repository.list_roles(search=search, page=page)
    counts = await repository.get_member_counts([r["id"] for r in result.items])
    for role in result.items:
        role["member_count"] = counts.get(role["id"], 0)
    return result


async def create_role(name: str) -> str:
    name = name.strip() or "New role"
    return await repository.create_role(name=name)


async def update_role_display(role_id: str, *, name: str, description: str, color: str) -> None:
    name = name.strip()
    if not name:
        raise RBACError("Role name is required.")
    await repository.update_role_display(role_id, name=name, description=description.strip(), color=color)


async def toggle_assignable(role_id: str) -> None:
    role = await repository.get_role(role_id)
    if not role:
        raise RBACError("Role not found.")
    if role["is_system"]:
        raise RBACError("System roles can't have assignment blocked.")
    await repository.set_assignable(role_id, not role["is_assignable"])


async def delete_role(role_id: str) -> None:
    role = await repository.get_role(role_id)
    if not role:
        raise RBACError("Role not found.")
    if role["is_system"]:
        raise RBACError("System roles can't be deleted.")
    await repository.delete_role(role_id)


async def duplicate_role(role_id: str) -> str:
    return await repository.duplicate_role(role_id)


"""
groupby takes a list and bundles together items that are next to each other and share the same key
(here, the same category). Think of it like sorting a deck of cards into piles — but with one strict rule:
it only looks at the card directly before the current one.

If the current item has the same category as the one right before it, it goes in the same pile.
The moment the category changes, groupby says "new pile" and starts a fresh group.

If not sorted, groupby may not group items correctly because it only looks at the card directly before the current one.
"""


async def get_permissions_grouped() -> list[tuple[str, list]]:
    """[(category, [permission, ...]), ...] — ready for the Permissions tab."""
    permissions = await repository.get_all_permissions()
    return [
        (category or "Other", list(group))
        for category, group in groupby(permissions, key=lambda p: p["category"])
    ]


async def update_role_permissions(role_id: str, permission_ids: list[str]) -> None:
    await repository.set_role_permissions(role_id, permission_ids)


"""
    deciding what sidebar pages a role can see, and saves that choice.

    all_keys is a full set of every possible sidebar page (nav keys)
    set(selected_keys) >= all_keys asks: "did the user tick every single box"
    the >= on set means "contains all elements of the other set"
    so if all keys are selected, the set is a superset of all_keys, and we store None (unrestricted)
    otherwise, we store the selected keys as-is
"""


async def update_role_sidebar(role_id: str, selected_keys: list[str]) -> None:
    """NULL = unrestricted (every nav key was checked); otherwise store exactly what's checked."""
    all_keys = {key for key, _ in NAV_KEYS}
    keys = None if set(selected_keys) >= all_keys else selected_keys
    await repository.set_sidebar_keys(role_id, keys)


"""
adds a member to a role, if the role is assignable.
"""


async def add_member(role_id: str, user_id: str, assigned_by: str) -> None:
    role = await repository.get_role(role_id)
    if role and not role["is_assignable"]:
        raise RBACError("This role's assignment is currently blocked.")
    await repository.add_member(role_id, user_id, assigned_by)


async def remove_member(role_id: str, user_id: str, *, requested_by: str) -> None:
    if user_id == requested_by:
        raise RBACError("You can't remove yourself from a role.")
    await repository.remove_member(role_id, user_id)
