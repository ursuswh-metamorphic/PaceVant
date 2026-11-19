"""Key-free worker/runtime. Reads only observer settings, never attestor/relayer keys."""

import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import TypeAdapter

from treasury_backend.config.control import LOOPBACK
from treasury_backend.core.domain import Address
from treasury_backend.core.errors import ControlError
from treasury_backend.core.models import Mandate
from treasury_backend.modules.monitoring.service import OutcomeMonitor
from treasury_backend.modules.persistence import Store
from treasury_backend.modules.portfolio.observations import PortfolioReader
from treasury_backend.modules.workflows.client import RestExecutionClient


@dataclass(frozen=True, repr=False)
class ObserverSettings:
    mode: str
    db: Path
    chain_rpc_url: str
    execution_url: str
    execution_token: str
    operator_token: str
    relayer_address: str
    mandate_file: Path | None = None
    max_block_drift: int = 3

    @classmethod
    def from_env(cls):
        mode = os.environ.get("PACEVANT_MODE", "FUJI")
        if mode not in {"LOCAL", "FUJI"}:
            raise RuntimeError("Observer requires LOCAL or FUJI")
        names = ("DB", "CHAIN_RPC_URL", "B_URL", "B_TOKEN", "OPERATOR_TOKEN", "RELAYER_ADDRESS")
        values = {name: os.environ.get("PACEVANT_" + name) for name in names}
        if not all(values.values()):
            raise RuntimeError(
                "Observer requires DB, CHAIN_RPC_URL, B_URL, B_TOKEN, OPERATOR_TOKEN, RELAYER_ADDRESS"
            )
        parsed = urlsplit(values["B_URL"])
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") not in {"", "/execution"}
            or not (
                parsed.scheme == "https"
                or (parsed.scheme == "http" and parsed.hostname in LOOPBACK)
            )
        ):
            raise RuntimeError("Observer requires an HTTPS or loopback B origin")
        if min(
            len(values[name]) for name in ("B_TOKEN", "OPERATOR_TOKEN")
        ) < 24 or secrets.compare_digest(values["B_TOKEN"], values["OPERATOR_TOKEN"]):
            raise RuntimeError(
                "Observer requires separate service credentials of at least 24 characters"
            )
        mandate = os.environ.get("PACEVANT_MANDATE_FILE")
        return cls(
            mode,
            Path(values["DB"]),
            values["CHAIN_RPC_URL"],
            values["B_URL"],
            values["B_TOKEN"],
            values["OPERATOR_TOKEN"],
            TypeAdapter(Address).validate_python(values["RELAYER_ADDRESS"]),
            Path(mandate) if mandate else None,
        )


class ReadClient:
    """Intentionally exposes no execute/sign/deploy operation to the worker."""

    def __init__(self, client):
        self.settings, self.rpc = client.settings, client.rpc
        self.context = client.context
        self.observe = client.observe
        self.reconciliation = client.reconciliation
        self.submission_for_build = client.submission_for_build


class ObserverRuntime:
    def __init__(self, settings, clock=time.time):
        self.settings, self.clock = settings, clock
        self.store = Store(settings.db)
        self.http = httpx.Client(
            base_url=settings.execution_url,
            headers={"X-API-Key": settings.execution_token},
            timeout=httpx.Timeout(15, connect=3),
            trust_env=False,
            follow_redirects=False,
        )
        self.monitor = OutcomeMonitor(self.store, settings.mode, self.client, clock)

    def client(self, workflow_id, mandate):
        return ReadClient(RestExecutionClient(self.http, workflow_id, self.settings, self.store))

    def observe(self, vault):
        mandate = None
        if self.settings.mandate_file:
            mandate = Mandate.model_validate(
                json.loads(self.settings.mandate_file.read_text(encoding="utf-8"))
            )
            if mandate.vault_address != vault:
                raise ControlError("MANDATE_SCOPE_MISMATCH", 400)
        chain = 43113 if self.settings.mode == "FUJI" else 31337
        reader = PortfolioReader(self.settings.mode, self.settings.chain_rpc_url, clock=self.clock)
        version = self.store.history_version(chain, vault, self.settings.mode)
        value = reader.collect(
            vault,
            mandate=mandate,
            history_version=version,
            independent_reader=(
                lambda n: RestExecutionClient(
                    self.http, "observer", self.settings, self.store
                ).sdk.snapshot(n)
            )
            if mandate
            else None,
        )
        old = self.store.current_snapshot(self.settings.mode, chain, vault)
        if old:
            old_value = old["snapshot"]
            from treasury_contracts.readonly import readonly_web3

            w3 = readonly_web3(self.settings.chain_rpc_url, chain)
            try:
                if (
                    w3.to_hex(w3.eth.get_block(old_value["block_number"]).hash)
                    != old_value["block_hash"]
                ):
                    self.store.invalidate_snapshot(old_value["snapshot_id"], int(self.clock()))
            finally:
                w3.provider.close()
        self.store.save_snapshot(value)
        return value.model_dump()

    def close(self):
        self.http.close()
