import json
from types import SimpleNamespace

import pytest

from treasury_backend.operations import fuji_demo
from treasury_backend.operations.errors import OpsError


@pytest.mark.parametrize("fresh_after_wait", [True, False])
def test_demo_waits_for_real_round_headroom_before_starting(tmp_path, monkeypatch, fresh_after_wait):
    manifest = tmp_path / "deployment.json"
    manifest.write_text(json.dumps({"vault_address": "0x" + "12" * 20}))
    p = SimpleNamespace(network="fuji", deployment=manifest,
                        values={"TREASURY_ORACLE_MODE": "chainlink", "TREASURY_APPROVAL_TTL_SECONDS": "300"},
                        rpc="https://fuji.invalid")
    elapsed, reads = [0], []
    monkeypatch.setattr(fuji_demo.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(fuji_demo.time, "time", lambda: 1000)
    monkeypatch.setattr(fuji_demo.time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))

    def read():
        updated = 990 if elapsed[0] and fresh_after_wait else 500
        reads.append(updated)
        return SimpleNamespace(oracle_feeds=[SimpleNamespace(max_age_seconds=600, updated_at=updated)])

    monkeypatch.setattr(fuji_demo, "ChainlinkPriceProvider", lambda *_: SimpleNamespace(read=read))
    if fresh_after_wait:
        fuji_demo.wait_for_oracle_window(p, wait_seconds=15)
        assert reads == [500, 990] and elapsed[0] == 15
    else:
        with pytest.raises(OpsError, match="insufficient remaining freshness"):
            fuji_demo.wait_for_oracle_window(p, wait_seconds=15)
        assert reads == [500, 500]
