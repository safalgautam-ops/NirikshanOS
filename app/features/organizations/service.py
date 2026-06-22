"""Admin Organizations business logic."""

from __future__ import annotations

import re

from app.features.organizations import repository


class OrganizationError(Exception):
    """A user-visible organization failure — safe to display directly."""


# derive a unique slug column from the org name
def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


"""
first it fetches one page of organizations, filtered by search term and status
then it collects the IDs of just those organizations and asks for all their member counts in one call
returns a dictionary like {"org-abc": 42, "org-def": 23}

the important concept: the N+1 problem
Imagine doing this the naive way:

Run 1 query to get the page of organizations (say 20 of them).
Then, for each organization, run a separate query to count its members.

That's 1 query for the list, plus 20 more for the counts — 21 queries to display one page. This is the "N+1" problem:
    1 query to get N things, then N more queries (one per thing). The "+1" is the initial list query, and
    the "N" is the one-per-row follow-ups.
Why is that bad? Each query has overhead — a round-trip to the database, time spent waiting.
Twenty-one round-trips is dramatically slower than two, and it gets worse as the page grows or traffic increases.
It's a classic, easy-to-introduce performance trap.

Instead of one count-query per organization, we use a single query to get all the counts at once.

"""


async def get_organizations_page(*, search: str, status: str, page: int):
    result = await repository.list_organizations(
        search=search, status=status, page=page
    )
    counts = await repository.get_member_counts([o["id"] for o in result.items])
    for org in result.items:
        org["member_count"] = counts.get(org["id"], 0)
    return result


async def create_organization(
    *, name: str, description: str, status: str, created_by: str
) -> str:
    name = name.strip()
    if not name:
        raise OrganizationError("Organization name is required.")

    slug = _slugify(name)
    if await repository.get_by_slug(slug):
        raise OrganizationError("An organization with that name already exists.")

    return await repository.create_organization(
        name=name,
        slug=slug,
        description=description.strip(),
        status=status,
        created_by=created_by,
    )


async def update_organization(
    org_id: str, *, name: str, description: str, status: str
) -> None:
    name = name.strip()
    if not name:
        raise OrganizationError("Organization name is required.")
    await repository.update_organization(
        org_id, name=name, description=description.strip(), status=status
    )


async def delete_organization(org_id: str) -> None:
    await repository.delete_organization(org_id)
