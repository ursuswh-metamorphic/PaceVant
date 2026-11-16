import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from app.models import Mode

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures" / "mock"
DASHBOARD = ROOT / "apps" / "dashboard"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@dataclass(frozen=True, repr=False)
class Settings:
    mode: Mode = "MOCK"
    db: Path = ROOT / "data" / "control-plane-mock.sqlite3"
    mandate_file: Path = FIXTURES / "mandate.json"
    oracle_file: Path | None = None
    execution_url: str | None = None
    execution_token: str | None = None
    operator_token: str | None = None
    internal_token: str | None = None
    attestor_key: str | None = None

    @classmethod
    def from_env(cls):
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
            )
        }
        if mode != "MOCK":
            missing = [name for name, value in env.items() if not value and name != "DB"]
            if missing:
                raise RuntimeError("Missing PACEVANT settings: " + ", ".join(missing))
            url = urlsplit(env["B_URL"])
            if (
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
            tokens = [env[name] for name in ("B_TOKEN", "OPERATOR_TOKEN", "INTERNAL_TOKEN")]
            if min(map(len, tokens)) < 24 or len(set(tokens)) != 3:
                raise RuntimeError("Use separate service credentials of at least 24 characters")
        return cls(
            mode=mode,
            db=Path(env["DB"] or ROOT / "data" / f"control-plane-{mode.lower()}.sqlite3"),
            mandate_file=Path(env["MANDATE_FILE"] or FIXTURES / "mandate.json"),
            oracle_file=Path(env["ORACLE_FILE"]) if env["ORACLE_FILE"] else None,
            execution_url=env["B_URL"],
            execution_token=env["B_TOKEN"],
            operator_token=env["OPERATOR_TOKEN"],
            internal_token=env["INTERNAL_TOKEN"],
            attestor_key=env["ATTESTOR_KEY"],
        )
