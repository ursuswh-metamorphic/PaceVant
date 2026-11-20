"""Browser acceptance for the built React UI, replay, layout and real API boundaries."""

import argparse
import json

from playwright.sync_api import expect, sync_playwright

from treasury_backend.paths import ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:18040")
    p.add_argument("--live", action="store_true")
    args = p.parse_args()
    if not args.url.startswith("http://127.0.0.1:"):
        raise ValueError("LOCAL_ACCEPTANCE_ONLY")
    output = ROOT / "docs/audit"
    errors = []
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width":1440,"height":900})
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto(args.url,wait_until="networkidle")
        expect(page.get_by_role("heading",name="Secure AI agent execution.")).to_be_visible()
        assert page.get_by_role("tab").count()==3
        expect(page.get_by_role("tabpanel",name="Live Demo")).to_be_visible()
        expect(page.get_by_test_id("scenario-payment")).to_be_visible()
        expect(page.get_by_test_id("scenario-swap")).to_be_visible()
        expect(page.get_by_test_id("scenario-guard")).to_be_visible()
        page.screenshot(path=str(output/"judge-desktop-1440.png"),full_page=True)
        page.set_viewport_size({"width":1920,"height":1080})
        page.screenshot(path=str(output/"judge-desktop-1920.png"),full_page=True)
        page.get_by_test_id("view-replay").click()
        expect(page.get_by_test_id("execution-result")).to_contain_text("Recorded fork confirmation",timeout=15000)
        assert page.locator('a[href*="snowtrace.io"]').count()==0
        page.get_by_role("button",name="View evidence",exact=True).click()
        expect(page.get_by_role("dialog")).to_be_visible()
        expect(page.get_by_role("heading",name="Workflow evidence")).to_be_visible()
        page.get_by_role("button",name="Close details").click()
        page.get_by_test_id("tab-security").click()
        expect(page.get_by_test_id("security-panel")).to_be_visible()
        expect(page.get_by_role("tabpanel",name="Security & Policies")).to_be_visible()
        page.get_by_role("button",name="Z3 formal verification & signed Phi").click()
        expect(page.get_by_text("Off-chain Z3 verification",exact=True)).to_be_visible()
        page.get_by_test_id("tab-history").click()
        expect(page.get_by_test_id("history-panel")).to_be_visible()
        page.get_by_test_id("tab-live").click()
        page.get_by_role("button",name="Select Unsafe Transaction Rejected").click()
        page.get_by_test_id("view-replay").click()
        expect(page.get_by_test_id("execution-result")).to_contain_text("Rejected by security policy")
        expect(page.get_by_test_id("reason-code")).to_have_text("LFJ_UNSUPPORTED_ROUTE")
        page.get_by_role("button",name="Select Secure USDC Payment").click()
        page.get_by_test_id("view-replay").click()
        expect(page.get_by_test_id("execution-result")).to_contain_text("Recorded fork confirmation")
        page.set_viewport_size({"width":390,"height":844})
        assert page.locator('body').evaluate('(el)=>el.scrollWidth')<=390
        page.screenshot(path=str(output/"judge-mobile.png"),full_page=True)
        page.emulate_media(reduced_motion="reduce")
        page.get_by_test_id("tab-security").click()
        expect(page.get_by_test_id("security-panel")).to_be_visible()
        if args.live:
            page.set_viewport_size({"width":1440,"height":900})
            page.get_by_test_id("tab-live").click()
            posts = []

            def lose_initial_ack(route):
                if route.request.method == "POST":
                    posts.append(route.request.post_data)
                    route.fetch()
                    route.abort("failed")
                else:
                    route.continue_()

            page.route("**/judge/jobs", lose_initial_ack)
            page.get_by_test_id("run-payment").click()
            expect(page.get_by_role("alert")).to_be_visible(timeout=30000)
            page.reload(wait_until="networkidle")
            expect(page.get_by_test_id("execution-result")).to_contain_text("Fork execution confirmed",timeout=300000)
            assert len(posts) == 1
            assert page.locator('a[href*="snowtrace.io"]').count()==0
            page.get_by_test_id("tab-history").click()
            expect(page.get_by_text("CONFIRMED",exact=True).first).to_be_visible()
        browser.close()
    assert not errors,errors
    result={"status":"PASS","built_frontend":True,"checks":["three tabs","1440x900","1920x1080","mobile width","replay evidence drawer","no fork explorer link","policy and solver details","reduced motion"],"live_payment_from_browser":args.live,"lost_response_reload_no_duplicate":args.live,"browser":"headless Chromium"}
    (output/"judge-frontend-check.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
