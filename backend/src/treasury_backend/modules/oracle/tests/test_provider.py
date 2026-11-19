import json
from types import SimpleNamespace

import pytest

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.oracle import JsonFilePriceProvider, source_hash
from treasury_backend.operations import refresh_oracle


def price(timestamp=1_700_000_000):
    return {
        "chain_id": 31337,
        "vault_address": "0x" + "11" * 20,
        "price_usdc_usd_e8": "100000000",
        "price_wavax_usd_e8": "2000000000",
        "price_source": "TRUSTED_TEST_ORACLE",
        "price_timestamp": timestamp,
    }


def test_external_writer_timestamp_and_file_are_preserved(tmp_path):
    file = tmp_path / "oracle.json"
    raw = json.dumps(price()).encode()
    file.write_bytes(raw)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"vault_address": price()["vault_address"]}))
    profile = SimpleNamespace(
        deployment=manifest,
        control_data=tmp_path,
        chain_id=31337,
        values={"TREASURY_ORACLE_MODE": "external"},
    )
    result = refresh_oracle(profile)
    assert result["timestamp"] == price()["price_timestamp"]
    assert file.read_bytes() == raw
    assert JsonFilePriceProvider(file).read().price_timestamp == price()["price_timestamp"]


@pytest.mark.parametrize(
    "body",
    [
        '{"chain_id":31337,"chain_id":43113}',
        json.dumps(price() | {"price_source": "UNREVIEWED_PROVIDER"}),
    ],
)
def test_provider_refuses_duplicate_or_unreviewed_source(tmp_path, body):
    file = tmp_path / "oracle.json"
    file.write_text(body)
    with pytest.raises(ControlError, match="UNVERIFIED_PRICE"):
        JsonFilePriceProvider(file).read()
    with pytest.raises(ValueError, match="Unsupported oracle source"):
        source_hash("UNREVIEWED_PROVIDER")
