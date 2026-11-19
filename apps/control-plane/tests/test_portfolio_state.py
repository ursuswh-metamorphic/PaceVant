import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from eth_abi import encode
from fastapi.testclient import TestClient
from hexbytes import HexBytes
from web3 import Web3

from app.api import create_app
from app.errors import ControlError
from app.models import Mandate
from app.monitoring.runtime import ObserverSettings, ReadClient
from app.monitoring.service import OutcomeMonitor
from app.orchestration.mock import MockExecutionClient
from app.portfolio.observations import PortfolioReader, observed, verify_snapshot_hash
from app.settings import FIXTURES, Settings
from app.storage import Store
from treasury_contracts.models import BuiltTransaction, ExecutionReconciliation
from treasury_contracts.readonly import ReadError, ReadOnlyProvider

NOW = 2_000_000_000
BLOCK_HASH = "0x" + "ab" * 32


@pytest.fixture
def mandate():
    return Mandate.model_validate_json((FIXTURES / "mandate.json").read_text()).model_copy(
        update={"chain_id": 31337}
    )


class RpcFixture:
    def __init__(self, mandate):
        self.mandate, self.calls = mandate, []
        self.chain, self.block, self.timestamp = 31337, 123, NOW
        self.changed = self.unavailable = self.wrong_decimals = False
        self.headers = 0

    def respond(self, request):
        body = json.loads(request.content)
        method, args = body["method"], body["params"]
        self.calls.append((method, args))
        if method == "eth_chainId":
            result = hex(self.chain)
        elif method == "web3_clientVersion":
            result = "anvil/v1.7.1"
        elif method == "eth_getBlockByNumber":
            self.headers += 1
            result = {
                "number": hex(self.block),
                "timestamp": hex(self.timestamp),
                "hash": "0x" + "cd" * 32 if self.changed and self.headers > 1 else BLOCK_HASH,
            }
        elif method == "eth_getBalance":
            result = hex(123456789012345678901234567890)
        elif method == "eth_getCode":
            result = "0x6000"
        elif method == "eth_call":
            call = args[0]
            selector = call["data"][:10]
            mapping = {
                "usdc()": ("address", self.mandate.token_in),
                "wavax()": ("address", self.mandate.token_out),
                "activePolicyHash()": ("bytes32", bytes.fromhex(self.mandate.policy_hash[2:])),
                "policyVersion()": ("uint256", 1),
                "owner()": ("address", self.mandate.owner),
                "attestor()": ("address", "0x" + "12" * 20),
                "policyActive()": ("bool", True),
                "paused()": ("bool", False),
                "decimals()": (
                    "uint8",
                    7
                    if self.wrong_decimals
                    else 6
                    if call["to"].lower() == self.mandate.token_in
                    else 18,
                ),
                "balanceOf(address)": (
                    "uint256",
                    0 if call["to"].lower() == self.mandate.token_in else 10**30,
                ),
            }
            if self.unavailable and selector == Web3.to_hex(
                Web3.keccak(text="balanceOf(address)")[:4]
            ):
                return httpx.Response(
                    200, json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -1}}
                )
            kind, value = next(
                v for k, v in mapping.items() if selector == Web3.to_hex(Web3.keccak(text=k)[:4])
            )
            result = "0x" + encode([kind], [value]).hex()
        else:
            raise AssertionError(method)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    def collect(self, **kwargs):
        with httpx.Client(transport=httpx.MockTransport(self.respond)) as client:
            return PortfolioReader(
                "LOCAL", "http://127.0.0.1:8545", clock=lambda: NOW, client=client
            ).collect(
                self.mandate.vault_address, mandate=self.mandate, include_oracles=False, **kwargs
            )


def test_pinned_native_exact_tokens_hash_and_unknown_price(mandate):
    rpc = RpcFixture(mandate)
    value = rpc.collect()
    assert value.verification_status == "VERIFIED"
    assert value.assets[0].balance_base_units == "123456789012345678901234567890"
    assert value.assets[1].balance_base_units == "0"
    assert value.assets[2].balance_base_units == str(10**30)
    assert not value.authorization_eligible and value.price_observations == []
    assert value.block_hash == BLOCK_HASH and verify_snapshot_hash(value)
    assert value == RpcFixture(mandate).collect()
    for method, args in rpc.calls:
        if method in {"eth_getBalance", "eth_call", "eth_getCode"}:
            assert args[-1] == hex(123)
    assert not verify_snapshot_hash(value.model_copy(update={"history_version": 7}))


