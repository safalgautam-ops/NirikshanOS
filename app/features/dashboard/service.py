"""Assembles the two dashboard variants (admin/platform-wide, org-scoped)
into chart-ready dicts - every number the templates need is precomputed
here (bar percentages, formatted display strings) so dashboard.html stays
presentation-only, same as every other macro/template in this app."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.security.org_permissions import (
    get_user_org_membership,
    get_user_org_permission_names,
    is_org_owner,
)
from app.features.audit import service as audit_service
from app.features.cases import service as cases_service
from app.features.dashboard import repository as repo
from app.features.finance import repository as finance_repository
from app.features.onboarding.permissions import ORG_BILLING_MANAGE, ORG_STAFF_VIEW
from app.features.organizations import repository as org_repository
from app.features.plans import repository as plans_repository
from app.features.plans import service as plans_service

_CASE_STATUSES = [("open", "Open"), ("active", "Active"), ("closed", "Closed"), ("archived", "Archived")]

# Matches the badge color convention this app already uses for these same
# status strings elsewhere (see cases/list.html's status_variant) - open is
# the "needs attention" info color, active is in-progress/warning, closed
# is the success color, archived is neutral/secondary.
#
# Uses the raw (unprefixed) token names, not the --color-* Tailwind-utility
# aliases (--color-info etc) that @theme declares for `bg-info`/`text-info`
# class generation - those aliases are not guaranteed to exist as real,
# directly-`var()`-able custom properties under this app's dev-mode
# @tailwindcss/browser runtime compiler (confirmed empty via
# getComputedStyle in a real browser), while the underlying --info/
# --warning/--success/--secondary tokens they point to always resolve.
_CASE_STATUS_COLORS = {
    "open": "var(--info)",
    "active": "var(--warning)",
    "closed": "var(--success)",
    "archived": "var(--secondary)",
}


def _pie_slices(triples: list[tuple[str, float, str]]) -> list[dict]:
    """Turn (label, value, color) triples into pie_chart-ready slices - the
    one place conic-gradient start/end stops (0-100) get computed, so
    chart.html's pie_chart() macro only ever formats a CSS string, never
    does math. An all-zero total renders as a single flat muted ring
    instead of an empty/invalid gradient."""
    total = sum(value for _, value, _ in triples)
    if not total:
        return [{"label": "No data yet", "value": 0, "display": "0", "color": "var(--muted)", "start": 0, "end": 100}]

    slices = []
    cursor = 0.0
    for label, value, color in triples:
        pct = (value / total) * 100
        end = cursor + pct
        slices.append({
            "label": label,
            "value": value,
            "display": str(int(value)),
            "color": color,
            "start": round(cursor, 2),
            "end": round(end, 2),
        })
        cursor = end
    return slices


def _bars(pairs: list[tuple[str, float]], display_fmt) -> list[dict]:
    """Turn (label, value) pairs into bar_chart/hbar_chart-ready items -
    the one place `pct` (0-100, relative to the largest value in the set)
    gets computed, so chart.html's macros never touch raw numbers."""
    max_value = max((value for _, value in pairs), default=0)
    return [
        {
            "label": label,
            "value": value,
            "display": display_fmt(value),
            "pct": round((value / max_value) * 100, 1) if max_value else 0,
        }
        for label, value in pairs
    ]


def _bars_labeled(pairs: list[tuple[str, float]], display_fmt, *, min_pct: float = 14) -> list[dict]:
    """Like _bars(), but for bar_chart_labeled(), where the label renders
    inside the bar itself rather than beside it - a true zero/near-zero
    value still needs a visually non-empty bar for the label to sit on, so
    `bar_pct` is floored to `min_pct`. `display` always shows the real,
    unfloored value, so the floor is purely cosmetic - never misleading."""
    max_value = max((value for _, value in pairs), default=0)
    return [
        {
            "label": label,
            "value": value,
            "display": display_fmt(value),
            "bar_pct": max(round((value / max_value) * 100, 1), min_pct) if max_value else min_pct,
        }
        for label, value in pairs
    ]


def _line_series(pairs: list[tuple[str, float]], label_every: int = 5) -> dict:
    """Turn chronologically-ordered (label, value) pairs into line_chart-
    ready data: points as 0-100 x/y percentages (y inverted and padded so
    peaks/troughs never touch the SVG edge), a sparser set of x-axis labels
    - one every `label_every` points, since e.g. 90 daily labels would
    otherwise collide into unreadable text - and value_labels marking just
    the turning points (local peaks/troughs, plus both endpoints) with
    their actual number, so the reader can see real values without every
    single one of 90 points being individually labeled. x itself is inset
    to [2, 98] rather than the full [0, 100] so the first/last labels (and
    the line's endpoints) have room to render without clipping."""
    values = [v for _, v in pairs]
    n = len(pairs)
    max_value = max(values, default=0)
    min_value = min(values, default=0)
    span = (max_value - min_value) or 1

    points = []
    labels = []
    value_labels = []
    for i, (label, value) in enumerate(pairs):
        x = 2 + (i / (n - 1) * 96) if n > 1 else 50
        y = 95 - ((value - min_value) / span) * 90
        points.append({"x": round(x, 2), "y": round(y, 2)})
        if i % label_every == 0 or i == n - 1:
            labels.append({"x": round(x, 2), "text": label})

        is_endpoint = i == 0 or i == n - 1
        is_peak = 0 < i < n - 1 and value > values[i - 1] and value > values[i + 1]
        is_trough = 0 < i < n - 1 and value < values[i - 1] and value < values[i + 1]
        if is_endpoint or is_peak or is_trough:
            value_labels.append({"x": round(x, 2), "y": round(y, 2), "text": str(int(value))})

    return {
        "points": points,
        "labels": labels,
        "value_labels": value_labels,
        "total_display": str(int(sum(values))),
    }


