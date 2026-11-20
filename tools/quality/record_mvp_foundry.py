"""Run and record local Foundry verification without broadcasting or accessing wallet keys."""

import hashlib
import json
import subprocess

from treasury_backend.paths import ROOT
from treasury_contracts.toolchain import foundry_binary, native_tool_environment


def main():
    command = [foundry_binary("forge", ROOT), "test", "--offline", "--json"]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=native_tool_environment(),
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    raw = json.loads(result.stdout)
    cases = {
        suite: {name: test["status"] for name, test in body["test_results"].items()}
        for suite, body in raw.items()
    }
    states = [state for suite in cases.values() for state in suite.values()]
    sizes = {}
    for name in ("PolicyVaultMVP", "LFJSwapAdapterV3"):
        a = json.loads((ROOT / "out" / (name + ".sol") / (name + ".json")).read_text())
        sizes[name] = (len(a["deployedBytecode"]["object"].removeprefix("0x"))) // 2
        assert sizes[name] <= 24576
    source_paths = [
        "contracts/src/PolicyVaultMVP.sol",
        "contracts/src/PolicyVaultV3.sol",
        "contracts/src/adapters/LFJSwapAdapterV3.sol",
        "contracts/src/adapters/LFJSwapAdapter.sol",
        "packages/contracts-api/treasury_contracts/mvp.py",
        "packages/contracts-api/treasury_contracts/proof_v3.py",
    ]
    summary = {
        "environment": "LOCAL_TEST",
        "command": "forge test --offline --json",
        "public_writes": False,
        "passed": states.count("Success"),
        "failed": states.count("Failure"),
        "skipped": states.count("Skipped"),
        "returncode": result.returncode,
        "runtime_size_bytes": sizes,
        "cases": cases,
        "source_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in source_paths
        },
    }
    path = ROOT / "docs/audit/mvp-foundry-results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in {"cases", "source_sha256"}}, indent=2
        )
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
