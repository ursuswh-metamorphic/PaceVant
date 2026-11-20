"""Check measured artifact integrity separately from runtime security fixtures."""

import hashlib
import json

from treasury_backend.paths import ROOT

ARTIFACT = ROOT / "docs/evaluation/hybrid-task-alignment"


def test_frozen_corpus_and_release_run_bind_the_same_inputs():
    corpus = ROOT / "fixtures/evaluation/curated-300/benchmark_300_curated.jsonl"
    canonical = hashlib.sha256(corpus.read_bytes().replace(b"\r\n",b"\n")).hexdigest()
    original = json.loads((ROOT / "docs/evaluation/curated-300/run/run.json").read_text())
    measured = json.loads((ARTIFACT / "run/run.json").read_text())
    assert canonical == original["dataset_lf_sha256"] == measured["dataset_lf_sha256"]
    assert measured["config"]["algorithm"] == "hybrid-v1"
    for name,digest in measured["implementation_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n",b"\n")).hexdigest() == digest


def test_every_measured_case_respects_fusion_and_has_an_outcome():
    rows = list(map(json.loads,(ARTIFACT / "run/predictions.jsonl").read_text().splitlines()))
    assert len(rows) == len({r["benchmark_id"] for r in rows}) == 300
    for row in rows:
        assert row["execution_eligibility"] == "UNSUPPORTED_EXECUTION"
        assert row["broadcasts"] == 0
        report = row.get("report")
        if report is None:
            assert row["prediction"] == "UNAVAILABLE"
            continue
        checks = report["constraints"]
        if any(c["status"] == "FAIL" for c in checks):
            assert report["status"] == "MISALIGNED"
        if report["status"] == "ALIGNED":
            assert checks and all(c["status"] == "PASS" for c in checks)
            assert report["binding"]["verdict"] == "VALID"
            assert report["action_input_hash"]
            assert report["semantic_findings"]
            assert all(f["verdict"] == "ALIGNED" for f in report["semantic_findings"])


def test_comparison_keeps_abstentions_and_does_not_charge_archived_inference():
    comparison = json.loads((ARTIFACT / "ABLATIONS.json").read_text())
    for key in "ABCD":
        m = comparison[key]["full"]
        assert m["n"] == 300
        assert sum(m[k] for k in ("tp","tn","fp","fn","abstained_accept","abstained_reject")) == 300
        assert m["execution_unsupported"] == 300
        assert comparison[key]["held_out"]["n"] == 244
    assert comparison["A"]["full"]["accuracy_full_denominator"] == .49
    assert comparison["A"]["measurement"]["new_model_calls"] == 0
    assert comparison["B"]["measurement"]["new_model_calls"] == 0


def test_runtime_has_no_frozen_answer_or_sample_identity_dependency():
    source = ROOT / "backend/src/treasury_backend/modules/alignment"
    for name in ("hybrid.py","hybrid_engine.py"):
        text = (source / name).read_text()
        assert not any(marker in text for marker in ("single_tx_", "expected_decision", "intent_constraints", "curate_single_transaction"))
