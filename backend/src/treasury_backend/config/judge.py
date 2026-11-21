"""Bounded judge settings; public signing needs explicit activation and authority."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from treasury_backend.modules.alignment.provider import ShieldConfig
from treasury_backend.paths import ROOT


@dataclass(frozen=True)
class JudgeSettings:
    data_dir: Path = ROOT / "data/judge"
    rpc_url: str = "https://api.avax-test.network/ext/bc/C/rpc"
    enabled: bool = False
    daily_limit: int = 6
    ip_hourly_limit: int = 6
    global_daily_limit: int = 30
    timeout_seconds: int = 240
    wait_oracle_seconds: int = 45
    secure_cookie: bool = True
    visitor_session_seconds: int = 30 * 86400
    execution_mode: str = 'ANVIL_FORK'
    manifest_file: Path | None = None

    @classmethod
    def from_env(cls):
        def flag(name, default):
            value = os.environ.get(name, default)
            if value not in {"0", "1"}:
                raise ValueError("INVALID_JUDGE_FLAG")
            return value == "1"

        def integer(name, default, low, high):
            value = int(os.environ.get(name, default))
            if not low <= value <= high:
                raise ValueError("INVALID_JUDGE_LIMIT")
            return value

        for name in ("B_FUJI_OWNER_PRIVATE_KEY", "B_OWNER_PRIVATE_KEY", "DEPLOYER_PRIVATE_KEY"):
            if os.environ.get(name):
                raise ValueError("OWNER_KEY_FORBIDDEN_IN_SERVING")
        rpc_url = os.environ.get("PACEVANT_JUDGE_RPC_URL", cls.rpc_url)
        parsed = urlsplit(rpc_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("INVALID_JUDGE_RPC_URL")
        mode=os.environ.get('PACEVANT_JUDGE_EXECUTION_MODE','ANVIL_FORK')
        if mode not in {'ANVIL_FORK','REAL_FUJI_EXECUTION'}:
            raise ValueError('INVALID_JUDGE_EXECUTION_MODE')
        if mode=='REAL_FUJI_EXECUTION' and os.environ.get('PACEVANT_MVP_LIVE_ENABLED')!='1':
            raise ValueError('MVP_PUBLIC_EXECUTION_NOT_AUTHORIZED')
        return cls(data_dir=Path(os.environ.get("PACEVANT_JUDGE_DATA_DIR", str(cls.data_dir))), rpc_url=rpc_url,
            execution_mode=mode,manifest_file=Path(os.environ['PACEVANT_MVP_MANIFEST_FILE']) if os.environ.get('PACEVANT_MVP_MANIFEST_FILE') else None,
            enabled=flag("PACEVANT_JUDGE_ENABLED", "0"),
            daily_limit=integer("PACEVANT_JUDGE_VISITOR_DAILY_LIMIT", 6, 1, 30),
            ip_hourly_limit=integer("PACEVANT_JUDGE_IP_HOURLY_LIMIT", 6, 1, 60),
            global_daily_limit=integer("PACEVANT_JUDGE_GLOBAL_DAILY_LIMIT", 30, 1, 200),
            timeout_seconds=integer("PACEVANT_JUDGE_TIMEOUT_SECONDS", 240, 60, 900 if mode=='REAL_FUJI_EXECUTION' else 360),
            wait_oracle_seconds=integer("PACEVANT_JUDGE_ORACLE_WAIT_SECONDS", 45, 0, 720 if mode=='REAL_FUJI_EXECUTION' else 90),
            secure_cookie=flag("PACEVANT_JUDGE_SECURE_COOKIE", "1"),
            visitor_session_seconds=integer("PACEVANT_JUDGE_SESSION_SECONDS", 30*86400, 86400, 90*86400))

    def configured(self):
        try:
            if self.execution_mode=='REAL_FUJI_EXECUTION':
                import json

                from eth_account import Account

                from treasury_contracts.mvp import MvpManifest

                if not self.manifest_file or os.environ.get('PACEVANT_MVP_LIVE_ENABLED')!='1':
                    return False
                manifest=MvpManifest.model_validate(json.loads(self.manifest_file.read_text(encoding='utf-8')))
                manifest.verify_owner()
                if manifest.environment!='REAL_FUJI_EXECUTION':
                    return False
                if Account.from_key(os.environ['PACEVANT_ATTESTOR_KEY']).address.lower()!=manifest.attestor or Account.from_key(os.environ['B_FUJI_RELAYER_PRIVATE_KEY']).address.lower()!=manifest.relayer:
                    return False
            shield = ShieldConfig.from_env("FUJI")
            return self.enabled and shield.mode in {"wallet_pipeline", "wallet_hardened"} and any(
                item.api_key for item in (shield, *shield.fallbacks))
        except (ValueError, TypeError, KeyError, OSError):
            return False