def _radar_series(pairs: list[tuple[str, float]], *, rings: int = 4) -> dict:
    """Turn (label, value) pairs into radar_chart-ready data: a polygon
    grid (concentric rings + spokes) plus the data polygon/dots/outer
    labels, all in the same 0-100 coordinate space every other chart macro
    uses. Axes are placed clockwise starting at 12 o'clock (the
    conventional radar/spider chart layout) - one axis per pair, so
    callers should pass every category they want an axis for (including
    zero-value ones), not just the ones with a nonzero value."""
    cx = cy = 50.0
    r_max = 32.0
    n = len(pairs)
    max_value = max((v for _, v in pairs), default=0) or 1

    def polar(angle_deg: float, r: float) -> tuple[float, float]:
        angle = math.radians(angle_deg)
        return cx + r * math.cos(angle), cy + r * math.sin(angle)

    angles = [-90 + (360 / n) * i for i in range(n)] if n else []

    grid_rings = []
    for level in range(1, rings + 1):
        r = r_max * level / rings
        ring_points = [polar(a, r) for a in angles]
        grid_rings.append(" ".join(f"{x:.2f},{y:.2f}" for x, y in ring_points))

    spokes = []
    labels = []
    for (label, _value), angle in zip(pairs, angles):
        ex, ey = polar(angle, r_max)
        spokes.append({"x2": round(ex, 2), "y2": round(ey, 2)})
        lx, ly = polar(angle, r_max + 11)
        labels.append({"x": round(lx, 2), "y": round(ly, 2), "text": label})

    dots = []
    polygon_pts = []
    for (_label, value), angle in zip(pairs, angles):
        r = (value / max_value) * r_max
        x, y = polar(angle, r)
        polygon_pts.append(f"{x:.2f},{y:.2f}")
        dots.append({"x": round(x, 2), "y": round(y, 2), "display": str(int(value))})

    return {
        "cx": cx,
        "cy": cy,
        "grid_rings": grid_rings,
        "spokes": spokes,
        "polygon_points": " ".join(polygon_pts),
        "dots": dots,
        "labels": labels,
    }


_RADIAL_PALETTE = ["var(--info)", "var(--success)", "var(--warning)", "var(--secondary)", "var(--destructive)"]


def _radial_bars(pairs: list[tuple[str, float]]) -> list[dict]:
    """Turn (label, value) pairs into radial_chart-ready rings - one
    concentric ring per pair, innermost first, so callers should already
    have the pairs in the order they want rendered from the center out
    (e.g. Counter.most_common() - most popular gets the prominent inner
    ring). Each ring's arc length (as an SVG stroke-dasharray) is
    proportional to value against the shared max across ALL rings, not an
    independent 0-100% per ring, so length differences stay meaningful.
    fill/gap are precomputed dash lengths, not percentages, since the
    dasharray needs real units matching each ring's own circumference."""
    n = len(pairs)
    max_value = max((v for _, v in pairs), default=0) or 1
    inner, outer = 14.0, 42.0
    band = (outer - inner) / n if n else 0.0
    thickness = band * 0.62

    items = []
    for i, (label, value) in enumerate(pairs):
        r = inner + band * (i + 0.5)
        circumference = 2 * math.pi * r
        frac = min(max(value / max_value, 0.02), 0.985) if value > 0 else 0.0
        filled = circumference * frac
        items.append({
            "label": label,
            "display": str(int(value)),
            "radius": round(r, 2),
            "thickness": round(thickness, 2),
            "hit_thickness": round(thickness + 3, 2),
            "dash": round(filled, 2),
            "gap": round(circumference - filled, 2),
            "color": _RADIAL_PALETTE[i % len(_RADIAL_PALETTE)],
        })
    return items


def _last_n_months(n: int) -> list[tuple[int, int]]:
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month
    months = []
    for _ in range(n):
        months.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(months))


def _last_n_days(n: int):
    today = datetime.now(timezone.utc).date()
    return [today - timedelta(days=offset) for offset in range(n - 1, -1, -1)]


