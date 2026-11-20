"""ITAG + real V2 Anvil execution. Semantic replies are explicitly scripted."""

import json
import time

import pytest
from dataclasses import replace

from eth_account import Account
from fastapi.testclient import TestClient
from v2_setup import activate

from treasury_backend.api.app import create_app
from treasury_backend.config.control import FIXTURES, Settings
from treasury_backend.config.execution import Settings as ExecutionSettings
from treasury_backend.config.demo import DemoSettings
from treasury_backend.modules.alignment.provider import ShieldConfig, Completion
from treasury_backend.modules.execution.service import ExecutionService
from treasury_backend.operations.itag_benchmark import ReplayProvider


@pytest.mark.parametrize("output_limit,mode,demo,fee_cap", [(1000,"paper",False,5*10**15), (16000,"paper",False,5*10**15), (65536,"paper",False,5*10**15), (65536,"wallet_pipeline",False,5*10**15), (65536,"wallet_pipeline",True,5*10**15), (65536,"wallet_pipeline",True,1)])
def test_itag_v2_artifact_budget_and_completion(plane, tmp_path, monkeypatch, output_limit, mode, demo, fee_cap):
    _, chain, keys, _ = plane
    activate(chain, keys, tmp_path)
    c = chain.context()
    mandate = json.loads((FIXTURES / "mandate.json").read_text(encoding="utf-8"))
    for key in (
        "chain_id",
        "vault_address",
        "owner",
        "router",
        "token_in",
        "token_out",
        "policy_hash",
        "proof_policy",
        "registry",
    ):
        mandate[key] = c[key]
    mandate.update(expires_at=c["policy_expires_at"], session_id=c["proof_session"]["session_id"])
    mp, op = tmp_path / "mandate.json", tmp_path / "oracle.json"
    mp.write_text(json.dumps(mandate), encoding="utf-8")
    op.write_text(
        json.dumps(
            dict(
                chain_id=31337,
                vault_address=c["vault_address"],
                price_source="TRUSTED_TEST_ORACLE",
                price_timestamp=int(time.time()),
                price_usdc_usd_e8="100000000",
                price_wavax_usd_e8="2000000000",
            )
        ),
        encoding="utf-8",
    )

    class DataFixtureProvider(ReplayProvider):
        def complete(self, messages):
            data = json.loads(messages[1]["content"])
            if "subject" in data and data["message"]["role"] == "TOOL":
                # Scripted extraction: real chain artifacts in this fixture contain data, no commands.
                return Completion("[]")
            return super().complete(messages)

    monkeypatch.setattr(
        "treasury_backend.modules.alignment.engine.ChatProvider", lambda _: DataFixtureProvider()
    )
    cfg = replace(
        Settings(),
        mode="LOCAL",
        db=tmp_path / "itag.sqlite3",
        mandate_file=mp,
        oracle_file=op,
        attestor_key=keys["attestor"],
        chain_rpc_url=chain.settings.rpc_url,
        relayer_address=Account.from_key(keys["relayer"]).address,
        operator_token="o" * 32,
        internal_token="i" * 32,
        require_itag=True,
        shield=ShieldConfig(mode=mode, context_chars=100000, max_output_chars=output_limit),
    )
    ec = ExecutionSettings(**{**chain.settings.model_dump(), "api_key": "e" * 32})
    demo_config = DemoSettings(enabled=demo, address="0x" + "11" * 20, access_token="d" * 32,
                               initial_credit_wei=10**16, max_transaction_fee_wei=fee_cap)
    app = create_app(cfg, ec, execution_service=ExecutionService(ec, chain), demo_settings=demo_config,legacy_demo_tests=True)
    with TestClient(app, headers={"Authorization": "Bearer " + cfg.operator_token}) as client:
        spec = (
            client.post(
                "/v1/itag/intents",
                json=dict(
                    kind="ONE_SHOT_SWAP",
                    mandate_id=mandate["mandate_id"],
                    deadline=int(time.time()) + 120,
                    total_budget="100000000",
                    steps=[dict(step_id="swap", min_amount="100000000", max_amount="100000000")],
                ),
            )
            .raise_for_status()
            .json()
        )
        request = dict(
            goal="Buy WAVAX with 100 USDC",
            mandate_id=mandate["mandate_id"],
            temporal_intent=dict(
                spec_id=spec["spec_id"], revision=spec["revision"], step_id="swap"
            ),
        )
        before = chain.balances()
        nonce_before = chain.w3.eth.get_transaction_count(chain.deployment["relayer"])
        if demo:
            unauth = client.get("/v1/demo/account")
            assert unauth.status_code == 401  # Operator credential is NOT a demo credential.
            selected = client.post("/v1/demo/select", json={"account_id":"demo"}).raise_for_status().json()
            assert selected["access_token"] != demo_config.access_token
            headers = {"Authorization": "Bearer " + selected["access_token"], "Idempotency-Key": "demo-request-1"}
            denied = client.post("/v1/workflows/start", headers=headers, json=request)
            assert denied.status_code == 401
            first = client.post("/v1/demo/workflows", json={"goal": request["goal"]}, headers=headers).raise_for_status().json()
        else:
            first = client.post("/v1/workflows/start", json=request).raise_for_status().json()
        wf = client.get("/v1/workflows/" + first["workflow_id"]).raise_for_status().json()
        for _ in range(30):
            if wf["status"] not in {"SUBMITTING", "SUBMITTED"}:
                break
            time.sleep(0.1)
            wf = client.get("/v1/workflows/" + first["workflow_id"]).raise_for_status().json()
        if demo and fee_cap == 1:
            assert wf["status"] == "FAILED_TO_SUBMIT", wf["status"]
            assert "DEMO_TRANSACTION_FEE_LIMIT" in wf["timeline"][-1]["reason_codes"]
            assert any(e["stage"] == "ATTESTED" for e in wf["timeline"])
            assert chain.w3.eth.get_transaction_count(chain.deployment["relayer"]) == nonce_before
            account = client.get("/v1/demo/account", headers=headers).raise_for_status().json()
            assert account["spent_wei"] == account["reserved_wei"] == "0"
            assert not account["transactions"]
            return
        if output_limit >= 16000:
            assert wf["status"] == "CONFIRMED", [
                (e["stage"], e.get("decision", {}).get("reason_codes")) for e in wf["timeline"]
            ]
            if demo:
                ledger = app.state.gas_credit
                assert ledger.billed(next(e["build"]["build_id"] for e in wf["timeline"] if e["stage"] == "BUILT"))
                account = client.get("/v1/demo/account", headers=headers).raise_for_status().json()
                assert len(account["transactions"]) == 1 and int(account["spent_wei"]) > 0
                assert account["reserved_wei"] == "0"
                tx = account["transactions"][0]
                receipt = chain.w3.eth.get_transaction_receipt(tx["tx_hash"])
                assert int(tx["actual_cost_wei"]) == receipt.gasUsed * receipt.effectiveGasPrice
                nonce = chain.w3.eth.get_transaction_count(chain.deployment["relayer"])
                duplicate = client.post("/v1/demo/workflows", json={"goal": request["goal"]}, headers=headers).raise_for_status().json()
                assert duplicate["workflow_id"] == first["workflow_id"]
                assert chain.w3.eth.get_transaction_count(chain.deployment["relayer"]) == nonce
                account2 = client.get("/v1/demo/account", headers=headers).raise_for_status().json()
                assert account2["spent_wei"] == account["spent_wei"]
                assert len([e for e in account2["ledger"] if e["kind"] == "GAS_DEBIT"]) == 1
                assert "private_key" not in json.dumps(account2).lower()
                checked = client.get("/v1/demo/workflows/" + first["workflow_id"] + "/security-checks", headers=headers).raise_for_status().json()
                assert checked["all_passed"] and checked["broadcast"] is False
                assert all(c["status"] == "PASS" for c in checked["checks"])
                assert chain.w3.eth.get_transaction_count(chain.deployment["relayer"]) == nonce
                # RPC failure is inconclusive, never a successful negative security check.
                with monkeypatch.context() as failed_rpc:
                    def unavailable(*args, **kwargs):
                        raise RuntimeError("test-only RPC outage")
                    failed_rpc.setattr(chain.w3.eth, "call", unavailable)
                    inconclusive = client.get("/v1/demo/workflows/" + first["workflow_id"] + "/security-checks", headers=headers).raise_for_status().json()
                    assert not inconclusive["all_passed"]
                    assert all(c["status"] == "INCONCLUSIVE" for c in inconclusive["checks"])
                request["temporal_intent"] = wf["temporal_intent"]
                # A second demo request with no available credit MUST NOT broadcast.
                with ledger.db() as db:
                    db.execute("UPDATE demo_account SET credit_wei=?", (account["spent_wei"],))
                denied = client.post("/v1/demo/workflows", json={"goal": request["goal"]}, headers={**headers, "Idempotency-Key":"demo-request-2"})
                assert denied.status_code == 409 and denied.json()["error"]["code"] == "GAS_CREDIT_INSUFFICIENT"
                assert chain.w3.eth.get_transaction_count(chain.deployment["relayer"]) == nonce
            second = client.post("/v1/workflows/start", json=request).raise_for_status().json()
            assert second["status"] == "REJECTED", second
        else:
            assert wf["status"] == "ESCALATED", wf
            assert not any(e["stage"] == "ATTESTED" for e in wf["timeline"])
            with app.state.control.store.connection() as conn:
                assert conn.execute(
                    "SELECT 1 FROM shield_events WHERE kind='OUTPUT_BUDGET_EXCEEDED'"
                ).fetchone()
            assert chain.balances() == before
