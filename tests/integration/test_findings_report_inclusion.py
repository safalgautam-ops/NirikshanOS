"""Integration tests: the included_in_report flag on case findings/indicators (migration 035, app/features/analysis/findings_repository.py)."""

from app.features.analysis import findings_service


def _make_finding(run_async, case_id, author_id):
    finding_id = run_async(
        findings_service.create_finding(
            case_id=case_id,
            evidence_id=None,
            module_id=None,
            author_id=author_id,
            title="Suspicious hash match",
            description="SHA256 matches a known-bad list.",
            severity="high",
            confidence="high",
        )
    )
    return finding_id


def _make_indicator(run_async, case_id, author_id):
    indicator_id = run_async(
        findings_service.create_indicator(
            case_id=case_id,
            evidence_id=None,
            module_id=None,
            author_id=author_id,
            ioc_type="hash",
            value="3a8c57b4204236535e86332d430d8baf87fd4e1fe0846291a961043227761880",
            severity="high",
            confidence="high",
        )
    )
    return indicator_id


def test_finding_included_flag_persists_after_marking(run_async, make_user, make_org):
    from app.features.cases.repository import create_case
    from app.features.organizations.repository import add_member as add_org_member

    author = make_user()
    org = make_org(created_by=author["id"])
    run_async(add_org_member(org["id"], author["id"]))
    case_id = run_async(
        create_case(
            organization_id=org["id"],
            title="Finding Inclusion Case",
            description="",
            classification="internal",
            severity="low",
            forensic_status="not_started",
            created_by=author["id"],
        )
    )

    finding_id = _make_finding(run_async, case_id, author["id"])

    before = run_async(findings_service.list_findings(case_id))
    assert before[0]["included_in_report"] == 0

    run_async(findings_service.mark_finding_included(case_id, finding_id))

    after = run_async(findings_service.list_findings(case_id))
    assert after[0]["included_in_report"] == 1


def test_indicator_included_flag_persists_after_marking(run_async, make_user, make_org):
    from app.features.cases.repository import create_case
    from app.features.organizations.repository import add_member as add_org_member

    author = make_user()
    org = make_org(created_by=author["id"])
    run_async(add_org_member(org["id"], author["id"]))
    case_id = run_async(
        create_case(
            organization_id=org["id"],
            title="Indicator Inclusion Case",
            description="",
            classification="internal",
            severity="low",
            forensic_status="not_started",
            created_by=author["id"],
        )
    )

    indicator_id = _make_indicator(run_async, case_id, author["id"])

    before = run_async(findings_service.list_indicators(case_id))
    assert before[0]["included_in_report"] == 0

    run_async(findings_service.mark_indicator_included(case_id, indicator_id))

    after = run_async(findings_service.list_indicators(case_id))
    assert after[0]["included_in_report"] == 1