async def get_admin_dashboard() -> dict:
    """Platform-wide widgets for staff/System Admin: traffic, users,
    revenue, popular plan, popular modules, recent signups/transactions."""
    users_total = await repo.count_users()
    orgs = await repo.count_organizations()
    active_subs = await repo.count_active_subscriptions()

    transactions = await repo.list_completed_transaction_amounts()
    revenue_total = sum((t["total_amount"] for t in transactions), Decimal("0"))

    months = _last_n_months(6)
    month_totals = {ym: Decimal("0") for ym in months}
    for t in transactions:
        created = t["created_at"]
        key = (created.year, created.month)
        if key in month_totals:
            month_totals[key] += t["total_amount"]
    revenue_chart = _bars_labeled(
        [(datetime(y, m, 1).strftime("%B"), float(month_totals[(y, m)])) for y, m in months],
        lambda v: f"Rs.{v:,.0f}",
    )

    traffic_since = datetime.now(timezone.utc) - timedelta(days=89)
    sessions = await repo.list_session_created_dates(traffic_since)
    days = _last_n_days(90)
    day_counts = {d: 0 for d in days}
    for s in sessions:
        created_date = s["createdAt"].date()
        if created_date in day_counts:
            day_counts[created_date] += 1
    traffic_chart = _line_series([(d.strftime("%b %-d"), day_counts[d]) for d in days], label_every=5)

    module_rows = await repo.list_task_module_names()
    top_modules = Counter(row["module_name"] for row in module_rows).most_common(5)
    popular_modules = _radial_bars(top_modules)

    plan_rows = await repo.list_active_subscription_plan_ids()
    all_plans = await plans_repository.list_plans()
    plan_counts = Counter(row["plan_id"] for row in plan_rows)
    # Every plan gets a radar axis, including ones with zero active
    # subscriptions - a radar's whole point is comparing across a fixed set
    # of categories, so silently dropping an axis for "no data yet" would
    # make the shape misleading rather than just sparse.
    popular_plans = _radar_series([(p["display_name"], plan_counts.get(p["id"], 0)) for p in all_plans])

    recent_orgs = await repo.list_recent_organizations(5)
    recent_transactions = (await finance_repository.list_transactions())[:5]

    return {
        "stats": {
            "users_total": users_total,
            "orgs_total": orgs["total"],
            "orgs_pending": orgs["pending"],
            "revenue_total_display": f"Rs. {revenue_total:,.0f}",
            "active_subs": active_subs,
        },
        "revenue_chart": revenue_chart,
        "traffic_chart": traffic_chart,
        "popular_modules": popular_modules,
        "popular_plans": popular_plans,
        "recent_orgs": recent_orgs,
        "recent_transactions": recent_transactions,
    }


async def get_org_dashboard(user_id: str) -> dict | None:
    """Org-scoped widgets, shaped by the viewer's role: an owner (or anyone
    holding the matching org permission) sees organization-wide numbers and
    tables; everyone else sees the same widgets scoped to only what they're
    row-level allowed to see (see cases/service.py.can_access_case) - never
    a permission error, just a narrower version of the same dashboard.
    Returns None if the caller belongs to no organization at all."""
    membership = await get_user_org_membership(user_id)
    if not membership:
        return None

    org_id = membership["organization_id"]
    owner = is_org_owner(user_id, membership)
    granted = await get_user_org_permission_names(user_id)
    can_view_members = owner or ORG_STAFF_VIEW.name in granted
    can_view_billing = owner or ORG_BILLING_MANAGE.name in granted

    org = await org_repository.get_organization(org_id)

    role_label = "Owner"
    if not owner:
        role = await org_repository.get_org_role(membership["role_id"]) if membership["role_id"] else None
        role_label = role["name"] if role else "Member"

    cases = await cases_service.list_cases_for_user(org_id, user_id, is_owner=owner)
    status_counts = Counter(c["status"] for c in cases)
    open_count = status_counts.get("open", 0) + status_counts.get("active", 0)
    case_status_chart = _pie_slices(
        [(label, status_counts.get(key, 0), _CASE_STATUS_COLORS[key]) for key, label in _CASE_STATUSES]
    )

    members = None
    member_count = None
    if can_view_members:
        all_members = await org_repository.list_members(org_id)
        member_count = len(all_members)
        members = all_members[:8]

    sub = await plans_service.get_active_subscription(org_id)
    plan_name = (sub.get("plan_snapshot") or {}).get("display_name") if sub else None
    plan_status = sub.get("status") if sub else None

    subscription_history = None
    if can_view_billing:
        since = datetime.now(timezone.utc) - timedelta(days=93)
        subscription_history = await plans_repository.list_subscriptions_for_org(org_id, since=since)

    recent_activity = await audit_service.get_activity_log_for_cases([c["id"] for c in cases], limit=8)

    return {
        "org": org,
        "role_label": role_label,
        "is_owner": owner,
        "can_view_members": can_view_members,
        "can_view_billing": can_view_billing,
        "stats": {
            "case_total": len(cases),
            "case_scope_label": "Organization" if owner else "My",
            "open_count": open_count,
            "member_count": member_count,
            "plan_name": plan_name,
            "plan_status": plan_status,
        },
        "case_status_chart": case_status_chart,
        "members": members,
        "member_count": member_count,
        "subscription_history": subscription_history,
        "recent_activity": recent_activity,
    }
