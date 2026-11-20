"""Integrity and independent-reference checks for the frozen single-transaction corpus."""

import copy
import csv
import importlib.util
import json

from treasury_backend.paths import ROOT

PACKAGE = ROOT / "fixtures/evaluation/curated-300"


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/evaluation" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cases():
    return [
        json.loads(s) for s in (PACKAGE / "benchmark_300_curated.jsonl").read_text().splitlines()
    ]


def test_schema_count_and_operation_scope():
    rows = cases()
    required = {
        "benchmark_id",
        "source_dataset",
        "source_sample_id",
        "original_sample",
        "curated_intent",
        "curated_transaction",
        "operation_type",
        "protocol",
        "expected_decision",
        "expected_violation_type",
        "expected_failure_reason",
        "required_context",
        "audit_status",
        "modifications",
        "modification_rationale",
        "provenance_type",
        "validation_status",
    }
    assert len(rows) == 300
    assert all(required <= r.keys() for r in rows)
    assert all(r["operation_type"] == "SWAP" and r["protocol"] == "Uniswap V2" for r in rows)
    assert all(r["execution_eligibility"] == "UNSUPPORTED_EXECUTION" for r in rows)
    assert all(r["required_context"]["history"] == [] for r in rows)
    assert len({r["benchmark_id"] for r in rows}) == 300
    assert len({r["source_sample_id"] for r in rows}) == 300


def test_no_duplicate_groups_or_semantic_near_duplicates():
    curate = load_tool("curate_single_transaction")
    descriptors = [curate.descriptor(r) for r in cases()]
    assert len({d["group"] for d in descriptors}) == 300
    assert len({d["meaning"] for d in descriptors}) == 300


def test_frozen_originals_and_exact_call_preservation():
    curate = load_tool("curate_single_transaction")
    lineage = json.loads((PACKAGE / "benchmark_300_provenance.json").read_bytes())
    for case, item in zip(cases(), lineage["selected"], strict=True):
        assert curate.digest(case["original_sample"]) == item["original_sample_sha256"]
        assert case["original_sample"]["proposed_tx"]["call"] == case["curated_transaction"]["call"]
        assert case["original_label"] == case["original_sample"]["label"]
        assert case["source_sample_id"] == case["original_sample"]["test_id"]
        assert case["provenance_type"] == "SOURCE_TRANSACTION_WITH_ADAPTED_SYNTHETIC_CONTEXT"


def test_reference_labels_are_independent_of_source_gold():
    curate = load_tool("curate_single_transaction")
    for row in cases():
        result = curate.reference(row)
        assert bool(result) == (row["expected_decision"] == "REJECT")
        assert (result[0][1] if result else "All modeled alignment constraints satisfied") == row[
            "expected_failure_reason"
        ]
        mutated = copy.deepcopy(row)
        mutated["original_label"] = "REJECT" if row["original_label"] == "PASS" else "PASS"
        mutated["original_sample"]["label"] = mutated["original_label"]
        mutated["original_sample"]["reason"] = {"failed_validation_node": "MADE_UP"}
        assert curate.reference(mutated) == result


def test_provider_input_excludes_gold_and_source_identity():
    runner = load_tool("evaluate_curated_single_transaction")
    for row in cases():
        before = runner.model_input(row)
        mutated = copy.deepcopy(row)
        mutated.update(
            expected_decision="WHATEVER",
            source_sample_id="label_leak",
            expected_failure_reason="label_leak",
        )
        mutated["original_sample"] = {"label": "label_leak", "reason": "label_leak"}
        assert runner.model_input(mutated) == before
        serialized = json.dumps(before)
        assert row["source_sample_id"] not in serialized
        assert "label_leak" not in serialized
        assert "original_label" not in serialized
        assert "all_reference_violations" not in serialized


def test_sampling_and_source_statistics_reproduce():
    curate = load_tool("curate_single_transaction")
    lineage = json.loads((PACKAGE / "benchmark_300_provenance.json").read_bytes())
    selected, counts = curate.select_descriptors(
        lineage["eligible_candidate_pool"], lineage["seed"]
    )
    assert [d["id"] for d in selected] == [r["source_sample_id"] for r in cases()]
    assert dict(counts) == lineage["actual_quotas"]
    assert sum(v["count"] for v in lineage["statistics"].values()) == 20000
    for d in lineage["statistics"].values():
        assert not any("transfer" in name.lower() for name in d["operations"])


def test_full_source_audit_and_selection_link():
    with (PACKAGE / "benchmark_300_audit.csv").open(newline="") as stream:
        audit = list(csv.DictReader(stream))
    assert len(audit) == 20000
    selected = [r for r in audit if r["selected"] == "True"]
    assert len(selected) == 300
    assert {r["source_id"] for r in selected} == {r["source_sample_id"] for r in cases()}
    assert all(r["status"] == "MODIFY" for r in selected)


def test_confusion_metrics_keep_abstentions_and_unsupported_separate():
    report = load_tool("report_curated_single_transaction")
    rows = [
        {"gold": gold, "prediction": prediction, "execution_eligibility": "UNSUPPORTED_EXECUTION"}
        for gold, prediction in [
            ("REJECT", "REJECT"),
            ("REJECT", "ACCEPT"),
            ("ACCEPT", "ACCEPT"),
            ("ACCEPT", "UNAVAILABLE"),
        ]
    ]
    m = report.metrics(rows)
    assert m["n"] == 4 and m["execution_unsupported"] == 4
    assert (m["tp"], m["tn"], m["fp"], m["fn"]) == (1, 1, 0, 1)
    assert m["accuracy_full_denominator"] == 0.5
    assert m["false_accept_rate"] == 0.5
    assert m["coverage"] == 0.75
    assert m["abstained_accept"] == 1
    assert m["selective_accuracy"] == 2 / 3
    assert report.metrics([rows[2]])["f1"] is None
    assert report.metrics([])["f1"] is None
