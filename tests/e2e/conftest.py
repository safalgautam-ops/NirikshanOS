"""E2E fixtures."""

import json
import subprocess

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost"


@pytest.fixture(scope="session", autouse=True)
def _clear_real_login_rate_limit():
    """The E2E tier logs in through the real app, over the real network - nginx proxies every request through one fixed container IP, so every E2E login attempt (across every run of this suite) shares the exact same rate-limit key on the real dev Redis."""
    keys_result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "redis",
            "redis-cli",
            "-n",
            "0",
            "--scan",
            "--pattern",
            "rate:login:*",
        ],
        cwd="/home/deadeye/Music/NirikshanOS",
        capture_output=True,
        text=True,
    )
    for key in keys_result.stdout.strip().splitlines():
        if key:
            subprocess.run(
                ["docker", "compose", "exec", "-T", "redis", "redis-cli", "-n", "0", "DEL", key],
                cwd="/home/deadeye/Music/NirikshanOS",
                capture_output=True,
                text=True,
            )
    yield


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def page(browser):
    context = browser.new_context()
    pg = context.new_page()
    yield pg
    context.close()


@pytest.fixture(scope="session")
def e2e_user():
    """Provisions a real, verified user + approved org in the live dev database by running provision_e2e_user.py inside the web container - see that file for why the email-OTP step is skipped."""
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "web", "python3", "tests/e2e/provision_e2e_user.py"],
        cwd="/home/deadeye/Music/NirikshanOS",
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])
