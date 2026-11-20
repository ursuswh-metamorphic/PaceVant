"""LOCAL transfer integration using the canonical app and disposable Anvil vault."""

import json
import time
from dataclasses import replace
from pathlib import Path

import pytest
from eth_account import Account
from fastapi.testclient import TestClient
from v2_setup import activate
from web3 import Web3

from treasury_backend.api.app import create_app
from treasury_backend.config.control import FIXTURES, Settings
from treasury_backend.config.execution import Settings as ExecutionSettings
from treasury_backend.config.demo import DemoSettings
from treasury_backend.modules.alignment.provider import Completion, ShieldConfig
from treasury_backend.modules.execution.service import ExecutionService
from treasury_backend.operations.execution import send
from treasury_backend.operations.itag_benchmark import ReplayProvider
from treasury_backend.modules.transfers.service import PLANNER_PROMPT
from treasury_backend.modules.temporal.semantic_evaluator import PROMPT
from treasury_contracts.transfer import transfer_tuple


class TransferFixture(ReplayProvider):
    mutations = {}

    def complete(self, messages):
        data = json.loads(messages[1]["content"])
        if messages[0]["content"] == PLANNER_PROMPT:
            task = data["task"]
            return Completion(
                json.dumps(
                    dict(
                        action="TRANSFER_ERC20",
                        intent_id=data["intent_id"],
                        task_id=task["task_id"],
                        revision=task["revision"],
                        chain_id=task["chain_id"],
                        vault_address=task["vault_address"],
                        token=task["token"],
                        recipient=task["recipient"],
                        amount_base_units="20000000",
                        deadline=data["deadline"],
                        user_goal_reason=task["objective"],
                        **{},
                    )
                    | self.mutations
                )
            )
        if messages[0]["content"] == PROMPT:
            cat = data["evidence_catalog"]
            scope = next(e for e in cat["entries"] if e["scope_role"] == "ACTIVE_OPERATOR_INTENT")
            return Completion(
                json.dumps(
                    dict(
                        candidate_alias=cat["candidate_alias"],
                        semantic_verdict="ALIGNED",
                        goal_drift_detected=False,
                        uncertainty=[],
                        task_relationships=[
                            dict(
                                task_alias=t,
                                relationship="DIRECT",
                                supporting_aliases=[scope["alias"], cat["candidate_alias"]],
                                objective_field="terms.objective",
                                candidate_field="proposal.user_goal_reason",
                                explanation="Scripted authorized payment.",
                            )
                            for t in cat["task_aliases"]
                        ],
                    )
                )
            )
        return super().complete(messages)


@pytest.fixture
def transfer_app(plane, tmp_path, monkeypatch):
    _, chain, keys, _ = plane
    owner = Account.from_key(keys["owner"])
    send(chain.w3, owner, chain.vault.functions.setApprovalTtl(180))
    activate(
        chain,
        keys,
        tmp_path,
        {"max_session_risk_usd_e8": "100000000000", "global_daily_risk_usd_e8": "100000000000"},
    )
    now = chain.w3.eth.get_block("latest").timestamp
    session = chain.deployment["session_id"]
    send(chain.w3, owner, chain.vault.functions.revokeSession(session))
    # Sessions are immutable identities. Use an explicit fresh fixture session.
    session = "0x" + "a7" * 32
    send(
        chain.w3, owner, chain.vault.functions.createSession(session, now, now + 3600, 1000 * 10**8)
    )
    chain.deployment["session_id"] = session
    recipient = Account.create().address
    send(
        chain.w3,
        owner,
        chain.vault.functions.configureTransferRecipient(
            chain.usdc.address, recipient, (50 * 10**6, 100 * 10**6, now + 3600, 10**8, 6, True)
        ),
    )
    c = chain.context()
    mandate = json.loads((FIXTURES / "mandate.json").read_text())
    for k in (
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
        mandate[k] = c[k]
    mandate.update(expires_at=c["policy_expires_at"], session_id=session)
    mp = tmp_path / "transfer-mandate.json"
    mp.write_text(json.dumps(mandate))
    op = tmp_path / "transfer-oracle.json"
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
        )
    )
    provider = TransferFixture()
    monkeypatch.setattr(
        "treasury_backend.modules.alignment.engine.ChatProvider", lambda _: provider
    )
    cfg = replace(
        Settings(),
        mode="LOCAL",
        db=tmp_path / "payment-control.db",
        mandate_file=mp,
        oracle_file=op,
        attestor_key=keys["attestor"],
        chain_rpc_url=chain.settings.rpc_url,
        relayer_address=keys.get("relayer_address", ""),
        operator_token="o" * 32,
        internal_token="i" * 32,
        require_itag=True,
        shield=ShieldConfig(mode="paper", context_chars=100000),
    )
    ec = ExecutionSettings(**{**chain.settings.model_dump(), "api_key": "e" * 32})
    runtime = ExecutionService(ec, chain)
    app = create_app(cfg, ec, execution_service=runtime, demo_settings=DemoSettings(enabled=False))
    with TestClient(app, headers={"Authorization": "Bearer " + cfg.operator_token}) as client:
        yield client, chain, keys, recipient, provider, tmp_path


