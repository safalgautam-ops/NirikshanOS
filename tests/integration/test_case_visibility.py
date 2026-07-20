"""Integration tests: row-level case visibility
(app/features/cases/repository.py::list_member_cases - referenced directly
in report §3.2, §4.2, Appendix E1). Exercises the real function against a
real test database with two distinct org members.
"""
from app.features.cases.repository import add_member, create_case, list_member_cases
from app.features.organizations.repository import add_member as add_org_member


def _make_case(run_async, org_id, creator_id):
    return run_async(
        create_case(
            organization_id=org_id,
            title="Test Case",
            description="",
            classification="internal",
            severity="low",
            forensic_status="not_started",
            created_by=creator_id,
        )
    )


def test_creator_sees_their_own_case(run_async, make_user, make_org):
    creator = make_user()
    org = make_org(created_by=creator["id"])
    run_async(add_org_member(org["id"], creator["id"]))

    case_id = _make_case(run_async, org["id"], creator["id"])

    visible = run_async(list_member_cases(org["id"], creator["id"]))
    assert case_id in {c["id"] for c in visible}


def test_other_member_does_not_see_a_case_they_were_not_added_to(run_async, make_user, make_org):
    creator = make_user()
    outsider = make_user()
    org = make_org(created_by=creator["id"])
    run_async(add_org_member(org["id"], creator["id"]))
    run_async(add_org_member(org["id"], outsider["id"]))

    _make_case(run_async, org["id"], creator["id"])

    visible = run_async(list_member_cases(org["id"], outsider["id"]))
    assert visible == []


def test_member_explicitly_added_to_a_case_can_see_it(run_async, make_user, make_org):
    creator = make_user()
    added_member = make_user()
    org = make_org(created_by=creator["id"])
    run_async(add_org_member(org["id"], creator["id"]))
    run_async(add_org_member(org["id"], added_member["id"]))

    case_id = _make_case(run_async, org["id"], creator["id"])
    run_async(add_member(case_id, added_member["id"], added_by=creator["id"]))

    visible = run_async(list_member_cases(org["id"], added_member["id"]))
    assert case_id in {c["id"] for c in visible}


def test_two_members_of_the_same_org_see_different_case_lists(run_async, make_user, make_org):
    """The exact claim in report §4.2: two members of the same organisation
    see different case lists by default."""
    creator = make_user()
    member_a = make_user()
    member_b = make_user()
    org = make_org(created_by=creator["id"])
    for u in (creator, member_a, member_b):
        run_async(add_org_member(org["id"], u["id"]))

    case_shared = _make_case(run_async, org["id"], creator["id"])
    run_async(add_member(case_shared, member_a["id"], added_by=creator["id"]))
    # member_b is never added to this case.

    a_sees = {c["id"] for c in run_async(list_member_cases(org["id"], member_a["id"]))}
    b_sees = {c["id"] for c in run_async(list_member_cases(org["id"], member_b["id"]))}

    assert case_shared in a_sees
    assert case_shared not in b_sees
