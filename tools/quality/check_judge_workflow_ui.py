"""Exercise real local judge UI, without mocks or public-chain writes."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PUBLIC='--public' in sys.argv
BASE=next((arg.split('=',1)[1].rstrip('/') for arg in sys.argv if arg.startswith('--url=')),'http://127.0.0.1:5173')
OUT = ROOT / ("data/judge-public-acceptance" if PUBLIC else "data/judge-mvp-final" if '--final' in sys.argv else "data/judge-ui-acceptance")
OUT.mkdir(parents=True, exist_ok=True)
EXPECTED = ['OWNER_AUTHORITY', 'AGENT_PROPOSAL', 'BUILD', 'SIMULATION', 'RISK', 'ITAG', 'PROOF', 'SDE', 'ATTESTATION', 'EXACT_SIGNED_PREFLIGHT', 'OUTCOME']
MODULES = EXPECTED + ['OUTCOME']
report = {'started_at': datetime.now(timezone.utc).isoformat(), 'browser': 'headless Chromium', 'backend_mocked': False, 'public_chain_writes': PUBLIC, 'runs': [], 'checks': [], 'errors': [], 'post_failures': []}
jobs, posts, observations = {}, [], []

def save():
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

save()

with sync_playwright() as play:
    print('Launching local Chromium', flush=True)
    browser = play.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.on('pageerror', lambda error: report['errors'].append(str(error)))
    def response_received(response):
        if '/judge/' in response.url and response.status >= 400 and response.request.method=='POST':
            print('HTTP '+str(response.status)+' '+response.url+' '+response.text()[:300], flush=True)
            report['post_failures'].append({'status':response.status,'body':response.json()})
        if '/judge/jobs' not in response.url or response.status not in (200, 201, 202):
            return
        try:
            value = response.json()
            if 'job_id' not in value:
                return
            jobs[value['job_id']] = value
            if response.request.method == 'POST':
                posts.append({'job_id': value['job_id'], 'scenario': value['scenario']})
            event = {'job_id': value['job_id'], 'status': value['status'], 'phase': value.get('phase'), 'active_stage': value.get('active_stage'), 'stages': [e['stage'] for e in value.get('workflow', {}).get('timeline', [])], 'observed_at': time.time()}
            observations.append(event)
            if len(observations) == 1 or {k:v for k,v in event.items() if k!='observed_at'} != {k:v for k,v in observations[-2].items() if k!='observed_at'}:
                print(json.dumps(event), flush=True)
        except Exception as error:
            report['errors'].append('Response capture: ' + str(error))
    page.on('response', response_received)
    try:
        print('Opening Live Demo', flush=True)
        page.goto(BASE+'/', wait_until='networkidle', timeout=45000)
        page.get_by_test_id('tab-live').click()
        expect(page.get_by_test_id('run-scenario')).to_be_visible()
        page.locator('.react-flow__node[data-id="0"]').click()
        expect(page.get_by_role('dialog')).to_be_visible()
        assert page.get_by_role('dialog').locator('.stage-detail-content').count() == 0
        page.get_by_role('button', name='Close details').click()
        report['checks'].append('No execution data before a real run')
        print('Empty module panel passed', flush=True)

        for scenario in (['payment'] if '--payment-only' in sys.argv else ['swap'] if '--swap-only' in sys.argv else ['payment', 'swap']):
            print('Checking scenario '+scenario, flush=True)
            page.get_by_test_id('scenario-' + scenario).click()
            page.get_by_role('combobox').click()
            options = page.get_by_role('option').all_text_contents()
            assert len(options) == 4, options
            page.keyboard.press('Escape')
            for label in options[1:]:
                print('Checking attack preview '+label.encode('ascii','backslashreplace').decode(), flush=True)
                before = len(posts)
                page.get_by_role('combobox').click()
                page.get_by_role('option', name=label, exact=True).click()
                page.get_by_test_id('run-scenario').click()
                dialog = page.get_by_role('dialog')
                expect(dialog).to_be_visible()
                assert dialog.locator('.preview-disclosure').count() == 1
                assert dialog.locator('.stage-detail-content').count() == 0
                page.get_by_role('button', name='Close details').click()
                assert len(posts) == before
            report['checks'].append(scenario + ': three protocol-specific attack previews; no backend job created')
            print('Starting real '+scenario+' workflow', flush=True)
            page.get_by_role('combobox').click()
            page.get_by_role('option', name=options[0], exact=True).click()
            if '--wait-oracle' in sys.argv:
                # A source observation schedules the test only; all live gates
                # still reread and verify their own context inside the worker.
                until = time.monotonic()+720
                while True:
                    source = page.request.get(BASE+'/judge/source',timeout=30000).json()
                    updated = source.get('oracle',{}).get('updated_at',0)
                    age = time.time()-updated
                    if source.get('status')=='VERIFIED_READ' and 0<=age<=120:
                        print('Verified source window ready, age '+str(round(age))+'s',flush=True)
                        break
                    print('Waiting for independently fresh Chainlink window, source age '+str(round(age))+'s',flush=True)
                    report['waiting_for_oracle']={'scenario':scenario,'age_seconds':round(age),'checked_at':datetime.now(timezone.utc).isoformat()}
                    save()
                    assert time.monotonic()<until,'No fresh oracle signing window within test deadline'
                    page.wait_for_timeout(30000)
            expect(page.get_by_test_id('run-scenario')).to_be_enabled(timeout=15000)
            before = len(posts)
            page.get_by_test_id('run-scenario').click()
            expect(page.get_by_test_id('run-session')).to_be_visible()
            print('Run clicked: '+page.locator('.notice').all_inner_texts().__repr__().encode('ascii','backslashreplace').decode(), flush=True)
            deadline = time.monotonic() + 310
            submission_deadline = time.monotonic() + 40
            while len(posts) == before and time.monotonic() < submission_deadline:
                page.wait_for_timeout(250)
                assert not report['post_failures'], report['post_failures']
            assert len(posts) == before + 1, page.locator('body').inner_text()
            job_id = posts[-1]['job_id']
            reloaded, inspected_ai = False, False
            while time.monotonic() < deadline:
                value = jobs[job_id]
                timeline = value.get('workflow', {}).get('timeline', [])
                if not reloaded and value['status'] == 'RUNNING':
                    page.get_by_role('tab',name='Tổng quan',exact=True).click()
                    expect(page.get_by_test_id('run-session')).to_be_visible()
                    page.reload(wait_until='domcontentloaded')
                    expect(page.get_by_test_id('tab-live')).to_have_attribute('data-state','active')
                    expect(page.get_by_test_id('run-scenario')).to_be_disabled()
                    reloaded = True
                if not inspected_ai and any(e['stage'] == 'AGENT_PROPOSAL' for e in timeline):
                    page.get_by_role('button', name='Chuẩn bị', exact=True).click()
                    page.locator('.react-flow__node[data-id="1"]').click()
                    dialog = page.get_by_role('dialog')
                    expect(dialog.locator('.stage-input blockquote')).to_have_text(value['workflow']['intent']['objective'])
                    expect(dialog.locator('.stage-output')).to_be_visible()
                    assert dialog.locator('pre').count() == 0
                    page.get_by_role('button', name='Close details').click()
                    inspected_ai = True
                if value.get('terminal'):
                    break
                page.wait_for_timeout(400)
            value = jobs[job_id]
            assert value.get('terminal'), 'UI polling did not observe terminal result'
            assert len(posts) == before + 1, 'Reload created another job'
            (OUT / (scenario + '-job.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            run = {'scenario': scenario, 'job_id': job_id, 'status': value['status'], 'reason_code': value.get('reason_code'), 'reload_recovered': reloaded, 'ai_panel_data_matched': inspected_ai, 'post_count': len(posts)-before, 'modules': []}
            report['runs'].append(run)
            save()
            workflow = value.get('workflow', {})
            timeline = workflow.get('timeline', [])
            stages = [event['stage'] for event in timeline]
            run['stages'] = stages
            assert value['environment'] == ('REAL_FUJI_EXECUTION' if PUBLIC else 'ANVIL_FORK')
            assert value['public_chain_broadcast'] is (PUBLIC and value['status']=='CONFIRMED')
            for event in timeline:
                if event['stage'] in EXPECTED:
                    assert stages.index(event['stage']) == EXPECTED.index(event['stage']), stages
            if value['status'] == 'CONFIRMED':
                assert all(event in stages for event in EXPECTED), stages
                assert workflow['outcome']['status'] == 'CONFIRMED'
                if PUBLIC:
                    assert workflow['outcome']['public_chain_receipt'] is True
                    expect(page.get_by_role('link',name='Xem giao dịch trên Fuji')).to_have_attribute('href','https://testnet.snowtrace.io/tx/'+workflow['outcome']['tx_hash'])
                page.get_by_role('button', name='Chuẩn bị', exact=True).click()
                page.locator('.react-flow__node[data-id="0"]').click()
                for index, source in enumerate(MODULES):
                    dialog = page.get_by_role('dialog')
                    expect(dialog.locator('.stage-detail-content')).to_be_visible()
                    assert source in '\n'.join(dialog.locator('.event-recorded').all_inner_texts()), (index, dialog.inner_text())
                    assert dialog.locator('pre').count() == 0
                    content = dialog.inner_text()
                    if index == 1:
                        assert workflow['intent']['objective'] in content
                        assert ('0.01 USDC' if scenario=='payment' else '0.000001 USDC') in content
                    if index in (10, 11):
                        assert workflow['outcome']['tx_hash'] in content
                    run['modules'].append({'index': index, 'data_visible': True, 'source': source})
                    if index < 11:
                        dialog.get_by_role('button', name='Tiếp theo', exact=True).click()
                page.get_by_role('button', name='Close details').click()
                assert page.locator('.security-node.state-passed').count() == 12
            else:
                expect(page.get_by_test_id('run-block-reason')).to_be_visible()
            # A completed run also survives a refresh without recreating a job.
            page.reload(wait_until='domcontentloaded')
            expect(page.get_by_test_id('tab-live')).to_have_attribute('data-state','active')
            expect(page.get_by_test_id('run-session').locator('.run-session-id')).to_have_attribute('title',job_id)
            assert len(posts)==before+1
            run['completed_refresh_restored']=True
            page.get_by_test_id('tab-history').click()
            expect(page.locator('.history-surface tbody tr')).to_have_count(len(report['runs']), timeout=15000)
            page.get_by_test_id('tab-live').click()
            save()
        report['checks'].append('Each real run submitted once; F5 recovered its identity without duplicate POST')
        if '--final' in sys.argv:
            # The existing fixed guard preset is backend-only in the current UI.
            # Submit its exact supported API contract; then view it through the
            # same recovery path with the actual returned job identity.
            print('Starting backend-only security guard (not one of the six previews)',flush=True)
            response=page.request.post(BASE+'/judge/jobs',
                data={'scenario':'guard'},headers={'Idempotency-Key':'final-guard-'+str(time.time_ns())})
            assert response.status==202,response.text()
            guard=response.json()
            # The display reference performs only GET and cannot grant authority.
            page.evaluate('(run)=>sessionStorage.setItem("pacevant.judge.view.v1",JSON.stringify(run))',
                {'job_id':guard['job_id'],'scenario':'guard'})
            page.reload(wait_until='domcontentloaded')
            expect(page.get_by_test_id('tab-live')).to_have_attribute('data-state','active')
            deadline=time.monotonic()+310
            while not jobs.get(guard['job_id'],{}).get('terminal') and time.monotonic()<deadline:
                page.wait_for_timeout(500)
            value=jobs[guard['job_id']]
            assert value.get('terminal')
            (OUT/'guard-job.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            guard_run={'scenario':'guard','surface':'backend-only fixed preset, viewed in UI','job_id':value['job_id'],
                'status':value['status'],'reason_code':value.get('reason_code'),'stages':[e['stage'] for e in value.get('workflow',{}).get('timeline',[])]}
            report['runs'].append(guard_run)
            save()
            expect(page.get_by_test_id('run-block-reason')).to_be_visible()
            guard_run['displayed_reason']=page.get_by_test_id('run-block-reason').inner_text()
            assert value['status']=='REJECTED', 'Guard must be rejected by a real check; dependency failure is not attack detection'
            assert not any(e['stage'] in ['ATTESTATION','OUTCOME'] for e in value['workflow']['timeline'])
            page.get_by_test_id('run-block-reason').get_by_role('button').click()
            expect(page.locator('.block-codes')).to_contain_text(value['reason_code'])
            page.get_by_role('button',name='English',exact=True).click()
            expect(page.get_by_test_id('run-block-reason')).to_contain_text('Why did the run stop?')
            page.get_by_role('button',name='Tiếng Việt',exact=True).click()
            page.reload(wait_until='domcontentloaded')
            expect(page.get_by_test_id('run-block-reason')).to_be_visible()
            report['checks'].append('Real backend guard rejected before signing; UI explained reason in VI/EN and retained it after F5')
        for width,height in [(1440,900),(390,844)]:
            page.set_viewport_size({'width':width,'height':height})
            assert page.locator('body').evaluate('(element)=>element.scrollWidth') <= width
        assert not report['errors'], report['errors']
        report['status'] = 'PASS' if all(run['status']==('REJECTED' if run['scenario']=='guard' else 'CONFIRMED') for run in report['runs']) else 'BACKEND_RUN_NOT_CONFIRMED'
    except Exception as error:
        report['status'] = 'FAIL'
        report['failure'] = str(error)
        print('FAIL: '+str(error).encode('ascii','backslashreplace').decode(), flush=True)
    finally:
        report['posts'] = posts
        report['observations'] = observations
        save()
        browser.close()
print(json.dumps({'status':report['status'], 'runs':report['runs'], 'failure':report.get('failure'), 'errors':report['errors']}), flush=True)
if report['status'] != 'PASS':
    raise SystemExit(1)
