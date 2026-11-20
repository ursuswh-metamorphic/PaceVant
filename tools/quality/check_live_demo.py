"""Exercise the real web demo. Read-only/on-chain-free unless --broadcast is explicit."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright


async def check(args):
    report = {"source": "CHROMIUM_WEB_UI", "url": args.url,
              "broadcast_requested": args.broadcast, "cases": [], "browser_errors": []}
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1080})
        page.on("pageerror", lambda error: report["browser_errors"].append(str(error)))
        await page.goto(args.url, wait_until="networkidle")
        await page.locator("#demo-select-form button").click()
        await page.locator("#demo-budget").wait_for(state="visible", timeout=120000)
        report["wallet"] = await page.locator("#demo-wallet").inner_text()
        report["credit_before"] = await page.locator("#demo-credit").inner_text()
        await page.locator("#demo-activity").select_option("security")
        cases = [("limit", None), ("session", None), ("auth", None), ("contract", None)]
        if args.include_ai:
            cases.extend(("injection", c) for c in ("recipient_redirect", "policy_override", "forged_user"))
        for kind, challenge in cases:
            await page.locator("#live-case").select_option(kind)
            if challenge:
                await page.locator("#shield-challenge").select_option(challenge)
            await page.locator("#run").click()
            end = time.monotonic() + 150
            while time.monotonic() < end:
                raw = await page.locator("#live-check-result").text_content()
                if raw and raw.startswith("{"):
                    value = json.loads(raw)
                    break
                if await page.locator("#run").is_enabled():
                    raise RuntimeError(await page.locator("#live-check-summary").inner_text())
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Security check timed out: " + kind)
            item = {"case": kind, "challenge": challenge, "result": value,
                    "visible_summary": await page.locator("#live-check-summary").inner_text()}
            report["cases"].append(item)
            print(json.dumps({"case": kind, "challenge": challenge,
                              "passed": value.get("all_passed", not value.get("reason_codes"))}), flush=True)
            if value.get("all_passed") is False or value.get("reason_codes"):
                raise RuntimeError("Check did not pass; inspect actual evidence: " + kind)
        if args.broadcast:
            await page.locator("#demo-activity").select_option("normal")
            await page.locator("#live-goal").fill("Buy WAVAX with 0.000001 USDC")
            await page.locator("#run").click()
            end = time.monotonic() + 720
            while time.monotonic() < end:
                await asyncio.sleep(4)
                state = await page.locator("#workflow-status").inner_text()
                if state in {"CONFIRMED", "REVERTED", "REJECTED", "ESCALATED", "FAILED_TO_SUBMIT", "EXPIRED", "Lỗi"}:
                    break
            report["swap"] = {"workflow": await page.locator("#workflow-id").inner_text(),
                              "status": state}
            if state != "CONFIRMED":
                raise RuntimeError("Swap did not confirm; use same request ID to inspect, never auto retry")
        await page.locator("#demo-refresh").click()
        await page.wait_for_timeout(4000)
        report["credit_after"] = await page.locator("#demo-credit").inner_text()
        report["last_fee"] = await page.locator("#demo-last-fee").inner_text()
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(args.screenshot), full_page=True)
        await browser.close()
    report["status"] = "PASS" if not report["browser_errors"] else "FAIL"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--include-ai", action="store_true", help="Call real Shield models for three fixed challenges")
    parser.add_argument("--broadcast", action="store_true", help="Send ONE tiny Fuji swap through the UI, with real gas")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    report = asyncio.run(check(args))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]),
                      "broadcast_requested": args.broadcast, "browser_errors": report["browser_errors"]}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
