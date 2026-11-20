import json
import os
import re
import secrets
import tempfile
from pathlib import Path

from dotenv import dotenv_values, set_key
from eth_account import Account
from filelock import FileLock

from .errors import OpsError

PUBLIC_RPC = "https://api.avax-test.network/ext/bc/C/rpc"
POLICY_ENV = {
    "TREASURY_MAX_RELATIVE_LOSS_BPS": "",
    "TREASURY_MAX_FIXED_LOSS_USD": "",
    "TREASURY_ORACLE_BAND_BPS": "",
    "TREASURY_POSTCONDITION_TOLERANCE_BPS": "",
    "TREASURY_SESSION_RISK_LIMIT_USD": "",
    "TREASURY_GLOBAL_DAILY_RISK_LIMIT_USD": "",
}
ENV_DEFAULTS = {
    "PACEVANT_DEMO_ENABLED": "0",
    "PACEVANT_DEMO_ACCESS_TOKEN": "",
    "PACEVANT_DEMO_INITIAL_CREDIT_WEI": "1000000000000000",
    "PACEVANT_DEMO_MAX_TX_FEE_WEI": "100000000000000",
    "TREASURY_FUJI_FORK_RPC_URL": "https://api.avax-test.network/ext/bc/C/rpc",
    "PACEVANT_SHIELD_FALLBACKS": "",
    "PACEVANT_SHIELD_REASONING_EFFORT": "",
    "PACEVANT_SHIELD_MAX_OUTPUT_CHARS": "16000",
    "PACEVANT_REQUIRE_ITAG": "0",
    "READ_ADDRESS": "0x0000000000000000000000000000000000000000",
    "VITE_NETWORK": "fuji",
    "B_MODE": "local",
    "B_LOCAL_RPC_URL": "http://127.0.0.1:8545",
    "B_LOCAL_DEPLOYMENT_FILE": "deployments/execution-local.json",
    "B_LOCAL_DATA_DIR": ".execution-data",
    "B_LOCAL_RELAYER_PRIVATE_KEY": "",
    "B_FUJI_DEPLOYMENT_FILE": "deployments/execution-fuji.json",
    "B_FUJI_DATA_DIR": ".execution-data-fuji",
    "PACEVANT_SERVE_FRONTEND": "true",
    "PACEVANT_CORS_ORIGINS": "",
    "PACEVANT_PLANNER_PROVIDER": "rules",
    "GROQ_API_KEY": "",
    "GROQ_MODEL": "openai/gpt-oss-20b",
    "GROQ_TIMEOUT_SECONDS": "20",
    "GROQ_MAX_COMPLETION_TOKENS": "512",
    "GROQ_REQUESTS_PER_MINUTE": "4",
    "GROQ_REQUESTS_PER_DAY": "200",
    "GROQ_TOKENS_PER_MINUTE": "4000",
    "GROQ_TOKENS_PER_DAY": "80000",
    "GROQ_CACHE_TTL_SECONDS": "300",
    "DEEPSEEK_API_KEY": "",
    "DEEPSEEK_MODEL": "deepseek-flash",
    "GEMINI_API_KEY": "",
    "GEMINI_MODEL": "gemma-4-26b-a4b-it",
    "XINGCHI_API_KEY": "",
    "XINGCHI_BASE_URL": "",
    "XINGCHI_MODEL": "gpt-6.1-sol",
    "PACEVANT_AI_ROTATION_ORDER": "deepseek,groq,gemini,xingchi",
    # Explicit opt-in preserves the established Fuji signing window during a main sync.
    "PACEVANT_SHIELD_MODE": "disabled",
    "PACEVANT_SHIELD_PROVIDER": "openai_compatible",
    "PACEVANT_SHIELD_MODEL": "gpt-6.1-sol",
    "PACEVANT_SHIELD_BASE_URL": "https://xingchiapi.com/v1",
    "PACEVANT_SHIELD_API_STYLE": "responses",
    "PACEVANT_SHIELD_USER_AGENT": "Cursor/0.45.0",
    "PACEVANT_SHIELD_API_KEY": "",
    "PACEVANT_SHIELD_TEMPERATURE": "omit",
    "PACEVANT_SHIELD_TIMEOUT": "20",
    "PACEVANT_SHIELD_RETRIES": "1",
    "PACEVANT_SHIELD_CONTEXT_CHARS": "24000",
    "PACEVANT_SHIELD_EPSILON": "0",
    "PACEVANT_SHIELD_MAX_REPLANS": "2",
    "TREASURY_OWNER_ADDRESS": "",
    "TREASURY_ATTESTOR_ADDRESS": "",
    "TREASURY_RELAYER_ADDRESS": "",
    # Demo identity address only is forwarded; its key never serves a signing role.
    "TREASURY_DEMO_USER_PRIVATE_KEY": "",
    "TREASURY_DEMO_USER_ADDRESS": "",
    "TREASURY_ORACLE_MODE": "demo",
    "TREASURY_ORACLE_SOURCE_ID": "TRUSTED_TEST_ORACLE",
    "PACEVANT_MODE": "MOCK",
    "PACEVANT_B_URL": "http://127.0.0.1:8001",
    "PACEVANT_B_TOKEN": "${B_API_KEY}",
    "PACEVANT_CHAIN_RPC_URL": "${B_FUJI_RPC_URL}",
    "PACEVANT_RELAYER_ADDRESS": "${AGENT_ADDRESS}",
    "PACEVANT_MANDATE_FILE": ".control-data-v2/fuji/mandate.json",
    "PACEVANT_ORACLE_FILE": ".control-data-v2/fuji/oracle.json",
    "PACEVANT_ATTESTOR_KEY": "",
    "PACEVANT_OPERATOR_TOKEN": "",
    "PACEVANT_INTERNAL_TOKEN": "",
    "PACEVANT_FUJI_VERIFICATION_RPC": PUBLIC_RPC,
    "B_FUJI_ATTESTOR_ADDRESS": "",
    "B_FUJI_OWNER_PRIVATE_KEY": "${DEPLOYER_PRIVATE_KEY}",
    "B_FUJI_RELAYER_PRIVATE_KEY": "${AGENT_PRIVATE_KEY}",
    "B_FUJI_RPC_URL": "${FUJI_RPC_URL}",
    "FUJI_RPC_URL": PUBLIC_RPC,
    "DEPLOYER_PRIVATE_KEY": "",
    "AGENT_PRIVATE_KEY": "",
    "AGENT_ADDRESS": "",
    "FUJI_TEST_WALLETS_ONLY": "false",
    "B_API_KEY": "",
    "TREASURY_LOCAL_RPC_URL": "http://127.0.0.1:8545",
    "TREASURY_LOCAL_DEPLOYMENT_FILE": "deployments/treasury-local-v2.json",
    "TREASURY_FUJI_DEPLOYMENT_FILE": "deployments/treasury-fuji-v2.json",
    "TREASURY_LOCAL_DATA_DIR": ".execution-data-v2",
    "TREASURY_FUJI_DATA_DIR": ".execution-data-fuji-v2",
    "TREASURY_CONTROL_DATA_DIR": ".control-data-v2",
    "TREASURY_A_PORT": "8000",
    "TREASURY_B_PORT": "8001",
    "TREASURY_OWNER_POLICY_APPROVED": "false",
    "TREASURY_MAX_WAVAX_PER_SWAP": "0",
    "TREASURY_MAX_ORACLE_AGE_SECONDS": "60",
    "TREASURY_APPROVAL_TTL_SECONDS": "30",
    "TREASURY_SESSION_DURATION_SECONDS": "3600",
    "TREASURY_ORACLE_USDC_USD": "1",
    "TREASURY_ORACLE_WAVAX_USD": "20",
    "TREASURY_FUJI_MAX_BLOCK_DRIFT": "30",
    "TREASURY_LOCAL_MAX_BLOCK_DRIFT": "3",
    "TREASURY_FUJI_CONFIRMATIONS": "2",
    "TREASURY_LOCAL_CONFIRMATIONS": "1",
    **POLICY_ENV,
}


