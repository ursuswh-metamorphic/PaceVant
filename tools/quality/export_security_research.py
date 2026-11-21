"""Build the read-only UX showcase from immutable, existing evaluation records.

No network, model calls, signing or execution. --check verifies reproducibility.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'frontend/public/evidence/security-research.json'
BASE = '16e4d68437e74fceb1fe41281e05d99490465837'


def source(path):
    raw = (ROOT / path).read_bytes().replace(b'\r\n', b'\n')
    committed = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)
    assert raw == committed, f'Source differs from the linked commit: {path}'
    return {'path': path, 'sha256': hashlib.sha256(raw).hexdigest(),
            'url': f'https://github.com/ursuswh-metamorphic/PaceVant/blob/{BASE}/{path}'}


def build():
    budget_path = 'docs/evaluation/itag-final/ANVIL_BUDGET_ISOLATION.json'
    semantic_path = 'docs/evaluation/itag-semantic-reliability/FINAL_LIVE_RESULTS.json'
    budget = json.loads((ROOT / budget_path).read_text(encoding='utf-8'))
    semantic = json.loads((ROOT / semantic_path).read_text(encoding='utf-8'))
    row = next(r for r in semantic['rows'] if r['id'] == 'lh002' and r['repetition'] == 1)
    assert row['deterministic'] == 'PASS' and row['semantic'] == 'MISALIGNED' and row['sde']['hybrid'] == 'REJECT'
    assert budget['public_broadcasts'] == 0 and semantic['broadcasts'] == 0
    steps = []
    for r in budget['rows']:
        assessment = r['explanation']['assessment']
        facts = r['explanation']['recorded_facts']
        steps.append({k: r[k] for k in ['workflow', 'sde', 'risk', 'proof', 'signed', 'receipt', 'graph', 'graph_hash']} | {
            'candidate': r['candidate'], 'deterministic': assessment['deterministic'],
            'budget': facts['intent_records'][0]['terms']['total_budget'],
            'prior_outcomes': facts['prior_outcomes'], 'summary': r['explanation']['decision_summary']})
    assert [r['signed'] for r in steps] == [True, True, False]
    assert [r['deterministic']['spent'] for r in steps] == ['0', '10000000', '20000000']
    assert all(r['budget'] == '20000000' and r['candidate']['amount_in_base_units'] == '10000000' for r in steps)
    return {'version': 1, 'source_commit': BASE,
            'budget': {'scope': 'RECORDED · LOCAL ANVIL · SCRIPTED EVALUATION', 'chain_id': budget['chain_id'],
                       'public_broadcasts': 0, 'source': source(budget_path), 'steps': steps},
            'purpose': {'scope': 'REAL-MODEL RESEARCH · SYNTHETIC HISTORY', 'broadcasts': 0,
                        'source': source(semantic_path),
                        **{k: row[k] for k in ['id', 'repetition', 'graph', 'deterministic', 'semantic', 'semantic_finding', 'semantic_reasons', 'sde']},
                        'facts': row['explanation']['recorded_facts'],
                        'provider': {k: row['semantic_provider'][k] for k in ['model', 'provider', 'prompt_version', 'scope']}},
            'metric_sources': [source('docs/research/EXPERIMENT_CATALOG.md'),
                               source('docs/evaluation/itag-semantic-reliability/FINAL_REPORT.md')]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    content = json.dumps(build(), ensure_ascii=False, indent=2) + '\n'
    if args.check:
        assert OUTPUT.read_text(encoding='utf-8') == content, 'Research export is stale'
        print('Research artifact matches source records; no execution performed.')
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(content, encoding='utf-8')
        print(f'Exported {OUTPUT.relative_to(ROOT)}')
