"""Drive all four public security cases through Chromium, optionally two real sends.

No arbitrary calldata, private keys or credentials. Every UI request retains its
original job identity. A normal send with an unknown result is never retried.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright


async def check(args):
    report = {"url": args.url, "source": "CHROMIUM_LIVE_UI", "cases": [], "normal": [], "browser_errors": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")

    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        page = await context.new_page()
        page.on("pageerror", lambda error: report["browser_errors"].append(str(error)))
        await page.goto(args.url, wait_until="networkidle")
        await page.get_by_test_id("tab-live").click()

        async def run(scenario, label, attack=None):
            await page.get_by_test_id("scenario-"+scenario).click()
            await page.get_by_role("combobox").click()
            options = await page.get_by_role("option").all_text_contents()
            if len(options) != 3:
                raise RuntimeError("Expected standard transaction plus exactly two security cases")
            await page.get_by_role("option", name=label, exact=True).click()
            async with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/judge/jobs"), timeout=45000) as response_info:
                await page.get_by_test_id("run-scenario").click(timeout=45000)
            response = await response_info.value
            value = await response.json()
            if response.status != 202:
                raise RuntimeError("UI request rejected: "+str(value.get("error", {}).get("code")))
            job_id = value["job_id"]
            print(json.dumps({"started": attack or scenario, "job_id": job_id}), flush=True)
            end = time.monotonic()+960
            while time.monotonic() < end:
                observed = await context.request.get(args.url.rstrip("/")+"/judge/jobs/"+job_id)
                value = await observed.json()
                if value.get("terminal"):
                    break
                await asyncio.sleep(2)
            else:
                raise RuntimeError("Unresolved original job: "+job_id)
            if attack:
                evidence = value.get("attack_evidence", {})
                passed = (value.get("status") == "REJECTED" and value.get("attack") == attack
                    and evidence.get("control") == "SUCCESS" and evidence.get("observed_selector") == evidence.get("expected_selector")
                    and evidence.get("broadcast") is False and value.get("public_chain_broadcast") is False)
                report["cases"].append({"attack": attack, "passed": passed, "options": options, "job": value})
                await page.get_by_test_id("attack-evidence").wait_for(timeout=20000)
            else:
                outcome = (value.get("workflow") or {}).get("outcome") or {}
                passed = value.get("status") == "CONFIRMED" and value.get("public_chain_broadcast") is True and outcome.get("public_chain_receipt") is True
                report["normal"].append({"scenario": scenario, "passed": passed, "job": value})
            save()
            print(json.dumps({"case": attack or scenario, "passed": passed, "status": value.get("status"), "reason": value.get("reason_code")}), flush=True)
            await page.screenshot(path=str(args.output.parent/((attack or scenario)+".png")), full_page=True)
            # Reload must restore exactly the same record, never create another job.
            await page.reload(wait_until="networkidle")
            await page.get_by_test_id("run-session").wait_for(timeout=20000)
            restored = await context.request.get(args.url.rstrip("/")+"/judge/jobs/"+job_id)
            if (await restored.json()).get("job_id") != job_id:
                raise RuntimeError("Reload lost the original job")
            return passed

        try:
            for scenario, attack, label in (
                ("payment", "payment-amount", "Nâng số tiền thanh toán"),
                ("payment", "payment-replay", "Phát lại giao dịch đã ký"),
                ("swap", "swap-slippage", "Hạ đầu ra tối thiểu"),
                ("swap", "swap-route", "Thay router ngoài phạm vi"),
            ):
                if not await run(scenario, label, attack):
                    raise RuntimeError("Security case did not pass: "+attack)
            if args.broadcast:
                for scenario in ("payment", "swap"):
                    await run(scenario, "Không thêm tấn công")
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.screenshot(path=str(args.output.parent/"mobile.png"), full_page=True)
            report["mobile_overflow"] = await page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            report["status"] = "PASS" if not report["browser_errors"] and not report["mobile_overflow"] and all(x["passed"] for x in report["cases"]+report["normal"]) else "FAIL"
        except Exception as error:
            report.update(status="FAIL", failure=str(error))
            raise
        finally:
            save()
            await browser.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://pacevant.live")
    parser.add_argument("--broadcast", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("docs/audit/live-adversarial-20261121/report.json"))
    args = parser.parse_args()
    report = asyncio.run(check(args))
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]), "normal": len(report["normal"])}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
