import importlib.util
import json
import sys
from itertools import count
from pathlib import Path
from uuid import UUID

from treasury_backend.modules.alignment.provider import ShieldConfig
from treasury_backend.modules.persistence import Store
from treasury_backend.operations.itag_benchmark import ReplayProvider
from treasury_backend.paths import ROOT


def test_hidden_annotation_cannot_change_any_provider_message(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("bench", ROOT / "tools/evaluation/itag_final.py")
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    sample = json.loads(
        Path(bench.PACKAGE / "LONG_HORIZON_SCENARIOS.jsonl").read_text().splitlines()[0]
    )
    snapshots = []
    for index, label in enumerate(["benign", "purpose_conflict"]):
        seq = count(1)
        for name, module in list(sys.modules.items()):
            if name.startswith("treasury_") and hasattr(module, "uuid4"):
                monkeypatch.setattr(module, "uuid4", lambda seq=seq: UUID(int=next(seq)))
        row = bench.one(
            dict(
                sample, truth=dict(sample["truth"], type=label, expected=("PASS", "REJECT")[index])
            ),
            ShieldConfig(mode="paper", context_chars=100000),
            ReplayProvider(),
            Store(tmp_path / f"case{index}.db"),
        )
        snapshots.append([c["messages_sha256"] for c in row["calls"]])
        assert (
            row["explanation"]["recorded_facts"]["budget_in_token_base_units"]["spent"]
            == "75000000"
        )
    assert snapshots[0] == snapshots[1]