@pytest.mark.parametrize(
    "failure", ["chain", "reorg", "stale", "decimals", "balance", "identity", "independent"]
)
def test_observation_negative_sources(mandate, failure):
    rpc = RpcFixture(mandate)
    if failure == "chain":
        rpc.chain = 1
        with pytest.raises(ControlError, match="CHAIN_MISMATCH"):
            rpc.collect()
        return
    if failure == "reorg":
        rpc.changed = True
        with pytest.raises(ControlError, match="BLOCK_HASH_MISMATCH"):
            rpc.collect()
        return
    if failure == "stale":
        rpc.timestamp = NOW - 61
    if failure == "decimals":
        rpc.wrong_decimals = True
    if failure == "balance":
        rpc.unavailable = True
    if failure == "identity":
        # Independent owner mandate expects another input contract.
        original = rpc.mandate
        rpc.mandate = original.model_copy(update={"token_in": "0x" + "88" * 20})
        reader = PortfolioReader(
            "LOCAL",
            "http://localhost",
            clock=lambda: NOW,
            client=httpx.Client(transport=httpx.MockTransport(rpc.respond)),
        )
        value = reader.collect(original.vault_address, mandate=original, include_oracles=False)
        assert "TOKEN_IDENTITY_MISMATCH" in value.reason_codes
        reader.client.close()
        return
    remote = {
        "chain_id": 31337,
        "vault_address": mandate.vault_address,
        "block_number": 123,
        "block_hash": BLOCK_HASH,
        "timestamp": NOW,
        "policy_hash": mandate.policy_hash,
        "usdc_base_units": "1",
        "wavax_base_units": str(10**30),
    }
    value = rpc.collect(independent_reader=(lambda n: remote) if failure == "independent" else None)
    assert value.verification_status == "INCOMPLETE" and not value.authorization_eligible
    if failure == "balance":
        assert value.assets[1].balance_base_units is None
    if failure == "decimals":
        assert "TOKEN_DECIMALS_MISMATCH" in value.assets[1].reason_codes
    if failure == "independent":
        assert value.independent_balance_check == "MISMATCH"


@pytest.mark.parametrize(
    "method",
    [
        "eth_sendRawTransaction",
        "eth_sendTransaction",
        "eth_sign",
        "personal_sign",
        "anvil_setBalance",
        "evm_mine",
        "eth_estimateGas",
    ],
)
def test_read_transport_never_allows_mutation(method):
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: pytest.fail("Forbidden RPC left process"))
    ) as client:
        provider = ReadOnlyProvider("https://fuji.invalid", 43113, client=client)
        with pytest.raises(ReadError, match="READONLY_METHOD_FORBIDDEN"):
            provider.make_request(method, [])


@pytest.mark.parametrize(
    "response",
    [
        [],
        {"jsonrpc": "1.0", "id": 1, "result": "0xa869"},
        {"jsonrpc": "2.0", "id": 500, "result": "0xa869"},
    ],
)
def test_malformed_rpc_fails_closed(response):
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response))
    ) as client:
        provider = ReadOnlyProvider("https://fuji.invalid", 43113, client=client)
        with pytest.raises(ReadError):
            provider.make_request("eth_chainId", [])


def test_sqlite_immutable_snapshots_scope_and_invalidation(tmp_path, mandate):
    db = Store(tmp_path / "legacy.sqlite3")
    value = RpcFixture(mandate).collect()
    db.save_snapshot(value)
    db.save_snapshot(value)
    assert len(db.scoped_snapshots("LOCAL", 31337, mandate.vault_address)) == 1
    assert not db.scoped_snapshots("FUJI", 31337, mandate.vault_address)
    assert not db.scoped_snapshots("LOCAL", 31337, "0x" + "66" * 20)
    with (
        pytest.raises(sqlite3.IntegrityError, match="immutable"),
        db.connection(write=True) as conn,
    ):
        conn.execute("UPDATE portfolio_snapshots SET body='{}'")
    db.invalidate_snapshot(value.snapshot_id, NOW + 1)
    assert db.current_snapshot("LOCAL", 31337, mandate.vault_address) is None
    assert db.snapshot_record(value.snapshot_id)["state"] == "INVALIDATED"
    assert Store(db.path).snapshot_record(value.snapshot_id)["snapshot"] == value.model_dump()