def authorize(client, chain, recipient, budget=20, one_shot=True):
    task = dict(
        task_id="invoice-123",
        revision=1,
        chain_id=31337,
        vault_address=chain.vault.address,
        token=chain.usdc.address,
        recipient=recipient,
        objective="Pay Alice for invoice 123 using treasury USDC.",
        total_budget=str(budget * 10**6),
        per_transfer=str(min(50, budget) * 10**6),
        deadline=int(time.time()) + 600,
        one_shot=one_shot,
    )
    client.post("/v1/transfers/tasks", json=task).raise_for_status()
    return task


def test_authorized_transfer_and_replay(transfer_app):
    client, chain, keys, recipient, provider, tmp_path = transfer_app
    task = authorize(client, chain, recipient)
    before = chain.usdc.functions.balanceOf(chain.vault.address).call()
    request = dict(
        task_id=task["task_id"],
        revision=1,
        request_id="payment-1",
        goal="Pay Alice 20 USDC for invoice 123.",
    )
    result = client.post("/v1/transfers", json=request).raise_for_status().json()
    assert result["status"] == "CONFIRMED", result
    assert result["semantic"]["verdict"] == "ALIGNED"
    assert result["sde"]["verdict"] == "APPROVE"
    assert result["proof"]["status"] == "VERIFIED"
    assert chain.usdc.functions.balanceOf(recipient).call() == 20 * 10**6
    assert chain.usdc.functions.balanceOf(chain.vault.address).call() == before - 20 * 10**6
    nonce = chain.w3.eth.get_transaction_count(Account.from_key(keys["relayer"]).address)
    duplicate = client.post("/v1/transfers", json=request).raise_for_status().json()
    assert duplicate["tx_hash"] == result["tx_hash"]
    assert chain.w3.eth.get_transaction_count(Account.from_key(keys["relayer"]).address) == nonce
    repeated = (
        client.post("/v1/transfers", json={**request, "request_id": "payment-2"})
        .raise_for_status()
        .json()
    )
    assert repeated["status"] == "REJECTED"
    with client.app.state.execution.store.db() as db:
        raw = db.execute("SELECT raw FROM payment_raw WHERE id='payment-1'").fetchone()[0]
    tx = chain.w3.eth.get_transaction(result["tx_hash"])
    with pytest.raises(Exception):
        chain.w3.eth.call({"from": tx["from"], "to": tx["to"], "data": tx["input"]})
    assert chain.usdc.functions.balanceOf(recipient).call() == 20 * 10**6
    (tmp_path / "evidence.json").write_text(
        json.dumps(
            {
                "task": task,
                "request": request,
                "before": str(before),
                "approved": result,
                "replay": repeated,
            },
            indent=1,
        )
    )


def test_unauthorized_recipient(transfer_app):
    client, chain, _, recipient, provider, _ = transfer_app
    task = authorize(client, chain, recipient)
    stranger = Account.create().address
    provider.mutations = {"recipient": stranger}
    result = (
        client.post(
            "/v1/transfers",
            json=dict(
                task_id=task["task_id"],
                revision=1,
                request_id="bad-recipient",
                goal="Pay Alice 20 USDC.",
            ),
        )
        .raise_for_status()
        .json()
    )
    assert result["status"] in {"REJECTED", "ESCALATED"}
    assert not result.get("signed") and not result.get("tx_hash")
    assert chain.usdc.functions.balanceOf(stranger).call() == 0


