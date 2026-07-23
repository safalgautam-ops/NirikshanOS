"""E2E test: a real browser session, driving the actual running app (nginx -> Flask, real MySQL/Redis/MinIO) rather than Flask's test client - login, then create a real case through the real dialog UI, and see it appear on the case list."""

import re

from playwright.sync_api import expect

BASE_URL = "http://localhost"


def test_login_then_create_a_case_end_to_end(page, e2e_user):
    page.goto(f"{BASE_URL}/auth/login")
    page.fill('input[name="email"]', e2e_user["email"])
    page.fill('input[name="password"]', e2e_user["password"])
    page.click('button[type="submit"]:has-text("Login")')
    expect(page).to_have_url(f"{BASE_URL}/dashboard", timeout=10_000)

    page.goto(f"{BASE_URL}/cases/")
    page.click('button:has-text("New Case")')
    dialog = page.locator("#create-case-dialog")
    expect(dialog).to_be_visible()

    case_title = f"E2E Playwright Case {e2e_user['user_id'][:8]}"
    page.fill("#case-title", case_title)
    page.click("[data-target='#select-popup-case-classification']")
    dialog.locator("#select-popup-case-classification [data-slot='select-item']").first.click()

    page.click('button[type="submit"]:has-text("Next: Upload evidence")')

    expect(page).to_have_url(re.compile(r"/cases/[a-f0-9]+\?created=1$"), timeout=10_000)
    expect(page.locator("body")).to_contain_text(case_title, timeout=10_000)

    page.goto(f"{BASE_URL}/cases/")
    expect(page.locator("body")).to_contain_text(case_title)
