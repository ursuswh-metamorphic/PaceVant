"""Allowlisted disposable Foundry tests. No RPC URL, sender, calldata or secret input."""

import json
import subprocess
from collections import deque
from threading import Lock
from time import monotonic

from treasury_backend.core.errors import ControlError
from treasury_backend.paths import ROOT
from treasury_contracts.toolchain import foundry_binary, native_tool_environment

CASES = {
    "prompt-injection": "testAttackUnauthorizedProposal",
    "tampered-calldata": "testAttackTamperedCall",
    "state-drift": "testAttackStateDrift",
    "severe-slippage": "testAttackSevereSlippage",
    "cumulative-loss": "testAttackCumulativeLoss",
    "invalid-payee": "testAttackInvalidPayee",
    "excessive-allowance": "testAttackExcessiveAllowance",
    "kill-switch": "testAttackKillSwitch",
    "daily-cap": "testAttackDailyCap",
}


class AttackLab:
    def __init__(self):
        self.lock = Lock()
        self.calls = deque()

    def run(self, case):
        if case not in CASES:
            raise ControlError("UNKNOWN_ATTACK_CASE", 404)
        if not self.lock.acquire(blocking=False):
            raise ControlError("ATTACK_LAB_BUSY", 429)
        try:
            now = monotonic()
            while self.calls and now - self.calls[0] > 60:
                self.calls.popleft()
            if len(self.calls) >= 8:
                raise ControlError("ATTACK_LAB_RATE_LIMIT", 429)
            self.calls.append(now)
            command = [
                foundry_binary("forge", ROOT),
                "test",
                "--offline",
                "--json",
                "--match-contract",
                "PolicyVaultMVPTest",
                "--match-test",
                "^" + CASES[case] + r"\(\)$",
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=native_tool_environment(),
                capture_output=True,
                text=True,
                timeout=90,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                output = json.loads(completed.stdout)
                results = [
                    r for suite in output.values() for r in suite.get("test_results", {}).values()
                ]
                passed = (
                    completed.returncode == 0
                    and len(results) == 1
                    and results[0].get("status") == "Success"
                )
            except (ValueError, AttributeError):
                passed = False
            return {
                "case": case,
                "test": CASES[case],
                "status": "PASS" if passed else "NOT_VERIFIED",
                "environment": "LOCAL_TEST",
                "label": "SIMULATED ATTACK",
                "broadcast": False,
                "public_chain_receipt": False,
                "public_gas_used_wei": "0",
                "scope": "Deterministic enforcement test; not a measurement of LLM attack-detection accuracy",
            }
        except (subprocess.TimeoutExpired, OSError):
            raise ControlError("ATTACK_LAB_UNAVAILABLE", 503) from None
        finally:
            self.lock.release()
