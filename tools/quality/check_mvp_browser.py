"""Headless LOCAL-only UI smoke. Credentials are read directly into a masked browser field."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import expect, sync_playwright

from treasury_backend.paths import ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:18030")
    p.add_argument(
        "--credential-file", type=Path, default=ROOT / "data/mvp-browser/operator-access.txt"
    )
    p.add_argument("--output", type=Path, default=ROOT / "docs/audit/mvp-browser-check.json")
    args = p.parse_args()
    if urlsplit(args.url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("LOCAL_UI_ONLY")
    capability = httpx.get(args.url + "/mvp/capabilities", timeout=10).raise_for_status().json()
    if capability["environment"] != "LOCAL_TEST":
        raise ValueError("LOCAL_UI_ONLY")
    failures = []
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1360, "height": 980})
        page.on("pageerror", lambda error: failures.append(str(error)))
        page.goto(args.url, wait_until="networkidle")
        assert page.locator("h1").inner_text().startswith("Two operations.")
        assert page.locator("#kind option").all_text_contents() == ["SWAP_EXACT_IN", "USDC_PAYMENT"]
        page.locator("#credential").fill(args.credential_file.read_text(encoding="utf-8"))
        page.get_by_role("button", name="Connect system treasury", exact=True).click()
        expect(page.locator("#agent")).to_have_text("Manual",timeout=30000)
        page.get_by_role("button", name="AI Agent Console", exact=True).click()
        page.locator("#kind").select_option("USDC_PAYMENT")
        assert page.locator("#payee").locator("option").count() == 1
        assert page.locator("#route-label").is_hidden()
        page.locator("#amount").fill("1")
        page.locator("#objective").fill("Pay exactly 1 test USDC to the owner-approved system EOA")
        page.locator("#execute").click()
        expect(page.locator("#workflow-state")).to_contain_text("CONFIRMED",timeout=60000)
        assert "LOCAL_TEST" in page.locator("#timeline").inner_text()
        assert page.locator("#timeline a").count() == 0
        page.get_by_role("button", name="Security Center", exact=True).click()
        expect(page.locator("#gas-expenses")).to_contain_text("actual_cost_wei",timeout=30000)
        page.screenshot(path=str(args.output.with_suffix(".png")), full_page=True)
        page.get_by_role("button", name="Attack Lab", exact=True).click()
        assert page.locator("#attack-cases button").count() == 6
        page.get_by_role("button", name="Unauthorized payment", exact=True).click()
        expect(page.locator("#attack-result")).to_contain_text('"status": "PASS"',timeout=60000)
        page.get_by_role("button", name="Treasury Dashboard", exact=True).click()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.locator("main").bounding_box()["width"] <= 390
        browser.close()
    assert not failures, failures
    result = {
        "environment": "LOCAL_TEST",
        "status": "PASS",
        "public_writes": False,
        "checks": [
            "public chain status",
            "two operation choices",
            "operator login without private keys",
            "USDC receipt workflow",
            "timeline and no fake Fuji link",
            "proof/fee evidence",
            "isolated attack case",
            "mobile width",
        ],
        "semantic_scope": capability["semantic_evaluation_scope"],
        "browser": "headless Chromium",
        "in_app_browser_blocker": "Importing module node:process is not allowed in node_repl",
    }
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
