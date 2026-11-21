"""Measured public process events. Never an input to authorization or proof hashes."""

import re
from contextlib import contextmanager
from time import perf_counter


def public_value(value, depth=0):
    """Bounded structural redaction; retain public bytes32 hashes and references."""
    if depth > 8:
        return "DETAIL_LIMIT"
    if isinstance(value, dict):
        return {
            str(k): public_value(v, depth + 1)
            for k, v in list(value.items())[:80]
            if not re.search(r"private.?key|secret|password|api.?key|authorization|credential|signature|raw.?tx|raw.?transaction|endpoint", str(k), re.I)
        }
    if isinstance(value, (list, tuple)):
        return [public_value(v, depth + 1) for v in value[:64]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:6000]


class WorkflowTrace:
    def __init__(self, store, workflow_id, clock, progress=None):
        self.store, self.id, self.clock, self.progress = store, workflow_id, clock, progress
        self.current = None
        self.started = None
        self.check_times = {}
        self.buffer = None

    def emit(self, stage, kind, status, **values):
        event = (self.id, stage, public_value({"kind": kind, "status": status, **values}), self.clock())
        if self.buffer is not None:
            self.buffer.append(event)
        else:
            self.store.activity(*event)

    @contextmanager
    def buffered(self):
        """Signing holds a SQLite write transaction: publish observations after release."""
        self.buffer = []
        try:
            yield
        finally:
            events, self.buffer = self.buffer, None
            for event in events:
                self.store.activity(*event)

    def move(self, stage, *, inputs=None, input_refs=()):
        self.finish()
        self.current, self.started = stage, perf_counter()
        self.emit(stage, "started", "RUNNING", inputs=inputs or {}, input_refs=list(input_refs))
        if self.progress:
            self.progress(stage)

    def finish(self, status="PASS", **values):
        if self.current is not None:
            for stage, check_id, check_ref in list(self.check_times):
                if stage == self.current:
                    self.check(check_id, "UNKNOWN", stage=stage, check_ref=check_ref,
                               observed={"reason_code": values.get("reason_code", "CHECK_INCOMPLETE")})
            self.emit(self.current, "completed", status,
                      duration_ms=round((perf_counter() - self.started) * 1000, 3), **values)
            self.current, self.started = None, None

    def check(self, check_id, status, *, expected=None, observed=None, stage=None, **values):
        target = stage or self.current
        key = (target, check_id, values.get("check_ref"))
        if status == "RUNNING":
            self.check_times[key] = perf_counter()
        elif key in self.check_times:
            values["duration_ms"] = round((perf_counter() - self.check_times.pop(key)) * 1000, 3)
        self.emit(target, "check", status, check_id=check_id,
                  expected=expected, observed=observed, **values)

    def shield(self, value):
        status = value.pop("status")
        key = value.pop("check_id", "SHIELD_CHECK")
        check_ref = value.pop("check_ref", None)
        self.check(key, status, check_ref=check_ref, expected="ALIGNED", observed=value)

    def execution(self, stage, check_id, status, **values):
        # Execution owns its facts; this callback only publishes safe observations.
        if stage == "RECONCILIATION" and self.current == "RELAY":
            self.move(stage, input_refs=["OUTCOME", "ATTESTATION", "PROOF"])
        self.check(check_id, status, stage=stage, **values)

    def fail(self, code, signed=False):
        if self.current is None:
            return
        self.check("STAGE_STOP", "UNKNOWN" if signed else "FAIL",
                   observed={"reason_code": code, "signed": signed})
        self.finish("UNKNOWN" if signed else "FAIL", reason_code=code)
