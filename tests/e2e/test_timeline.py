"""E2E test: the per-case manual investigation timeline, through a real browser against the actual running app."""

import re

from playwright.sync_api import expect

BASE_URL = "http://localhost"


def _login_and_create_case(page, e2e_user, title):
    page.goto(f"{BASE_URL}/auth/login")
    page.fill('input[name="email"]', e2e_user["email"])
    page.fill('input[name="password"]', e2e_user["password"])
    page.click('button[type="submit"]:has-text("Login")')
    expect(page).to_have_url(f"{BASE_URL}/dashboard", timeout=10_000)

    page.goto(f"{BASE_URL}/cases/")
    page.click('button:has-text("New Case")')
    dialog = page.locator("#create-case-dialog")
    expect(dialog).to_be_visible()
    page.fill("#case-title", title)
    page.click("[data-target='#select-popup-case-classification']")
    dialog.locator("#select-popup-case-classification [data-slot='select-item']").first.click()
    page.click('button[type="submit"]:has-text("Next: Upload evidence")')
    expect(page).to_have_url(re.compile(r"/cases/[a-f0-9]+\?created=1$"), timeout=10_000)
    return re.search(r"/cases/([a-f0-9]+)", page.url).group(1)


def test_add_task_note_and_milestone_on_a_real_case_timeline(page, e2e_user):
    case_title = f"E2E Timeline Case {e2e_user['user_id'][:8]}"
    case_id = _login_and_create_case(page, e2e_user, case_title)

    page.goto(f"{BASE_URL}/cases/{case_id}/timeline")
    expect(page.locator("body")).to_contain_text(case_title, timeout=10_000)

    expect(page.locator("[data-target='#add-task-dialog']")).to_be_visible()
    expect(page.locator("[data-target='#add-note-dialog']")).to_be_visible()
    expect(page.locator("[data-target='#add-milestone-dialog']")).to_be_visible()

    page.click("[data-target='#add-task-dialog']")
    page.fill("#task-title", "Isolate infected host")
    page.click("#add-task-dialog button[type=submit]:has-text('Create')")
    expect(page.locator("body")).to_contain_text("Isolate infected host", timeout=10_000)

    page.click("[data-target='#add-note-dialog']")
    page.fill("#note-title", "Client notified")
    page.fill("#note-body", "Called the client to report the incident.")
    page.click("#add-note-dialog button[type=submit]:has-text('Create')")
    expect(page.locator("body")).to_contain_text("Client notified", timeout=10_000)

    page.click("[data-target='#add-milestone-dialog']")
    page.fill("#milestone-title", "Containment complete")
    page.click("#add-milestone-dialog button[type=submit]:has-text('Create')")
    expect(page.locator("body")).to_contain_text("Containment complete", timeout=10_000)

    page.click("[data-edit-timeline-item]")
    expect(page.locator("#edit-timeline-item-title")).not_to_have_value("", timeout=5_000)
