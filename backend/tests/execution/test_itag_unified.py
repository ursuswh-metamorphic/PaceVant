"""ITAG + real V2 Anvil execution. Semantic replies are explicitly scripted."""

import json
import time
from dataclasses import replace

from eth_account import Account
from fastapi.testclient import TestClient
from v2_setup import activate

from treasury_backend.api.app import create_app
from treasury_backend.config.control import FIXTURES, Settings
from treasury_backend.config.execution import Settings as ExecutionSettings
from treasury_backend.modules.alignment.provider import ShieldConfig
from treasury_backend.modules.execution.service import ExecutionService
from treasury_backend.operations.itag_benchmark import ReplayProvider


def test_itag_v2_large_artifact_fails_closed_before_signing(plane, tmp_path, monkeypatch):
    _, chain, keys, _ = plane
    activate(chain, keys, tmp_path)
    c = chain.context()
    mandate = json.loads((FIXTURES / "mandate.json").read_text(encoding="utf-8"))
    for key in ("chain_id", "vault_address", "owner", "router", "token_in", "token_out", "policy_hash", "proof_policy", "registry"):
        mandate[key] = c[key]
    mandate.update(expires_at=c["policy_expires_at"], session_id=c["proof_session"]["session_id"])
    mp, op = tmp_path / "mandate.json", tmp_path / "oracle.json"
    mp.write_text(json.dumps(mandate), encoding="utf-8")
    op.write_text(json.dumps(dict(chain_id=31337, vault_address=c["vault_address"], price_source="TRUSTED_TEST_ORACLE", price_timestamp=int(time.time()), price_usdc_usd_e8="100000000", price_wavax_usd_e8="2000000000")), encoding="utf-8")
    monkeypatch.setattr("treasury_backend.modules.alignment.engine.ChatProvider", lambda _: ReplayProvider())
    cfg = replace(Settings(), mode="LOCAL", db=tmp_path / "itag.sqlite3", mandate_file=mp,
                  oracle_file=op, attestor_key=keys["attestor"], chain_rpc_url=chain.settings.rpc_url,
                  relayer_address=Account.from_key(keys["relayer"]).address,
                  operator_token="o" * 32, internal_token="i" * 32, require_itag=True,
                  shield=ShieldConfig(mode="paper", context_chars=100000))
    ec = ExecutionSettings(**{**chain.settings.model_dump(), "api_key": "e" * 32})
    app = create_app(cfg, ec, execution_service=ExecutionService(ec, chain))
    with TestClient(app, headers={"Authorization": "Bearer " + cfg.operator_token}) as client:
        spec = client.post("/v1/itag/intents", json=dict(kind="ONE_SHOT_SWAP", mandate_id=mandate["mandate_id"], deadline=int(time.time())+120, total_budget="100000000", steps=[dict(step_id="swap", min_amount="100000000", max_amount="100000000")])).raise_for_status().json()
        request = dict(goal="Buy WAVAX with 100 USDC", mandate_id=mandate["mandate_id"], temporal_intent=dict(spec_id=spec["spec_id"], revision=spec["revision"], step_id="swap"))
        before = chain.balances()
        first = client.post("/v1/workflows/start", json=request).raise_for_status().json()
        wf = client.get('/v1/workflows/'+first["workflow_id"]).raise_for_status().json()
        assert wf["status"] == "ESCALATED", wf
        assert not any(e["stage"] == "ATTESTED" for e in wf["timeline"])
        with app.state.control.store.connection() as conn:
            assert conn.execute("SELECT 1 FROM shield_events WHERE kind='OUTPUT_BUDGET_EXCEEDED'").fetchone()
        assert chain.balances() == before