def path_for(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def read_env(path):
    values = {k: v or "" for k, v in dotenv_values(path).items()}
    values.update(
        {
            k: v
            for k, v in os.environ.items()
            if k.startswith(("B_", "PACEVANT_", "TREASURY_", "FUJI_", "GROQ_", "GEMINI_", "XINGCHI_", "DEEPSEEK_"))
        }
    )
    return values


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=".tmp-", delete=False, encoding="utf-8"
    ) as f:
        json.dump(value, f, indent=2)
        f.write("\n")
        temporary = Path(f.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def update_env(path, updates):
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock"):
        original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".env-update-")
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(original)
            for key, value in updates.items():
                set_key(temporary, key, value, quote_mode="always")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def key_account(values, name):
    if not values.get(name):
        raise OpsError("Missing " + name)
    try:
        return Account.from_key(values[name])
    except Exception:
        raise OpsError("Invalid private key in " + name) from None


def init_env(env_file, *, generate_attestor=False):
    raw = dotenv_values(env_file, interpolate=False) if env_file.exists() else {}
    updates = {k: v for k, v in ENV_DEFAULTS.items() if k not in raw}
    for name in ("B_API_KEY", "PACEVANT_OPERATOR_TOKEN", "PACEVANT_INTERNAL_TOKEN"):
        if not raw.get(name):
            updates[name] = secrets.token_hex(32)
    if generate_attestor and not raw.get("PACEVANT_ATTESTOR_KEY"):
        updates["PACEVANT_ATTESTOR_KEY"] = Account.create().key.hex()
    update_env(env_file, updates)
    values = read_env(env_file)
    public_updates = {}
    for private, public in (
        ("PACEVANT_ATTESTOR_KEY", "B_FUJI_ATTESTOR_ADDRESS"),
        ("B_FUJI_RELAYER_PRIVATE_KEY", "AGENT_ADDRESS"),
    ):
        if values.get(private) and not values.get(public):
            public_updates[public] = key_account(values, private).address
    if public_updates:
        update_env(env_file, public_updates)
    return {
        "env_file": str(env_file),
        "added_or_initialized": sorted(set(updates) | set(public_updates)),
        "secret_values_printed": False,
    }


def units(value, decimals, name):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise OpsError("Invalid nonnegative decimal in " + name)
    whole, _, fraction = value.partition(".")
    if len(fraction) > decimals:
        raise OpsError("Too many decimal places in " + name)
    result = int(whole) * 10**decimals + int(fraction.ljust(decimals, "0") or "0")
    if result >= 2**256:
        raise OpsError("uint256 overflow in " + name)
    return str(result)


def integer(values, name, default=None, minimum=0, maximum=2**53 - 1):
    try:
        value = int(values.get(name, default))
    except (ValueError, TypeError):
        raise OpsError("Missing or invalid integer: " + name) from None
    if not minimum <= value <= maximum:
        raise OpsError("Out of range: " + name)
    return value
