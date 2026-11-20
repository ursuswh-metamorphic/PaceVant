from types import SimpleNamespace

import pytest

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.oracle import window


def clock(monkeypatch):
    elapsed = [0]
    monkeypatch.setattr(window.time, "time", lambda: 1000 + elapsed[0])
    monkeypatch.setattr(window.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(window.time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    return elapsed


def test_waits_for_new_round_without_restamping_old_values(monkeypatch):
    elapsed = clock(monkeypatch)
    old = SimpleNamespace(max_age_seconds=600, updated_at=450)
    fresh = SimpleNamespace(max_age_seconds=600, updated_at=1010)
    observed = []
    window.wait_for_round_window(lambda: SimpleNamespace(oracle_feeds=[fresh if elapsed[0] >= 10 else old]),
        required_seconds=300, on_wait=observed.append, max_wait=20)
    assert elapsed[0] == 10 and observed == [50]
    assert old.updated_at == 450


def test_unavailable_window_fails_closed_with_bounded_wait(monkeypatch):
    elapsed = clock(monkeypatch)
    with pytest.raises(ControlError, match="ORACLE_WINDOW_UNAVAILABLE"):
        window.wait_for_round_window(lambda: SimpleNamespace(oracle_feeds=[
            SimpleNamespace(max_age_seconds=600, updated_at=1)]), required_seconds=300,
            on_wait=lambda _: None, max_wait=20)
    assert elapsed[0] == 20
