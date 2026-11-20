import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from web3 import Web3

from treasury_backend.modules.oracle import DEFAULT_SOURCE_ID, source_hash
from treasury_contracts.rpc import evm_web3
from treasury_contracts.v2 import DeploymentProofConfig, ProofPolicy

from .env import POLICY_ENV, PUBLIC_RPC, integer, key_account, path_for, read_env, units
from .errors import OpsError


def owner_config(values):
    missing = [k for k in POLICY_ENV if not values.get(k)]
    if missing:
        raise OpsError("Missing owner risk settings: " + ", ".join(missing))
    if values.get("TREASURY_OWNER_POLICY_APPROVED", "").lower() != "true":
        raise OpsError("Owner must review parameters and set TREASURY_OWNER_POLICY_APPROVED=true")
    try:
        limit = units(
            values["TREASURY_SESSION_RISK_LIMIT_USD"], 8, "TREASURY_SESSION_RISK_LIMIT_USD"
        )
        policy = ProofPolicy(
            max_wavax_per_swap=units(
                values.get("TREASURY_MAX_WAVAX_PER_SWAP", "0"), 18, "TREASURY_MAX_WAVAX_PER_SWAP"
            ),
            max_relative_loss_bps=integer(values, "TREASURY_MAX_RELATIVE_LOSS_BPS", maximum=9999),
            fixed_loss_usd_e8=units(
                values["TREASURY_MAX_FIXED_LOSS_USD"], 8, "TREASURY_MAX_FIXED_LOSS_USD"
            ),
            oracle_band_bps=integer(values, "TREASURY_ORACLE_BAND_BPS", maximum=9999),
            tolerance_bps=integer(values, "TREASURY_POSTCONDITION_TOLERANCE_BPS", maximum=9999),
            max_oracle_age=integer(
                values, "TREASURY_MAX_ORACLE_AGE_SECONDS", "60", minimum=1, maximum=3600
            ),
            max_session_risk_usd_e8=limit,
            global_daily_risk_usd_e8=units(
                values["TREASURY_GLOBAL_DAILY_RISK_LIMIT_USD"],
                8,
                "TREASURY_GLOBAL_DAILY_RISK_LIMIT_USD",
            ),
            oracle_source_hash=source_hash(
                values.get("TREASURY_ORACLE_SOURCE_ID", DEFAULT_SOURCE_ID)
            ),
            authorization="OWNER_APPROVED",
        )
        return DeploymentProofConfig(
            proof_policy=policy,
            approval_ttl_seconds=integer(values, "TREASURY_APPROVAL_TTL_SECONDS", "30", minimum=1, maximum=300),
            session_limit_usd_e8=limit,
            session_duration_seconds=integer(
                values, "TREASURY_SESSION_DURATION_SECONDS", "3600", minimum=31, maximum=604800
            ),
        )
    except OpsError:
        raise
    except Exception:
        raise OpsError(
            "Owner risk configuration failed validation; check positive caps and integer/bps ranges"
        ) from None