@pytest.fixture
def pending(tmp_path, monkeypatch):
    original = MockExecutionClient.execution
    monkeypatch.setattr(
        MockExecutionClient,
        "execution",
        lambda self, tx: original(self, tx).model_copy(update={"status": "PENDING"}),
    )
    settings = replace(
        Settings(),
        db=tmp_path / "monitor.sqlite3",
        operator_token="operator-credential-long-enough",
    )
    with TestClient(create_app(settings, lambda: NOW)) as api:
        api.headers["Authorization"] = "Bearer " + settings.operator_token
        result = api.post(
            "/v1/workflows/start",
            json={
                "scenario": "normal_swap",
                "goal": "Buy WAVAX with 500 USDC",
                "mandate_id": "mandate_demo",
            },
        )
        assert result.status_code == 200, result.text
        control = api.app.state.control
        workflow = control.store.workflow(result.json()["workflow_id"])
        id_ = next(e["decision_id"] for e in workflow["timeline"] if e["stage"] == "SUBMITTED")
        client = control.mock_clients[workflow["workflow_id"]]
        monkeypatch.setattr(MockExecutionClient, "execution", original)
        yield api, control, id_, client


def test_restart_duplicate_worker_and_gas_once(pending):
    api, control, id_, client = pending
    restarted = OutcomeMonitor(Store(control.store.path), "MOCK", lambda *_: client, lambda: NOW)
    value = restarted.process(id_, force=True)
    assert value["state"] == "CONFIRMED", value
    version = control.store.history_version(
        client.mandate.chain_id, client.mandate.vault_address, "MOCK"
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: restarted.process(id_, force=True), range(4)))
    assert all(r["state"] in {"CONFIRMED", "BUSY_OR_NOT_DUE"} for r in results)
    assert (
        control.store.history_version(client.mandate.chain_id, client.mandate.vault_address, "MOCK")
        == version
        == 1
    )
    assert control.store.history_version(client.mandate.chain_id, "0x" + "66" * 20, "MOCK") == 0
    assert control.store.execution_gas_spent(
        client.mandate.chain_id, client.mandate.vault_address, NOW // 86400, "MOCK"
    ) == int(value["verification"]["gas_cost_wei"])
    with control.store.connection() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM portfolio_links WHERE phase='POST'").fetchone()[0]
            == 1
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM events WHERE stage='CONFIRMED'").fetchone()[0] == 1
        )
    path = f"/v1/reconciliations/{id_}"
    assert api.get(path).json()["outcome"]["post_snapshot_id"] == value["post_snapshot_id"]
    assert api.get(path, headers={"Authorization": ""}).status_code == 401
    params = {"chain_id": client.mandate.chain_id, "vault_address": client.mandate.vault_address}
    assert (
        api.get("/v1/history/transactions", params=params).json()["transactions"][0]["state"]
        == "CONFIRMED"
    )
    assert api.get("/v1/portfolio/current", params=params).json()["authorization_eligible"] is False


def test_outage_then_resume_without_submission(pending, monkeypatch):
    _, control, id_, client = pending
    monitor = OutcomeMonitor(control.store, "MOCK", lambda *_: client, lambda: NOW)
    original = client.execution
    monkeypatch.setattr(client, "execute", lambda *_: pytest.fail("Monitor must not submit"))
    monkeypatch.setattr(
        client, "execution", lambda *_: (_ for _ in ()).throw(ControlError("RPC_OUTAGE", 503))
    )
    assert monitor.process(id_, force=True)["state"] == "UNAVAILABLE"
    assert control.store.outcome_projection(id_) is None
    monkeypatch.setattr(client, "execution", original)
    assert monitor.process(id_, force=True)["state"] == "CONFIRMED"
    assert control.store.monitor_job(id_)["attempts"] >= 3


def test_external_balance_delta_remains_inconclusive(pending):
    _, control, id_, client = pending
    client.usdc += 5
    value = control.monitor.process(id_, force=True)
    assert value["state"] == "RECEIPT_MISMATCH"
    assert value["attribution_status"] == "INCONCLUSIVE_EXTERNAL_DELTA"
    assert list(value["unattributed_balance_deltas"].values()) == ["5"]


