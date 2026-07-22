"""E2E test: a real browser session, driving the actual running app
(nginx -> Flask, real MySQL/Redis/MinIO) rather than Flask's test client -
login, then create a real case through the real dialog UI, and see it
appear on the case list. Covers the "cases & evidence management" part of
the report's chosen slice end to end, at the UI layer, not just the route.
"""
import re

from playwright.sync_api import expect

BASE_URL = "http://localhost"


def test_login_then_create_a_case_end_to_end(page, e2e_user):
    # --- Login ---
    page.goto(f"{BASE_URL}/auth/login")
    page.fill('input[name="email"]', e2e_user["email"])
    page.fill('input[name="password"]', e2e_user["password"])
    page.click('button[type="submit"]:has-text("Login")')
    expect(page).to_have_url(f"{BASE_URL}/dashboard", timeout=10_000)

    # --- Open the case list and the "New Case" dialog ---
    page.goto(f"{BASE_URL}/cases/")
    page.click('button:has-text("New Case")')
    dialog = page.locator("#create-case-dialog")
    expect(dialog).to_be_visible()

    # --- Fill the form: title + classification (severity/forensic_status
    # already default to "medium"/"not_started" in the template) ---
    case_title = f"E2E Playwright Case {e2e_user['user_id'][:8]}"
    page.fill("#case-title", case_title)
    # The classification field is this app's custom listbox component (a
    # hidden <input> driven by a JS-only trigger+popup, not a native
    # <select>). A real click through the trigger+popup, not a scripted
    # value assignment: a native <dialog> opened with showModal() promotes
    # itself to the browser's top layer, and position:fixed elements inside
    # it (like this popup) used to be positioned relative to the dialog's
    # own box instead of the viewport - a real bug that made the popup land
    # partly outside the dialog's clipped bounds and unclickable. Fixed in
    # app.js's positionSelect(); this click is the regression guard for it.
    page.click("[data-target='#select-popup-case-classification']")
    dialog.locator("#select-popup-case-classification [data-slot='select-item']").first.click()

    page.click('button[type="submit"]:has-text("Next: Upload evidence")')

    # --- The route redirects to the new case's detail page on success ---
    expect(page).to_have_url(re.compile(r"/cases/[a-f0-9]+\?created=1$"), timeout=10_000)
    expect(page.locator("body")).to_contain_text(case_title, timeout=10_000)

    # --- And it now shows up back on the case list too ---
    page.goto(f"{BASE_URL}/cases/")
    expect(page.locator("body")).to_contain_text(case_title)