def test_cumulative_budget(transfer_app):
    client, chain, keys, recipient, provider, tmp_path = transfer_app
    task = authorize(client, chain, recipient, budget=50, one_shot=False)
    provider.mutations = {"amount_base_units": "30000000"}
    request = dict(
        task_id=task["task_id"], revision=1, request_id="first-30", goal="Pay Alice 30 USDC."
    )
    first = client.post("/v1/transfers", json=request).raise_for_status().json()
    assert first["status"] == "CONFIRMED", first
    nonce = chain.w3.eth.get_transaction_count(Account.from_key(keys["relayer"]).address)
    second = (
        client.post("/v1/transfers", json={**request, "request_id": "second-30"})
        .raise_for_status()
        .json()
    )
    assert second["status"] == "REJECTED", second
    assert "TRANSFER_TASK_BUDGET" in second["temporal"]["reason_codes"]
    assert not second.get("signed") and not second.get("tx_hash")
    assert chain.w3.eth.get_transaction_count(Account.from_key(keys["relayer"]).address) == nonce
    assert chain.usdc.functions.balanceOf(recipient).call() == 30 * 10**6
    (tmp_path / "budget-evidence.json").write_text(
        json.dumps({"task": task, "approved": first, "rejected": second}, indent=1)
    )


@pytest.mark.skipif(
    __import__("os").environ.get("PACEVANT_TRANSFER_LIVE") != "1",
    reason="Opt-in real model API; writes remain LOCAL Anvil",
)
def test_real_model_local_transfer(transfer_app):
    from treasury_backend.modules.alignment.engine import TaskShield
    from treasury_backend.modules.alignment.provider import ChatProvider
    from treasury_backend.operations.env import read_env
    from treasury_backend.paths import ROOT

    client, chain, _, recipient, _, tmp_path = transfer_app
    control = client.app.state.control
    config = replace(
        ShieldConfig.from_values("FUJI", read_env(ROOT / ".env")),
        retries=0,
        fallbacks=(),
        context_chars=100000,
    )
    assert config.api_key
    control.shield.close()
    control.shield = TaskShield(control.store, config, ChatProvider(config), clock=control.clock)
    task = authorize(client, chain, recipient)
    result = (
        client.post(
            "/v1/transfers",
            json=dict(
                task_id=task["task_id"],
                revision=1,
                request_id="real-model-payment",
                goal="Pay Alice exactly 20 USDC for invoice 123.",
            ),
        )
        .raise_for_status()
        .json()
    )
    (tmp_path / "real-model-evidence.json").write_text(json.dumps(result, indent=1))
    assert result["status"] == "CONFIRMED", {
        "status": result["status"],
        "reasons": result.get("reason_codes"),
        "semantic": result.get("semantic"),
    }
    assert result["semantic"]["provider_metadata"]["provider"] == config.provider
    assert chain.usdc.functions.balanceOf(recipient).call() == 20 * 10**6


@pytest.mark.parametrize(
    "mutation",
    [
        "recipient",
        "amount",
        "policy_version",
        "deadline",
        "risk",
        "session",
        "task_budget",
        "token",
        "signature",
    ],
)
def test_onchain_transfer_guards(transfer_app, mutation):
    from treasury_contracts.transfer import TRANSFER_FIELDS, transfer_message

    client, chain, keys, recipient, provider, _ = transfer_app
    task = authorize(client, chain, recipient, budget=50, one_shot=False)
    result = (
        client.post(
            "/v1/transfers",
            json=dict(
                task_id=task["task_id"],
                revision=1,
                request_id="guard-base",
                goal="Pay Alice 20 USDC.",
            ),
        )
        .raise_for_status()
        .json()
    )
    assert result["status"] == "CONFIRMED", result
    a = {
        n: int(result["approval"][n]) if t == "uint256" else result["approval"][n]
        for n, t in TRANSFER_FIELDS
    }
    a["nonce"] += 1
    changes = {
        "recipient": ("recipient", Account.create().address),
        "amount": ("amount", 51 * 10**6),
        "policy_version": ("transferPolicyVersion", a["transferPolicyVersion"] + 1),
        "deadline": ("deadline", 1),
        "risk": ("riskDebitUsdE8", 0),
        "session": ("sessionId", "0x" + "00" * 32),
        "task_budget": ("taskBudget", 10 * 10**6),
        "token": ("token", chain.wavax.address),
    }
    if mutation in changes:
        k, v = changes[mutation]
        a[k] = v
    signer = Account.create().key if mutation == "signature" else keys["attestor"]
    signed = Account.sign_message(transfer_message(31337, chain.vault.address, a), signer)
    assert Web3.to_hex(signed.message_hash) == Web3.to_hex(
        chain.vault.functions.hashTransferApprovalV2(transfer_tuple(a)).call()
    )
    balance = chain.usdc.functions.balanceOf(recipient).call()
    with pytest.raises(Exception):
        chain.vault.functions.executeApprovedTransferV2(transfer_tuple(a), signed.signature).call(
            {"from": Account.from_key(keys["relayer"]).address}
        )
    assert not chain.vault.functions.usedNonce(a["nonce"]).call()
    assert chain.usdc.functions.balanceOf(recipient).call() == balance
