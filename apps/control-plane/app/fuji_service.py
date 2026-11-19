"""Connection reuse, request throttling and short-lived Fuji snapshot caching."""

import copy
import time
from collections import deque
from threading import BoundedSemaphore, Lock

import httpx

from app.fuji_data import FujiReader
from app.fuji_rpc import HASH, FujiReadError, require_address


class FujiService:
    def __init__(self, client=None, clock=time.time, monotonic=time.monotonic):
        self.http = client or httpx.Client(
            trust_env=False,
            follow_redirects=False,
            limits=httpx.Limits(
                max_connections=4,
                max_keepalive_connections=4,
            ),
        )
        self.clock = clock
        self.monotonic = monotonic
        self.lock = Lock()
        self.slots = BoundedSemaphore(2)
        self.requests = deque()
        self.cache = {}

    def close(self):
        self.http.close()

    def snapshot(self, address, vault_address=None, tx_hash=None):
        holder = require_address(address)
        vault = require_address(vault_address) if vault_address else None
        if tx_hash is not None and not HASH.fullmatch(tx_hash):
            raise FujiReadError("INVALID_TRANSACTION_HASH")
        key = (holder, vault, tx_hash)
        now = self.monotonic()
        with self.lock:
            while self.requests and now - self.requests[0] >= 60:
                self.requests.popleft()
            if len(self.requests) >= 30:
                raise FujiReadError("FUJI_RATE_LIMITED")
            self.requests.append(now)
            # A cached snapshot retains its original block and observed_at.
            self.cache = {key: value for key, value in self.cache.items() if now - value[0] < 5}
            if key in self.cache:
                _, cached = self.cache[key]
                result = copy.deepcopy(cached)
                result["cached"] = True
                return result
        if not self.slots.acquire(blocking=False):
            raise FujiReadError("FUJI_READER_BUSY")
        try:
            result = FujiReader(self.http, now=int(self.clock())).snapshot(
                holder,
                vault_address=vault,
                tx_hash=tx_hash,
            )
            result["cached"] = False
            with self.lock:
                self.cache[key] = (self.monotonic(), copy.deepcopy(result))
            return result
        finally:
            self.slots.release()
