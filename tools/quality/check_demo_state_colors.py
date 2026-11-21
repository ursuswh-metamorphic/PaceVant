"""Render saved live evidence to verify semantic colors without creating any jobs.

The target serves the real frontend. Only read-only /judge responses are supplied
from recorded acceptance evidence; these screenshots are UI regression renders.
"""

import argparse
import asyncio
import json
from pathlib import Path

import httpx
from playwright.async_api import async_playwright


async def check(args):
    recorded = json.loads(args.report.read_text())
    jobs = [entry["job"] for entry in recorded["cases"] + recorded["normal"]]
    config = httpx.get("https://pacevant.live/judge/config", timeout=30).raise_for_status().json()
    config.update(busy=False, configured=True)
    config["quota"]["remaining_today"] = 1
    results = {"source": "SAVED_LIVE_EVIDENCE_UI_REGRESSION", "url": args.url, "renders": [], "browser_errors": []}
    args.output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch(headless=True)
        for job in jobs:
            context = await browser.new_context(viewport={"width": 1440, "height": 1080})
            await context.add_init_script("sessionStorage.setItem('pacevant.judge.view.v1', "+json.dumps(json.dumps({"job_id": job["job_id"], "scenario": job["scenario"]}))+" );")
            page = await context.new_page()
            page.on("pageerror", lambda error: results["browser_errors"].append(str(error)))

            async def serve(route, observed_job=job):
                path = route.request.url.split("/judge/", 1)[-1]
                if route.request.method != "GET":
                    raise RuntimeError("UI color verification must never create jobs")
                value = config if path == "config" else {"jobs": jobs} if path == "history" else observed_job if path.startswith("jobs/") else {"status": "UNAVAILABLE"}
                await route.fulfill(status=200, content_type="application/json", body=json.dumps(value))
            await page.route("**/judge/**", serve)
            await page.goto(args.url, wait_until="networkidle")
            await page.get_by_test_id("node-9").wait_for(timeout=20000)
            name = job.get("attack") or job["scenario"]
            if job.get("attack"):
                target, expected = 9, "rejected"
                await page.get_by_test_id("attack-scope").wait_for()
            elif job["status"] == "CONFIRMED":
                target, expected = 11, "passed"
            else:
                target, expected = 3, "unknown"
            node = page.get_by_test_id("node-"+str(target))
            classes = await node.get_attribute("class")
            assert "state-"+expected in classes, (name, classes, expected)
            color = await node.locator(".node-badge").evaluate("element => getComputedStyle(element).backgroundColor")
            expected_color = {"rejected": "rgb(192, 38, 58)", "passed": "rgb(14, 164, 126)", "unknown": "rgb(253, 243, 225)"}[expected]
            assert color == expected_color, (name, color, expected_color)
            await page.screenshot(path=str(args.output/(name+"-desktop.png")), full_page=True)
            await node.click()
            await page.get_by_role("dialog").wait_for()
            assert "tone-"+expected in (await page.get_by_role("dialog").locator(".chip").first.get_attribute("class")), name
            await page.keyboard.press("Escape")
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.screenshot(path=str(args.output/(name+"-mobile.png")), full_page=True)
            overflow = await page.evaluate("document.documentElement.scrollWidth > innerWidth")
            assert not overflow, name
            results["renders"].append({"case": name, "job_id": job["job_id"], "node": target,
                "state": expected, "badge_background": color, "mobile_overflow": overflow})
            await context.close()
        await browser.close()
    results["status"] = "PASS" if not results["browser_errors"] else "FAIL"
    (args.output/"colors.json").write_text(json.dumps(results, indent=2)+"\n", encoding="utf-8")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18111")
    parser.add_argument("--report", type=Path, default=Path("docs/audit/live-adversarial-20261121/report.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/audit/live-adversarial-20261121/colors-local"))
    result = asyncio.run(check(parser.parse_args()))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