@dataclass(repr=False)
class Profile:
    root: Path
    network: str
    values: dict
    rpc: str
    deployment: Path
    execution_data: Path
    control_data: Path
    a_port: int
    b_port: int
    drift: int
    confirmations: int

    @classmethod
    def load(cls, root, env_file, network):
        v = read_env(env_file)
        if network == "local":
            # Explicit isolated test mode: never inherit Fuji feeds/model keys/billing behavior.
            v = v | {"TREASURY_ORACLE_MODE": "demo", "TREASURY_ORACLE_SOURCE_ID": "TRUSTED_TEST_ORACLE",
                     "PACEVANT_PLANNER_PROVIDER": "rules", "PACEVANT_REQUIRE_ITAG": "0",
                     "PACEVANT_SHIELD_MODE": "disabled", "PACEVANT_DEMO_ENABLED": "0"}
            for key in list(v):
                if ((key.endswith("API_KEY") and key != "B_API_KEY") or key in {"PACEVANT_DEMO_ACCESS_TOKEN",
                        "TREASURY_DEMO_USER_PRIVATE_KEY", "B_FUJI_OWNER_PRIVATE_KEY",
                        "B_FUJI_RELAYER_PRIVATE_KEY", "DEPLOYER_PRIVATE_KEY", "AGENT_PRIVATE_KEY",
                        "PACEVANT_ATTESTOR_KEY"}):
                    v.pop(key)
        n = network.upper()
        rpc = v.get(f"TREASURY_{n}_RPC_URL") or (
            v.get("B_FUJI_RPC_URL") or PUBLIC_RPC if network == "fuji" else "http://127.0.0.1:8545"
        )
        parsed = urlsplit(rpc)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (
                parsed.scheme != "https"
                and not (
                    parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
        ):
            raise OpsError("RPC must use HTTPS or loopback HTTP, without userinfo")
        if network == "local" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise OpsError("Local mode requires a loopback Anvil RPC")
        return cls(
            root,
            network,
            v,
            rpc,
            path_for(
                root,
                v.get(f"TREASURY_{n}_DEPLOYMENT_FILE", f"deployments/treasury-{network}-v2.json"),
            ),
            path_for(
                root,
                v.get(
                    f"TREASURY_{n}_DATA_DIR",
                    ".execution-data-fuji-v2" if network == "fuji" else ".execution-data-v2",
                ),
            ),
            path_for(root, v.get("TREASURY_CONTROL_DATA_DIR", ".control-data-v2")) / network,
            integer(v, "TREASURY_A_PORT", "8000", minimum=1, maximum=65535),
            integer(v, "TREASURY_B_PORT", "8001", minimum=1, maximum=65535),
            integer(
                v,
                f"TREASURY_{n}_MAX_BLOCK_DRIFT",
                "30" if network == "fuji" else "3",
                minimum=1,
                maximum=240,
            ),
            integer(
                v,
                f"TREASURY_{n}_CONFIRMATIONS",
                "2" if network == "fuji" else "1",
                minimum=1,
                maximum=100,
            ),
        )

    @property
    def chain_id(self):
        return 43113 if self.network == "fuji" else 31337

    def web3(self):
        return evm_web3(Web3.HTTPProvider(self.rpc, request_kwargs={"timeout": 5}))

    def credentials(self, *, require_owner_key=False):
        if self.network == "local":
            key_file = self.execution_data / "local-keys.json"
            if not key_file.exists():
                raise OpsError("Local deployment keys missing; run treasury local first")
            local = json.loads(key_file.read_text())
            return local["attestor"], local["relayer"]
        if self.values.get("FUJI_TEST_WALLETS_ONLY", "").lower() != "true":
            raise OpsError("Set FUJI_TEST_WALLETS_ONLY=true for dedicated test wallets")
        if self.values.get("B_FUJI_OWNER_PRIVATE_KEY"):
            owner_address = key_account(self.values, "B_FUJI_OWNER_PRIVATE_KEY").address
        elif not require_owner_key and self.deployment.is_file():
            owner_address = Web3.to_checksum_address(
                json.loads(self.deployment.read_text())["owner"]
            )
        else:
            raise OpsError(
                "Owner key is needed for deployment; serving needs an existing V2 manifest"
            )
        signer = key_account(self.values, "PACEVANT_ATTESTOR_KEY")
        relayer = key_account(self.values, "B_FUJI_RELAYER_PRIVATE_KEY")
        for name, actual in (
            ("TREASURY_OWNER_ADDRESS", owner_address),
            ("TREASURY_ATTESTOR_ADDRESS", signer.address),
            ("TREASURY_RELAYER_ADDRESS", relayer.address),
        ):
            expected = self.values.get(name)
            if expected and expected.lower() != actual.lower():
                raise OpsError(name + " does not match its configured wallet role")
        if len({owner_address.lower(), signer.address.lower(), relayer.address.lower()}) != 3:
            raise OpsError("Owner, attestor and relayer must be three distinct test wallets")
        configured = self.values.get("B_FUJI_ATTESTOR_ADDRESS")
        if configured and configured.lower() != signer.address.lower():
            raise OpsError("B_FUJI_ATTESTOR_ADDRESS does not match PACEVANT_ATTESTOR_KEY")
        return self.values["PACEVANT_ATTESTOR_KEY"], self.values["B_FUJI_RELAYER_PRIVATE_KEY"]