def test_reorg_invalidates_projection_then_recovers_without_double_gas(pending, monkeypatch):
    _, control, id_, mock = pending
    initial = control.monitor.process(id_, force=True)
    _, bundle = control.store.decision(decision_id=id_)
    built = BuiltTransaction.model_validate(bundle["build"])
    old_report = ExecutionReconciliation.model_validate(initial["verification"])
    old_post = control.store.snapshot_record(initial["post_snapshot_id"])["snapshot"]
    replacement = "0x" + "dd" * 32
    canonical = (
        {built.build_block: mock.block_hash(built.build_block)}
        if hasattr(built, "build_block")
        else {}
    )
    canonical[old_report.block_number] = replacement

    class Eth:
        def get_block(self, n):
            return SimpleNamespace(hash=HexBytes(canonical.get(n, mock.block_hash(n))))

    monkeypatch.setattr(
        "app.monitoring.service.readonly_web3",
        lambda *_: SimpleNamespace(eth=Eth(), provider=SimpleNamespace(close=lambda: None)),
    )
    fake = SimpleNamespace(settings=SimpleNamespace(chain_rpc_url="http://localhost"))
    fake.reconciliation = lambda *_args, **_kwargs: old_report.model_copy(
        update={"verification_status": "PENDING", "canonical": False, "receipt_status": "PENDING"}
    )
    monitor = OutcomeMonitor(control.store, "MOCK", lambda *_: fake, lambda: NOW + 10)
    changed = monitor.process(id_, force=True)
    assert changed["state"] == "RECEIPT_MISMATCH", changed
    assert changed["verification"]["verification_status"] == "REORGED"
    assert control.store.snapshot_record(initial["post_snapshot_id"])["state"] == "INVALIDATED"
    scope = (built.chain_id, built.vault_address, NOW // 86400, "MOCK")
    assert control.store.execution_gas_spent(*scope) == 0
    fake.reconciliation = lambda *_args, **_kwargs: old_report.model_copy(
        update={"block_hash": replacement}
    )
    fields = {k: v for k, v in old_post.items() if k not in {"snapshot_id", "content_hash"}}
    fields["block_hash"] = replacement
    fake.observe = lambda *_args, **_kwargs: observed(fields)
    recovered = monitor.process(id_, force=True)
    assert recovered["state"] == "CONFIRMED", recovered
    assert recovered["post_snapshot_id"] != initial["post_snapshot_id"]
    assert control.store.execution_gas_spent(*scope) == int(old_report.gas_cost_wei)
    assert control.store.history_version(built.chain_id, built.vault_address, "MOCK") == 3


def test_reverted_swap_has_zero_token_movement_but_operational_gas(pending):
    _, control, id_, client = pending
    _, bundle = control.store.decision(decision_id=id_)
    balances = bundle["chain_balances"]
    client.usdc, client.wavax = int(balances["usdc_base_units"]), int(balances["wavax_base_units"])
    tx = control.store.monitor_job(id_)["tx_hash"]
    receipt = client.execution(tx).model_copy(
        update={
            "status": "REVERTED",
            "event_refs": [],
            "actual_token_in_delta_base_units": "0",
            "actual_token_out_delta_base_units": "0",
        }
    )
    value = control.monitor.process(id_, force=True, client=client, receipt=receipt)
    assert value["state"] == "REVERTED", value
    assert value["verification"]["gas_payer_role"] == "RELAYER"
    assert value["verification"]["token_out_delta_base_units"] == "0"
    assert int(value["verification"]["gas_cost_wei"]) > 0


@pytest.mark.parametrize(
    "status,price",
    [
        ("STALE", "100000000"),
        ("UNAVAILABLE", None),
        ("UNVERIFIED", None),
        ("WITHIN_HEARTBEAT", "100000000"),
    ],
)
def test_fuji_prices_remain_observation_only_even_when_returned(
    mandate, monkeypatch, status, price
):
    rpc = RpcFixture(
        mandate.model_copy(
            update={"chain_id": 43113, "token_in": "0xb6076c93701d6a07266c31066b298aec6dd65c2d"}
        )
    )
    rpc.chain = 43113

    def source(*args):
        return {
            "provider": "CHAINLINK",
            "pair": "USDC/USD",
            "contract": "0x" + "12" * 20,
            "price_usd_e8": price,
            "updated_at": NOW - 120,
            "status": status,
        }

    monkeypatch.setattr("app.portfolio.observations.chainlink", source)
    with httpx.Client(transport=httpx.MockTransport(rpc.respond)) as client:
        value = PortfolioReader(
            "FUJI", "https://fuji.invalid", clock=lambda: NOW, client=client
        ).collect(rpc.mandate.vault_address, mandate=rpc.mandate)
    assert not value.authorization_eligible
    assert all(
        not p.valuation_eligible and not p.authorization_eligible for p in value.price_observations
    )
    assert "ORACLE_TOKEN_IDENTITY_MISMATCH" in value.price_observations[0].reason_codes
    assert "PRICE_NOT_FRESH_FOR_RISK" in value.price_observations[0].reason_codes


def test_worker_capability_and_settings_never_read_keys(monkeypatch):
    for name, value in {
        "MODE": "FUJI",
        "DB": "observer.sqlite3",
        "CHAIN_RPC_URL": "https://fuji.invalid",
        "B_URL": "http://localhost:8001",
        "B_TOKEN": "b" * 24,
        "OPERATOR_TOKEN": "o" * 24,
        "RELAYER_ADDRESS": "0x" + "12" * 20,
    }.items():
        monkeypatch.setenv("PACEVANT_" + name, value)
    original = type(__import__("os").environ).get

    def guarded(self, key, *args):
        assert not any(part in key for part in ("PRIVATE_KEY", "ATTESTOR_KEY"))
        return original(self, key, *args)

    monkeypatch.setattr(type(__import__("os").environ), "get", guarded)
    settings = ObserverSettings.from_env()
    assert settings.mode == "FUJI"
    assert not any(hasattr(ReadClient, name) for name in ("execute", "sign", "deploy", "attest"))


def test_unknown_submission_recovery_reads_journal_without_retry(pending, monkeypatch):
    from treasury_contracts.models import ExecutionSubmission

    _, control, id_, client = pending
    job = control.store.monitor_job(id_)
    with control.store.connection(write=True) as conn:
        conn.execute("UPDATE monitor_jobs SET tx_hash=NULL WHERE decision_id=?", (id_,))
    monkeypatch.setattr(
        client, "execute", lambda *_: pytest.fail("A monitor rebroadcast a transaction")
    )
    client.submission_for_build = lambda _: None
    assert control.monitor.process(id_, force=True)["state"] == "UNKNOWN_SUBMISSION"
    client.submission_for_build = lambda _: ExecutionSubmission(
        tx_hash=job["tx_hash"], status="PENDING"
    )
    assert control.monitor.process(id_, force=True)["state"] == "CONFIRMED"
    assert control.store.monitor_job(id_)["tx_hash"] == job["tx_hash"]


def test_expired_unknown_hash_keeps_reservation_and_never_submits(pending, monkeypatch):
    _, control, id_, client = pending
    with control.store.connection(write=True) as conn:
        conn.execute("UPDATE monitor_jobs SET tx_hash=NULL WHERE decision_id=?", (id_,))
    monkeypatch.setattr(
        client, "execute", lambda *_: pytest.fail("Expired monitor tried submission")
    )
    client.submission_for_build = lambda _: None
    monitor = OutcomeMonitor(control.store, "MOCK", lambda *_: client, lambda: NOW + 3600)
    assert monitor.process(id_, force=True)["state"] == "EXPIRED_UNESTABLISHED"
    assert control.store.outcome_projection(id_) is None
    with control.store.connection() as conn:
        assert (
            conn.execute("SELECT state FROM attestations WHERE decision_id=?", (id_,)).fetchone()[0]
            == "SUBMITTED"
        )


def test_crashed_lease_expires_without_stale_owner_releasing_new_claim(pending):
    _, control, id_, _ = pending
    assert control.store.claim_monitor(id_, "old", NOW, force=True)
    assert control.store.claim_monitor(id_, "new", NOW + 1, force=True) is None
    assert control.store.claim_monitor(id_, "new", NOW + 301, force=True)
    control.store.release_monitor(id_, "old", NOW + 302, "UNAVAILABLE", {})
    assert control.store.monitor_job(id_)["lease"] == "new"


def test_rpc_budget_and_size_are_bounded():
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 1_048_577))
    ) as client:
        provider = ReadOnlyProvider("https://fuji.invalid", 43113, client=client)
        with pytest.raises(ReadError, match="READONLY_RESPONSE_TOO_LARGE"):
            provider.make_request("eth_chainId", [])
    ticks = iter([0, 26])
    provider = ReadOnlyProvider("https://fuji.invalid", 43113, monotonic=lambda: next(ticks))
    try:
        with pytest.raises(ReadError, match="READONLY_TIMEOUT"):
            provider.make_request("eth_chainId", [])
    finally:
        provider.close()


def test_observer_api_has_no_authorization_or_execution_routes(tmp_path):
    from app.monitoring.__main__ import create_observer_app

    settings = ObserverSettings(
        "LOCAL",
        tmp_path / "observe.sqlite3",
        "http://localhost:8545",
        "http://localhost:8001",
        "b" * 24,
        "o" * 24,
        "0x" + "12" * 20,
    )
    app = create_observer_app(settings)
    assert not any("execute" in route.path or "attest" in route.path for route in app.routes)
    with TestClient(app) as api:
        params = {"chain_id": 31337, "vault_address": "0x" + "11" * 20}
        assert api.get("/v1/portfolio/current", params=params).status_code == 401
        api.headers["Authorization"] = "Bearer " + "o" * 24
        assert api.get("/v1/portfolio/current", params=params).json()["portfolio"] is None
        assert api.get("/v1/portfolio/current", params={**params, "chain_id": 1}).status_code == 400
        assert api.get("/v1/portfolio/history", params={**params, "limit": 1000}).status_code == 400
