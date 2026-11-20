from pathlib import Path
from typing import Literal
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from treasury_contracts.toolchain import foundry_binary

from treasury_backend.paths import ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="B_", env_file=ROOT / ".env", extra="ignore"
    )
    mode: Literal["local", "fuji"] = "local"
    rpc_url: str = ""
    fork_rpc_url: str = ""
    deployment_file: Path | None = None
    data_dir: Path | None = None
    api_key: SecretStr = SecretStr("")
    relayer_private_key: SecretStr = SecretStr("")
    attestor_address: str = ""
    local_rpc_url: str = "http://127.0.0.1:8545"
    local_deployment_file: Path = Path("deployments/execution-local.json")
    local_data_dir: Path = Path(".execution-data")
    local_relayer_private_key: SecretStr = SecretStr("")
    fuji_rpc_url: str = "https://api.avax-test.network/ext/bc/C/rpc"
    fuji_deployment_file: Path = Path("deployments/execution-fuji.json")
    fuji_data_dir: Path = Path(".execution-data-fuji")
    fuji_relayer_private_key: SecretStr = SecretStr("")
    fuji_attestor_address: str = ""
    anvil_binary: str = ""
    rpc_timeout: int = 15
    receipt_timeout: int = 20
    max_ttl: int = 30
    freshness_seconds: int = 60
    max_block_drift: int = 3
    required_confirmations: int = Field(default=1, ge=1, le=100)

    def model_post_init(self, __context):
        # Generic B_* overrides remain supported; normal .env configuration uses
        # B_LOCAL_* / B_FUJI_* so changing mode cannot reuse a local signing key.
        self.rpc_url = self.rpc_url or getattr(self, f"{self.mode}_rpc_url")
        self.deployment_file = self.deployment_file or getattr(
            self, f"{self.mode}_deployment_file"
        )
        self.data_dir = self.data_dir or getattr(self, f"{self.mode}_data_dir")
        if not self.relayer_private_key.get_secret_value():
            self.relayer_private_key = getattr(self, f"{self.mode}_relayer_private_key")
        if not self.attestor_address and self.mode == "fuji":
            self.attestor_address = self.fuji_attestor_address
        if not self.deployment_file.is_absolute():
            self.deployment_file = ROOT / self.deployment_file
        if not self.data_dir.is_absolute():
            self.data_dir = ROOT / self.data_dir
        if not self.anvil_binary:
            self.anvil_binary = foundry_binary("anvil", ROOT)


class DeploymentSettings(Settings):
    """Owner key exists only in the operator deploy process, never in the API settings model."""

    owner_private_key: SecretStr = SecretStr("")
    fuji_owner_private_key: SecretStr = SecretStr("")

    def model_post_init(self, __context):
        super().model_post_init(__context)
        if self.mode == "fuji" and not self.owner_private_key.get_secret_value():
            self.owner_private_key = self.fuji_owner_private_key
