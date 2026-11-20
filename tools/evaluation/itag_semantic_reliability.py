"""Bounded catalog evaluation over existing immutable paired cases."""

import argparse
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from itag_final import LIVE_CASES, PACKAGE, one, summarize

from treasury_backend.modules.alignment.provider import ChatProvider, Completion, ShieldConfig
from treasury_backend.modules.persistence import Store
from treasury_backend.modules.temporal.semantic_evaluator import PROMPT
from treasury_backend.operations.env import read_env
from treasury_backend.operations.itag_benchmark import ReplayProvider
from treasury_backend.paths import ROOT


class RecordedProvider(ChatProvider):
    def __init__(self, config):
        super().__init__(config)
        self.semantic_outputs = []

    def complete(self, messages):
        result = super().complete(messages)
        if messages[0]["content"] == PROMPT:
            from treasury_backend.modules.alignment.provider import safe_value

            try:
                self.semantic_outputs.append(safe_value(json.loads(result.content)))
            except ValueError:
                self.semantic_outputs.append({"parse_error": True})
        return result


class CatalogFixture(ReplayProvider):
    """Canned judgment for interface testing only; labels never enter live provider requests."""

    def __init__(self, conflict=False):
        self.conflict = conflict

    def complete(self, messages):
        if messages[0]["content"] != PROMPT:
            return super().complete(messages)
        data = json.loads(messages[1]["content"])
        catalog = data["evidence_catalog"]
        candidate = next(e for e in catalog["entries"] if e["alias"] == catalog["candidate_alias"])
        scope = next(e for e in catalog["entries"] if "terms" in e["fields"])
        return Completion(
            json.dumps(
                {
                    "candidate_alias": candidate["alias"],
                    "semantic_verdict": "MISALIGNED" if self.conflict else "ALIGNED",
                    "goal_drift_detected": self.conflict,
                    "uncertainty": [],
                    "task_relationships": [
                        {
                            "task_alias": t,
                            "relationship": "CONTRADICTORY" if self.conflict else "DIRECT",
                            "supporting_aliases": [candidate["alias"], scope["alias"]],
                            "objective_field": "terms.objective",
                            "candidate_field": "proposal.user_goal_reason",
                            "explanation": "Scripted relationship to exercise canonical grounding.",
                        }
                        for t in catalog["task_aliases"]
                    ],
                }
            )
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    p.add_argument("--all", action="store_true")
    p.add_argument("--generalization", action="store_true")
    p.add_argument("--repeat", type=int, choices=(1, 2), default=1)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error("Use an unused result filename")
    config = ShieldConfig(mode="paper", context_chars=100000)
    if args.live:
        config = replace(
            ShieldConfig.from_values("FUJI", read_env(ROOT / ".env")), retries=0, fallbacks=()
        )
        if not config.api_key:
            p.error("Provider credential missing")
    rows = []
    for repetition in range(args.repeat):
        for sample in map(
            json.loads, (PACKAGE / "LONG_HORIZON_SCENARIOS.jsonl").read_text().splitlines()
        ):
            if not args.all and sample["id"] not in (
                *LIVE_CASES,
                *(("lh005", "lh006", "lh007", "lh008") if args.generalization else ()),
            ):
                continue
            with TemporaryDirectory() as directory:
                provider = (
                    RecordedProvider(config)
                    if args.live
                    else CatalogFixture(sample["truth"]["type"] == "purpose_conflict")
                )
                row = one(sample, config, provider, Store(Path(directory) / "case.db"))
                row["raw_semantic_outputs"] = getattr(provider, "semantic_outputs", [])
                row["repetition"] = repetition + 1
                rows.append(row)
                print(
                    row["id"],
                    row["semantic"],
                    row["sde"]["hybrid"],
                    row["semantic_provider"].get("grounding_error"),
                    flush=True,
                )
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(
            {
                "provenance": "REAL_MODEL_SYNTHETIC_HISTORY" if args.live else "SCRIPTED",
                "broadcasts": 0,
                "metrics": summarize(rows),
                "rows": rows,
            },
            stream,
            indent=1,
        )
        stream.write("\n")


if __name__ == "__main__":
    main()
