"""Integration tests: saving a case note or report draft writes a matching
audit log entry (app/features/audit/service.py's REPORT_SAVED/NOTE_SAVED).

Regression guard for a real bug: neither route used to call the audit
logger at all, so the case detail page's Activity tab never reflected a
note or report save, even though every other case mutation (creation,
evidence, members, timeline items) already did.
"""
from app.features.audit import service as audit_service
from app.features.cases.repository import create_case
from app.features.organizations.repository import add_member as add_org_member

from tests.helpers import get_csrf, login_as


def _make_case(run_async, make_user, make_org):
    user = make_user()
    org = make_org(created_by=user["id"])
    run_async(add_org_member(org["id"], user["id"]))
    case_id = run_async(create_case(
        organization_id=org["id"], title="Activity Log Case", description="",
        classification="internal", severity="low", forensic_status="not_started",
        created_by=user["id"],
    ))
    return user, case_id


def test_saving_a_note_writes_a_note_saved_audit_entry(client, make_user, make_org, run_async):
    user, case_id = _make_case(run_async, make_user, make_org)
    login_as(client, user)

    csrf = get_csrf(client, f"/cases/{case_id}")
    resp = client.put(
        f"/cases/{case_id}/note",
        json={"content": "Scratchpad entry about the incident."},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200

    log = run_async(audit_service.get_case_activity_log(case_id))
    actions = [entry["action"] for entry in log]
    assert "Note saved" in actions


def test_saving_a_report_writes_a_report_saved_audit_entry(client, make_user, make_org, run_async):
    user, case_id = _make_case(run_async, make_user, make_org)
    login_as(client, user)

    csrf = get_csrf(client, f"/cases/{case_id}")
    resp = client.put(
        f"/cases/{case_id}/report",
        json={"title": "Investigation Report", "content": "# Executive Summary\n\nDraft."},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200

    log = run_async(audit_service.get_case_activity_log(case_id))
    actions = [entry["action"] for entry in log]
    assert "Report saved" in actions
