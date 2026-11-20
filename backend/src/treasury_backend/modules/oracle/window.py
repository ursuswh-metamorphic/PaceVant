"""Wait for a genuine fresh round before opening a live approval window."""

import time

from treasury_backend.core.errors import ControlError


def wait_for_round_window(read, *, required_seconds, on_wait, max_wait=180):
    end = time.monotonic() + max_wait
    while True:
        try:
            price = read()
            if not price.oracle_feeds:
                raise ControlError("UNVERIFIED_PRICE", 503)
            now = int(time.time())
            remaining = min(f.max_age_seconds - (now - f.updated_at) for f in price.oracle_feeds)
        except ControlError as error:
            if error.code != "STALE_OR_UNVERIFIED_CHAINLINK_PRICE":
                raise
            remaining = -1
        if remaining >= required_seconds:
            return
        budget = end - time.monotonic()
        on_wait(remaining)
        if budget <= 0:
            raise ControlError("ORACLE_WINDOW_UNAVAILABLE", 503, retryable=True)
        time.sleep(min(10, budget))
