"""Execution module facade shared by in-process use cases and HTTP adapters."""

from collections import deque
from threading import Lock
from time import monotonic

from .chain import Chain
from .errors import PlaneError
from .relaying.relayer import Relayer
from .simulation.runner import Simulator
from .storage import Store
from .transaction.builder import Builder


class ExecutionService:
    def __init__(self, settings, chain=None):
        self.settings = settings
        self.store = Store(settings.data_dir)
        self.chain = chain
        self.gas_credit = None
        self._expensive_requests = deque()
        self._rate_lock = Lock()

    def start(self):
        self.chain = self.chain or Chain(self.settings)
        self.builder = Builder(self.chain, self.store)
        self.simulator = Simulator(self.chain, self.store)
        self.relayer = Relayer(self.chain, self.store)

    def expensive_rate(self):
        with self._rate_lock:
            now = monotonic()
            while self._expensive_requests and now - self._expensive_requests[0] >= 60:
                self._expensive_requests.popleft()
            if len(self._expensive_requests) >= 30:
                raise PlaneError("SIMULATION_RATE_LIMITED", "Simulation limit reached", 429, True)
            self._expensive_requests.append(now)

    def mutate(self, scope, key, body, fn):
        if key is None or not 1 <= len(key) <= 128:
            raise PlaneError(
                "INVALID_SCHEMA", "Idempotency-Key header (1..128 chars) is required", 400
            )
        with self.store.lock:
            return self.store.idempotent(scope, key, body, fn, refresh=scope == "execute")

    def build(self, proposal, key, *, workflow_id=None):
        result = self.mutate(
            "build", key, proposal.model_dump(), lambda: self.builder.build(proposal)
        )
        if self.gas_credit is not None and workflow_id:
            self.gas_credit.bind_build(workflow_id, result["build_id"])
        return result

    def simulate(self, request, key):
        self.expensive_rate()
        return self.mutate(
            "simulate",
            key,
            request.model_dump(),
            lambda: self.simulator.simulate(request.build_id, request.expected_policy_hash),
        )

    def preflight(self, request, key):
        self.expensive_rate()
        return self.mutate(
            "preflight-v2",
            key,
            request.model_dump(mode="json"),
            lambda: self.simulator.preflight_v2(request),
        )

    def execute(self, request, key):
        return self.mutate(
            "execute", key, request.model_dump(), lambda: self.relayer.execute(request)
        )
