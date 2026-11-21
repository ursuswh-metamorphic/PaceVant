"""Controlled UI fault injection only. Not a live security/transaction evaluation."""
import copy
import json
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/judge-mvp-final'
fixture=json.loads((ROOT/'fixtures/judge/payment.json').read_text(encoding='utf-8'))
job_id='judge_'+'e'*32
job={'job_id':job_id,'scenario':'payment','status':'RUNNING','created_at':int(time.time()),
    'environment':'ANVIL_FORK','public_chain_broadcast':False,'terminal':False,
    'phase':'WORKFLOW_RUNNING','active_stage':'SIMULATION','workflow':copy.deepcopy(fixture)}
job['workflow'].update(status='BUILT',outcome=None,timeline=fixture['timeline'][:3])
config={'enabled':True,'mode':'ANVIL_FORK','configured':True,'busy':False,
    'scenarios':[{'id':name} for name in ['payment','swap','guard']],
    'quota':{'remaining_today':6},'limits':{'timeout_seconds':240,'max_concurrent':1}}
report={'scope':'UI fault injection with controlled API responses, not live acceptance',
    'checks':[],'posts':0,'errors':[]}
state={'lost_response':False,'offline':False,'missing_accepted':False,'accepted':False,'key':None}

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':900})
    page.on('pageerror',lambda error:report['errors'].append(str(error)))
    def handler(route):
        request=route.request
        path=request.url.split('http://127.0.0.1:5173')[-1]
        if path=='/judge/config':
            return route.fulfill(json=config)
        if path=='/judge/history':
            return route.fulfill(json={'jobs':[]})
        if path=='/judge/jobs' and request.method=='POST':
            report['posts']+=1
            state['accepted']=True
            state['key']=request.headers.get('idempotency-key')
            if state['lost_response']:
                return route.abort('connectionreset')
            return route.fulfill(status=202,json=job)
        if path.startswith('/judge/requests/'):
            if state['accepted']:
                assert path.endswith(state['key'])
                return route.fulfill(json=job)
            return route.fulfill(status=404,json={'error':{'code':'JUDGE_REQUEST_NOT_FOUND'}})
        if path.startswith('/judge/jobs/'):
            if state['missing_accepted']:
                return route.fulfill(status=404,json={'error':{'code':'JUDGE_REQUEST_NOT_FOUND'}})
            if state['offline']:
                return route.abort('internetdisconnected')
            return route.fulfill(json=job)
        raise AssertionError('Unexpected API route '+path)
    page.route('**/judge/**',handler)
    try:
        page.goto('http://127.0.0.1:5173/',wait_until='networkidle')
        page.get_by_test_id('tab-live').click()
        state['lost_response']=True
        page.get_by_test_id('run-scenario').click()
        expect(page.get_by_test_id('run-session')).to_be_visible()
        page.reload(wait_until='domcontentloaded')
        expect(page.get_by_test_id('tab-live')).to_have_attribute('data-state','active')
        expect(page.get_by_test_id('run-session').locator('.run-session-id')).to_have_attribute('title',job_id,timeout=12000)
        assert report['posts']==1
        report['checks'].append('Lost POST response recovered by key after F5; no second POST')
        state['offline']=True
        page.reload(wait_until='domcontentloaded')
        expect(page.get_by_test_id('run-session')).to_contain_text('Tạm mất kết nối',timeout=12000)
        expect(page.get_by_test_id('run-scenario')).to_be_disabled()
        assert report['posts']==1
        state['offline']=False
        page.get_by_test_id('run-session').get_by_role('button',name='Kết nối lại',exact=True).click()
        expect(page.get_by_test_id('run-session')).to_contain_text('EVM Simulation')
        report['checks'].append('Disconnected GET is explicit and reconnect uses the same run without POST')
        state['missing_accepted']=True
        page.reload(wait_until='domcontentloaded')
        expect(page.get_by_test_id('run-session')).to_contain_text('Tạm mất kết nối',timeout=12000)
        page.get_by_test_id('run-session').get_by_role('button',name='Kết nối lại',exact=True).click()
        page.wait_for_timeout(1500)
        assert report['posts']==1
        report['checks'].append('Missing accepted job remains read-only; reconnect does not submit it again')
        state['missing_accepted']=False
        job.update(status='REJECTED',terminal=True,active_stage='ITAG',reason_code='SECURITY_GATE_FAILED')
        job['workflow']['timeline'] += [
            {'stage':'RISK','created_at':int(time.time()),'evidence':{'result':'FAIL','reason_codes':['MIN_OUTPUT_NOT_MET']}},
            {'stage':'ITAG','created_at':int(time.time()),'evidence':{'verdict':'PASS'}},
            {'stage':'REJECTION_OR_RECOVERY','created_at':int(time.time()),'evidence':{'code':'SECURITY_GATE_FAILED','signed':False}}]
        page.reload(wait_until='domcontentloaded')
        reason=page.get_by_test_id('run-block-reason')
        expect(reason).to_contain_text('Economic Risk')
        expect(reason).to_contain_text('thấp hơn mức tối thiểu')
        expect(reason).to_contain_text('trước khi ký')
        assert report['posts']==1
        page.reload(wait_until='domcontentloaded')
        expect(page.get_by_test_id('run-block-reason')).to_contain_text('Economic Risk')
        report['checks'].append('Specific failed Risk evidence wins over current ITAG stage and generic root error; terminal F5 restores it')
        for width,height in [(1440,900),(390,844)]:
            page.set_viewport_size({'width':width,'height':height})
            assert page.locator('body').evaluate('(node)=>node.scrollWidth')<=width
        assert not report['errors'],report['errors']
        report['status']='PASS'
    except Exception as error:
        report.update(status='FAIL',failure=str(error))
        raise
    finally:
        OUT.mkdir(exist_ok=True,parents=True)
        (OUT/'session-fault-injection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        browser.close()
print(json.dumps(report),flush=True)
