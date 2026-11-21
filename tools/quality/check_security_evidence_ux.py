"""Verify the production frontend build using recorded/read-only HTTP responses.

Run a local static server first. This tool rejects non-GET judge requests and
never contacts a live backend, RPC, signing service or model provider.
"""
import argparse
import asyncio
import copy
import hashlib
import json
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]


async def check(args):
    acceptance = json.loads((ROOT / 'docs/audit/live-adversarial-20261121/acceptance.json').read_text(encoding='utf-8'))
    jobs = [entry['job'] for entry in acceptance['cases'] + acceptance['normal']]
    research = json.loads((ROOT / 'frontend/public/evidence/security-research.json').read_text(encoding='utf-8'))
    config = {'enabled': True, 'configured': True, 'busy': False, 'mode': 'REAL_FUJI_EXECUTION',
              'scenarios': [entry['job']['request'] for entry in acceptance['normal']],
              'quota': {'remaining_today': 1, 'daily_limit': 6, 'global_daily_limit': 30},
              'limits': {'timeout_seconds': 900, 'max_concurrent': 1},
              'replay_available': [], 'semantic_scope': 'UI_REGRESSION_RECORDED_RESPONSES',
              'operator': {'enabled': False, 'reason': 'READ_ONLY_QA'}}
    result = {'scope': 'LOCAL_BROWSER_RECORDED_RESPONSES; NOT NEW EXECUTIONS',
              'frontend_index_sha256': hashlib.sha256((ROOT / 'frontend/dist/index.html').read_bytes()).hexdigest(),
              'research_sha256': hashlib.sha256((ROOT / 'frontend/public/evidence/security-research.json').read_bytes()).hexdigest(),
              'status': 'RUNNING', 'renders': [], 'checks': [], 'browser_errors': [], 'writes': []}
    args.output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch(headless=True)

        async def context_for(job, language='en', attempt=None):
            context = await browser.new_context(viewport={'width': 1440, 'height': 1080}, reduced_motion='reduce')
            await context.add_init_script('localStorage.setItem("pacevant.language", '+json.dumps(language)+'); sessionStorage.setItem("pacevant.judge.view.v1", '+json.dumps(json.dumps({'job_id': job['job_id'], 'scenario': job['scenario']}))+');')
            if attempt:
                await context.add_init_script('sessionStorage.setItem("pacevant.judge.attempt.v1", '+json.dumps(json.dumps(attempt))+');')
            page = await context.new_page()
            page.on('pageerror', lambda error: result['browser_errors'].append(str(error)))

            recovered_reads = 0

            async def serve(route, request):
                nonlocal recovered_reads
                if request.method != 'GET':
                    result['writes'].append(request.method + ' ' + request.url)
                    await route.abort()
                    return
                path = request.url.split('/judge/')[-1]
                if path.startswith('requests/'):
                    recovered_reads += 1
                    assert attempt and path == 'requests/' + attempt['key'], 'Recovery changed the request identity'
                    if recovered_reads == 1:
                        await route.fulfill(status=503, content_type='application/json', body=json.dumps({'error': {'code': 'JUDGE_DEPENDENCY_UNAVAILABLE'}}))
                        return
                value = config if path == 'config' else {'jobs': jobs} if path == 'history' else job if path.startswith(('jobs/', 'requests/')) else {'status': 'UNAVAILABLE', 'reason_code': 'READ_ONLY_QA'}
                await route.fulfill(status=200, content_type='application/json', body=json.dumps(value))
            await page.route('**/judge/**', serve)
            await page.goto(args.url, wait_until='networkidle')
            await page.get_by_test_id('status-panel').wait_for()
            return context, page

        async def no_overflow(page):
            assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth'), 'Page overflow'
            assert not await page.locator('.main-nav button').evaluate_all('(buttons) => buttons.some(el => el.scrollWidth > el.clientWidth)'), 'Navigation label overflow'
            if await page.get_by_role('dialog').count() and await page.get_by_role('dialog').evaluate('(el) => el.scrollWidth > el.clientWidth'):
                await page.screenshot(path=str(args.output / 'overflow-debug.png'))
                overflow = await page.get_by_role('dialog').evaluate('(el) => [...el.querySelectorAll("*")].filter(n => n.getBoundingClientRect().right > el.getBoundingClientRect().right).map(n => ({tag:n.tagName,class:n.className,width:n.scrollWidth})).slice(0,12)')
                raise AssertionError('Dialog overflow: ' + json.dumps(overflow))

        for job in jobs:
            context, page = await context_for(job)
            name = job.get('attack') or job['scenario']
            historical = bool(job.get('attack'))
            target = 9 if historical else 11
            expected = 'rejected' if historical else 'passed'
            await page.get_by_test_id(f'node-{target}').wait_for()
            assert f'state-{expected}' in await page.get_by_test_id(f'node-{target}').get_attribute('class')
            scope = page.get_by_test_id('status-panel').get_by_test_id('evidence-scope')
            assert await scope.inner_text() == ('HISTORICAL FUJI ETH_CALL' if historical else 'PUBLIC FUJI EXECUTION')
            if historical:
                assert await page.get_by_test_id('probe-details').inner_text()
                await page.get_by_test_id('probe-details').get_by_text('3. Expected and observed revert').click()
                assert job['attack_evidence']['observed_selector'] in await page.get_by_test_id('probe-details').inner_text()
            else:
                expense = job['workflow']['outcome'].get('system_gas_expense') or {}
                paid = expense.get('actual_cost_wei')
                exact = 'Unavailable' if paid is None else f'{int(paid) // 10**18}.{int(paid) % 10**18:018d}'.rstrip('0').rstrip('.') + ' AVAX'
                assert exact in await page.get_by_test_id('status-panel').inner_text()
            await no_overflow(page)
            if name in ['payment', 'payment-amount']:
                await page.screenshot(path=str(args.output / f'{name}-desktop-en.png'), full_page=True)
            gate = page.get_by_role('button', name='Inspect gate and evidence')
            await gate.focus()
            await page.keyboard.press('Enter')
            await page.get_by_role('dialog').wait_for()
            assert await page.get_by_role('dialog').locator('[data-module]').get_attribute('data-module') == str(target)
            await no_overflow(page)
            if name in ['payment', 'payment-amount']:
                await page.screenshot(path=str(args.output / f'{name}-gate-en.png'))
            await page.keyboard.press('Escape')
            await page.get_by_test_id('open-evidence').click()
            await page.get_by_role('dialog').wait_for()
            assert await page.get_by_role('dialog').get_by_test_id('evidence-scope').inner_text() == await scope.inner_text()
            assert await page.get_by_role('dialog').locator('.security-chain li').count() == 6
            await page.keyboard.press('Escape')
            for language in ['en', 'vi']:
                await page.set_viewport_size({'width': 390, 'height': 844})
                if language == 'vi':
                    await page.get_by_role('button', name='Tiếng Việt', exact=True).click()
                await no_overflow(page)
                if name in ['payment', 'payment-amount']:
                    await page.screenshot(path=str(args.output / f'{name}-mobile-{language}.png'), full_page=True)
                result['renders'].append({'case': name, 'language': language, 'viewport': '390x844', 'scope': await scope.inner_text(), 'gate': target, 'state': expected})
            await page.reload(wait_until='networkidle')
            assert await page.get_by_test_id('status-panel').get_by_test_id('evidence-scope').inner_text() == ('HISTORICAL FUJI ETH_CALL' if historical else 'PUBLIC FUJI EXECUTION')
            assert job['job_id'] in await page.content()
            await page.get_by_test_id('tab-history').click()
            await page.get_by_role('table').first.wait_for()
            assert 'HISTORICAL FUJI ETH_CALL' in await page.get_by_role('table').first.inner_text()
            await no_overflow(page)
            await page.get_by_test_id('tab-live').click()
            assert not await page.get_by_role('dialog').count(), 'Returning to live reopened a stale gate'
            result['checks'].append(name + ': recorded status, scope, actual gate, evidence drawer, keyboard, mobile VI/EN, reload, history')
            await context.close()

        for language in ['en', 'vi']:
            context, page = await context_for(jobs[-1], language)
            await page.get_by_test_id('tab-research').click()
            budget = page.get_by_test_id('budget-showcase')
            await budget.wait_for()
            await budget.get_by_role('button').nth(2).click()
            assert 'REJECT' in await budget.inner_text()
            assert ('Not signed' if language == 'en' else 'Không ký') in await budget.inner_text()
            await budget.locator('details').first.locator('summary').first.click()
            await budget.locator('.react-flow__node').first.wait_for()
            assert await budget.locator('.react-flow__node').count() == len(research['budget']['steps'][2]['graph']['nodes'])
            assert await budget.locator('.react-flow__edge').count() == len(research['budget']['steps'][2]['graph']['edges'])
            await budget.locator('.itag-explorer > details > summary').click()
            keyboard_node = budget.locator('.itag-node-list button').first
            await keyboard_node.focus()
            await page.keyboard.press('Enter')
            assert await budget.locator('.itag-node-evidence').count() == 1
            await no_overflow(page)
            await page.evaluate('scrollTo(0, 0)')
            await page.screenshot(path=str(args.output / f'research-desktop-{language}.png'), full_page=True)
            purpose = page.get_by_test_id('purpose-showcase')
            await purpose.locator('details').first.locator('summary').first.click()
            await purpose.locator('.react-flow__node').first.wait_for()
            assert await purpose.locator('.react-flow__node').count() == len(research['purpose']['graph']['nodes'])
            assert await purpose.locator('.react-flow__edge').count() == len(research['purpose']['graph']['edges'])
            await purpose.locator('.react-flow__node').first.click()
            assert await purpose.locator('.itag-node-evidence').count() == 1
            for size in [390, 768]:
                await page.set_viewport_size({'width': size, 'height': 844})
                await no_overflow(page)
            await page.set_viewport_size({'width': 390, 'height': 844})
            await page.evaluate('scrollTo(0, 0)')
            await page.screenshot(path=str(args.output / f'research-mobile-{language}.png'), full_page=True)
            result['checks'].append(f'Research {language}: step 3 unsigned, exact graph counts, node evidence, keyboard, desktop/mobile/tablet overflow')
            await context.close()

        for status in ['UNAVAILABLE', 'UNKNOWN', 'RUNNING']:
            job = copy.deepcopy(jobs[-1])
            job.update(status=status, terminal=status != 'RUNNING', active_stage='SIMULATION', attack=None, execution_kind=None,
                       reason_code='ORACLE_UNAVAILABLE' if status == 'UNAVAILABLE' else 'MODEL_RESPONSE_UNAVAILABLE_' + 'LONG_CODE_' * 30)
            job['workflow'].update(timeline=[], activity=[], outcome=None)
            context, page = await context_for(job)
            await page.get_by_test_id('node-3').wait_for()
            if status != 'RUNNING':
                assert 'state-unknown' in await page.get_by_test_id('node-3').get_attribute('class')
            assert not await page.locator('.security-node.state-passed').count()
            await page.get_by_role('button', name='Inspect gate and evidence').click()
            await page.get_by_role('dialog').wait_for()
            await page.set_viewport_size({'width': 390, 'height': 844})
            await no_overflow(page)
            await page.keyboard.press('Escape')
            result['checks'].append(f'{status}: partial workflow does not synthesize PASS or history; missing data/long reason mobile')
            await context.close()

        minimal = copy.deepcopy(jobs[-1])
        minimal.update(status='RUNNING', terminal=False, active_stage='ITAG')
        minimal['workflow'].update(outcome=None, activity=[], timeline=[{'stage': 'ITAG', 'created_at': minimal['created_at'], 'evidence': {'verdict': 'PASS', 'graph': {
            'nodes': [{'node_id': 'request', 'kind': 'AUTHENTICATED_USER_INTENT', 'trust': 'AUTHENTICATED'}, {'node_id': 'candidate', 'kind': 'AGENT_ACTION', 'trust': 'UNVERIFIED'}, {'node_id': 'mandate', 'kind': 'MANDATE', 'trust': 'AUTHENTICATED'}],
            'edges': [{'source': 'request', 'target': 'candidate', 'kind': 'AUTHORIZES'}]}}}])
        context, page = await context_for(minimal)
        await page.get_by_role('button', name='Inspect gate and evidence').click()
        await page.get_by_role('dialog').locator('.react-flow__node').first.wait_for()
        assert await page.get_by_role('dialog').locator('.itag-visual .react-flow__node').count() == 3
        assert await page.get_by_role('dialog').locator('.itag-visual .react-flow__edge').count() == 1
        assert 'TRANSACTION_OUTCOME' not in await page.get_by_role('dialog').locator('.itag-explorer').inner_text()
        result['checks'].append('Synthetic missing-history UI fixture: exactly 3 supplied nodes and 1 edge; no fabricated outcomes')
        await context.close()

        attempt = {'key': 'qa-existing-request-identity', 'body': {'scenario': jobs[-1]['scenario']}, 'created_at': 1}
        context, page = await context_for(jobs[-1], attempt=attempt)
        await page.get_by_role('button', name='Resume request', exact=True).click()
        await page.get_by_test_id('node-11').wait_for()
        await page.wait_for_function('() => sessionStorage.getItem("pacevant.judge.attempt.v1") === null')
        assert jobs[-1]['job_id'] in await page.content()
        result['checks'].append('Interrupted recovery: Resume reads the original request key; restores recorded terminal job without POST')
        await context.close()
        await browser.close()
    assert not result['writes'] and not result['browser_errors'], result
    result['status'] = 'PASS'
    (args.output / 'qa.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:18112')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/audit/security-ux-upgrade-20261121')
    asyncio.run(check(parser.parse_args()))
