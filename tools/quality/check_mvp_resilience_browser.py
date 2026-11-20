"""LOCAL-only judged-web recovery check. One payment, lost response/reload, no public writes."""

import argparse
import json
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from treasury_backend.paths import ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:18035")
    p.add_argument("--credential-file", type=Path, default=ROOT / "data/mvp-resilience-browser/operator-access.txt")
    args = p.parse_args()
    if not args.url.startswith("http://127.0.0.1:"):
        raise ValueError("LOCAL_UI_ONLY")
    capabilities = httpx.get(args.url + "/mvp/capabilities", timeout=30).raise_for_status().json()
    if capabilities["environment"] != "LOCAL_TEST":
        raise ValueError("LOCAL_UI_ONLY")
    credential = args.credential_file.read_text().strip()
    headers = {"Authorization": "Bearer " + credential}
    endpoint = args.url + "/mvp/treasury/" + capabilities["default_session_id"]
    before = httpx.get(endpoint, headers=headers, timeout=30).raise_for_status().json()["context"]
    post_count = 0
    failures = []
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width":1360, "height":1000})
        page.on("pageerror", lambda error: failures.append(str(error)))

        def lose_response(route):
            nonlocal post_count
            if route.request.method != "POST":
                route.continue_()
                return
            post_count += 1
            route.fetch(timeout=90000)  # Execute the real local workflow once.
            route.abort("failed")      # Browser never sees its successful response.

        page.route("**/mvp/workflows", lose_response)
        page.goto(args.url, wait_until="networkidle")
        page.locator("#credential").fill(credential)
        page.get_by_role("button", name="Connect system treasury", exact=True).click()
        expect(page.locator("#agent")).to_have_text("Manual", timeout=30000)
        page.locator("#demo-payment").click()
        expect(page.locator("#amount")).to_have_value("0.01")
        page.locator("#execute").click()
        expect(page.locator("#error")).to_be_visible(timeout=90000)
        expect(page.locator("#resume-request")).to_be_enabled(timeout=90000)
        assert post_count == 1
        page.reload(wait_until="networkidle")
        expect(page.locator("#request-recovery")).to_be_visible()
        page.locator("#credential").fill(credential)
        page.get_by_role("button", name="Connect system treasury", exact=True).click()
        expect(page.locator("#workflow-state")).to_contain_text("CONFIRMED", timeout=30000)
        expect(page.locator("#request-recovery")).to_be_hidden()
        assert post_count == 1
        assert page.locator("#timeline a").count() == 0

        def stale_readiness(route):
            response = route.fetch()
            value = response.json()
            value["ready"] = False
            value["checks"] = [{"code":"ORACLE_REFRESH_REQUIRED", "ready":False, "action":"Wait for a new round"}]
            for operation in value["operations"]:
                operation.update(ready=False, reasons=["ORACLE_REFRESH_REQUIRED"])
            route.fulfill(response=response, json=value)

        def unpriced_dashboard(route):
            response = route.fetch()
            value = response.json()
            value["context"].update(nominal_prices=None, price_intervals=None, oracle_valid_until=0)
            route.fulfill(response=response, json=value)

        page.route("**/mvp/readiness", stale_readiness)
        page.route("**/mvp/treasury/*", unpriced_dashboard)
        page.locator("#refresh").click()
        expect(page.locator("#readiness-checks")).to_contain_text("ORACLE_REFRESH_REQUIRED", timeout=30000)
        expect(page.locator("#allocation")).to_contain_text("fresh oracle reference unavailable")
        expect(page.locator("#execute")).to_be_disabled()
        assert page.locator("#usdc").inner_text() != "—"
        page.get_by_role("button", name="Treasury Dashboard", exact=True).click()
        page.set_viewport_size({"width":390, "height":844})
        assert page.locator("main").bounding_box()["width"] <= 390
        page.screenshot(path=str(ROOT / "docs/audit/mvp-resilience-browser.png"), full_page=True)
        browser.close()
    after = httpx.get(endpoint, headers=headers, timeout=30).raise_for_status().json()["context"]
    assert int(before["balances"][0]) - int(after["balances"][0]) == 10000
    assert int(before["payment_spend_remaining_usdc"]) - int(after["payment_spend_remaining_usdc"]) == 10000
    assert not failures, failures
    result = {"status":"PASS", "environment":"LOCAL_TEST", "public_writes":False,
              "payment_posts":post_count, "actual_usdc_debit_units":"10000",
              "semantic_scope":capabilities["semantic_evaluation_scope"],
              "checks":["preset", "lost POST response", "reload and login", "same-key receipt recovery without resend",
                        "no duplicate payment", "unpriced balances visible", "stale oracle disables execution", "mobile layout"],
              "browser":"headless Chromium", "in_app_browser":"Unavailable during bootstrap"}
    (ROOT / "docs/audit/mvp-resilience-browser.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
