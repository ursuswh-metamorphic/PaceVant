import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import TypeAdapter

from treasury_backend.config.planning import PlanningSettings
from treasury_backend.core.domain import Address
from treasury_backend.core.models import Mode
from treasury_backend.modules.alignment.provider import ShieldConfig
from treasury_backend.paths import ROOT

FIXTURES = ROOT / "fixtures" / "mock"
DASHBOARD = ROOT / "frontend"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@dataclass(frozen=True, repr=False)
class Settings:
    planning: PlanningSettings = field(default_factory=PlanningSettings)
    shield: ShieldConfig = field(default_factory=ShieldConfig)
    mode: Mode = "MOCK"
    db: Path = ROOT / "data" / "control-plane-mock.sqlite3"
    mandate_file: Path = FIXTURES / "mandate.json"
    oracle_file: Path | None = None
    execution_url: str | None = None
    execution_token: str | None = None
    operator_token: str | None = None
    internal_token: str | None = None
    attestor_key: str | None = None
    chain_rpc_url: str | None = None
    relayer_address: str | None = None
    max_block_drift: int = 3
    fuji_verification_rpc: str = "https://api.avax-test.network/ext/bc/C/rpc"
    cors_origins: tuple[str, ...] = ()
    serve_frontend: bool = True

    @classmethod
    def from_env(cls, *, require_execution_http=True):
        origins = tuple(
            value.strip().rstrip("/")
            for value in os.environ.get("PACEVANT_CORS_ORIGINS", "").split(",")
            if value.strip()
        )
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise RuntimeError("PACEVANT_CORS_ORIGINS must contain explicit HTTP(S) origins")
        serve_frontend = os.environ.get("PACEVANT_SERVE_FRONTEND", "true").lower()
        if serve_frontend not in {"true", "false"}:
            raise RuntimeError("PACEVANT_SERVE_FRONTEND must be true or false")
        mode = os.environ.get("PACEVANT_MODE", "MOCK")
        if mode not in ("MOCK", "LOCAL", "FUJI"):
            raise RuntimeError("PACEVANT_MODE must be MOCK, LOCAL or FUJI")
        env = {
            name: os.environ.get(f"PACEVANT_{name}")
            for name in (
                "DB",
                "MANDATE_FILE",
                "ORACLE_FILE",
                "B_URL",
                "B_TOKEN",
                "OPERATOR_TOKEN",
                "INTERNAL_TOKEN",
                "ATTESTOR_KEY",
                "CHAIN_RPC_URL",
                "RELAYER_ADDRESS",
            )
        }
        if mode != "MOCK":
            optional = {"DB"} if require_execution_http else {"DB", "B_URL", "B_TOKEN"}
            missing = [name for name, value in env.items() if not value and name not in optional]
            if missing:
                raise RuntimeError("Missing PACEVANT settings: " + ", ".join(missing))
            url = urlsplit(env["B_URL"] or "")
            if require_execution_http and (
                not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path not in ("", "/")
                or not (
                    url.scheme == "https" or (url.scheme == "http" and url.hostname in LOOPBACK)
                )
            ):
                raise RuntimeError(
                    "PACEVANT_B_URL must be an HTTPS origin or an HTTP loopback origin"
                )
            names = (
                ("B_TOKEN", "OPERATOR_TOKEN", "INTERNAL_TOKEN")
                if require_execution_http
                else ("OPERATOR_TOKEN", "INTERNAL_TOKEN")
            )
            tokens = [env[name] for name in names]
            if min(map(len, tokens)) < 24 or len(set(tokens)) != len(tokens):
                raise RuntimeError("Use separate service credentials of at least 24 characters")
            rpc = urlsplit(env["CHAIN_RPC_URL"])
            if (
                not rpc.hostname
                or rpc.username
                or rpc.password
                or rpc.fragment
                or (mode == "LOCAL" and rpc.hostname not in LOOPBACK)
                or (
                    rpc.scheme != "https"
                    and not (rpc.scheme == "http" and rpc.hostname in LOOPBACK)
                )
            ):
                raise RuntimeError("Use a loopback RPC for LOCAL and HTTPS for FUJI")
            TypeAdapter(Address).validate_python(env["RELAYER_ADDRESS"])
        max_drift = int(os.environ.get("PACEVANT_MAX_BLOCK_DRIFT", "3"))
        if not 1 <= max_drift <= 120:
            raise RuntimeError("PACEVANT_MAX_BLOCK_DRIFT must be 1..120")
        verification_rpc = os.environ.get(
            "PACEVANT_FUJI_VERIFICATION_RPC", "https://api.avax-test.network/ext/bc/C/rpc"
        )
        parsed_verification = urlsplit(verification_rpc)
        if (
            not parsed_verification.hostname
            or parsed_verification.username
            or parsed_verification.password
            or parsed_verification.fragment
            or not (
                parsed_verification.scheme == "https"
                or (
                    parsed_verification.scheme == "http"
                    and parsed_verification.hostname in LOOPBACK
                )
            )
        ):
            raise RuntimeError("PACEVANT_FUJI_VERIFICATION_RPC must use HTTPS or loopback HTTP")
        return cls(
            planning=PlanningSettings.from_values(os.environ),
            shield=ShieldConfig.from_env(mode),
            cors_origins=origins,
            serve_frontend=serve_frontend == "true",
            max_block_drift=max_drift,
            fuji_verification_rpc=verification_rpc,
            mode=mode,
            db=Path(env["DB"] or ROOT / "data" / f"control-plane-{mode.lower()}.sqlite3"),
            mandate_file=Path(env["MANDATE_FILE"] or FIXTURES / "mandate.json"),
            oracle_file=Path(env["ORACLE_FILE"]) if env["ORACLE_FILE"] else None,
            execution_url=env["B_URL"],
            execution_token=env["B_TOKEN"],
            operator_token=env["OPERATOR_TOKEN"],
            internal_token=env["INTERNAL_TOKEN"],
            attestor_key=env["ATTESTOR_KEY"],
            chain_rpc_url=env["CHAIN_RPC_URL"],
            relayer_address=env["RELAYER_ADDRESS"],
        )
