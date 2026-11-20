from types import SimpleNamespace

import pytest

from treasury_backend.core.errors import ControlError
from treasury_backend.operations import contracts
from treasury_contracts.oracle import CIRCLE_USDC, SOURCE_HASH, WAVAX


@pytest.mark.parametrize("source,allow_start", [(SOURCE_HASH, True), ("0x" + "12" * 32, False)])
def test_unavailable_cache_does_not_fake_oracle_or_bypass_source_policy(
    tmp_path, monkeypatch, source, allow_start
):
    cached = tmp_path / "oracle.json"
    cached.write_text('"old real snapshot"')
    p = SimpleNamespace(
        network="fuji", values={"TREASURY_ORACLE_MODE": "chainlink"}, control_data=tmp_path
    )

    def fail(_):
        raise ControlError("STALE_OR_UNVERIFIED_CHAINLINK_PRICE")

    monkeypatch.setattr(contracts, "refresh_oracle", fail)
    args = (
        p,
        {"token_in": CIRCLE_USDC, "token_out": WAVAX},
        {"proof_policy": {"oracle_source_hash": source}},
    )
    if allow_start:
        result = contracts._prepare_oracle(*args)
        assert (
            result["status"] == "UNAVAILABLE"
            and result["signing_requires_fresh_direct_chainlink_reads"]
        )
    else:
        with pytest.raises(ControlError):
            contracts._prepare_oracle(*args)
    assert cached.read_text() == '"old real snapshot"'
