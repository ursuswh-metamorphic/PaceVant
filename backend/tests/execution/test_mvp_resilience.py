"""Relevant availability/recovery checks only; never public sends or provider calls."""

from types import SimpleNamespace

import pytest

from treasury_backend.modules.execution.mvp import MvpChain
from treasury_backend.modules.workflows.readiness import inspect


def test_reference_keeps_owner_age_limit_even_if_feed_is_valid(monkeypatch):
    wavax = "0xd00ae08403b9bbb9124bb305c09058e32c39a48c"
    observed = SimpleNamespace(price_usdc_usd_e8="100000000", price_wavax_usd_e8="650000000",
        oracle_feeds=[SimpleNamespace(asset=wavax, updated_at=1000, max_age_seconds=600)],
        model_dump=lambda **_: {"source":"TEST_ROUND"})
    monkeypatch.setattr("treasury_backend.modules.oracle.chainlink.ChainlinkPriceProvider",
                        lambda *_: SimpleNamespace(read=lambda *_: observed))
    chain = SimpleNamespace(settings=SimpleNamespace(rpc_url="http://127.0.0.1:1"),
                            manifest=SimpleNamespace(treasury="test", wavax=wavax))
    assert MvpChain.reference(chain, 1, {"max_oracle_age":300}, 1200)[3] == 1300
    with pytest.raises(ValueError, match="ORACLE_WINDOW_UNAVAILABLE"):
        MvpChain.reference(chain, 1, {"max_oracle_age":300}, 1400)


def test_readiness_never_builds_signs_or_sends_and_shows_per_route_status(mvp):
    from treasury_backend.modules.persistence import Store
    from treasury_backend.modules.persistence.v3 import TreasuryStore

    store = TreasuryStore(Store(mvp["settings"].data_dir / "readiness-control.sqlite3"))
    execution = mvp["execution"]
    c = execution.context(mvp["session_id"])
    workflows = SimpleNamespace(execution=execution, store=store, clock=lambda: c["timestamp"])
    with execution.store.db() as db:
        before = db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    report = inspect(workflows)
    assert report["ready"], report
    assert next(x for x in report["operations"] if x["operation"] == "USDC_PAYMENT")["amount"] == "10000"
    assert not next(x for x in report["operations"] if x.get("direction") == "WAVAX_TO_USDC")["ready"]
    with execution.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] == before
    assert store.history() == []


def test_unpriced_dashboard_does_not_authorize_workflow(mvp, monkeypatch):
    execution = mvp["execution"]
    c = execution.display_context(mvp["session_id"])
    unpriced = c | {"nominal_prices":None, "price_intervals":None, "oracle_valid_until":0,
                    "oracle":{"status":"UNVERIFIED", "reason":"ORACLE_WINDOW_UNAVAILABLE"}}
    monkeypatch.setattr(execution, "display_context", lambda *_: unpriced)
    workflows = SimpleNamespace(execution=execution, store=SimpleNamespace(pending=lambda:[]),
                                clock=lambda:c["timestamp"])
    report = inspect(workflows)
    assert not report["ready"]
    assert all("ORACLE_REFRESH_REQUIRED" in op["reasons"] for op in report["operations"])
    assert unpriced["balances"] == c["balances"]
