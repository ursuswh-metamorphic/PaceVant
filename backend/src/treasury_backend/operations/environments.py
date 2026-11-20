import os

from eth_account import Account

from .env import PUBLIC_RPC
from .processes import anvil_binary


def safe_environment(extra):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(
            ("B_", "PACEVANT_", "TREASURY_", "FUJI_", "GROQ_", "GEMINI_", "XINGCHI_", "DEEPSEEK_")
        )
        and k not in {"DEPLOYER_PRIVATE_KEY", "AGENT_PRIVATE_KEY", "AGENT_ADDRESS"}
    }
    return env | {k: str(v) for k, v in extra.items()}


def b_environment(p, *, deployment=False):
    values = {
        "B_MODE": p.network,
        "B_RPC_URL": p.rpc,
        "B_FORK_RPC_URL": p.values.get(f"TREASURY_{p.network.upper()}_FORK_RPC_URL", ""),
        "B_DEPLOYMENT_FILE": p.deployment,
        "B_DATA_DIR": p.execution_data,
        "B_API_KEY": p.values.get("B_API_KEY", ""),
        "B_MAX_BLOCK_DRIFT": p.drift,
        "B_REQUIRED_CONFIRMATIONS": p.confirmations,
        "B_MAX_TTL": p.values.get("TREASURY_APPROVAL_TTL_SECONDS", "30"),
        "B_FRESHNESS_SECONDS": p.values.get("TREASURY_MAX_ORACLE_AGE_SECONDS", "60"),
        "B_ANVIL_BINARY": anvil_binary(),
    }
    if p.network == "fuji":
        signer, relayer = p.credentials(require_owner_key=deployment)
        values.update(
            B_RELAYER_PRIVATE_KEY=relayer, B_ATTESTOR_ADDRESS=Account.from_key(signer).address
        )
        if deployment:
            values["B_OWNER_PRIVATE_KEY"] = p.values["B_FUJI_OWNER_PRIVATE_KEY"]
    elif (p.execution_data / "local-keys.json").exists():
        _, relayer = p.credentials()
        values["B_RELAYER_PRIVATE_KEY"] = relayer
    return safe_environment(values)


def a_environment(p, *, source_root=None):
    signer, relayer = p.credentials()
    values = {
        "PACEVANT_MODE": p.network.upper(),
        "PACEVANT_SERVE_FRONTEND": p.values.get("PACEVANT_SERVE_FRONTEND", "true"),
        "PACEVANT_CORS_ORIGINS": p.values.get("PACEVANT_CORS_ORIGINS", ""),
        "PACEVANT_DB": p.control_data / "control.sqlite3",
        "PACEVANT_MANDATE_FILE": p.control_data / "mandate.json",
        "PACEVANT_ORACLE_FILE": p.control_data / "oracle.json",
        "PACEVANT_B_URL": f"http://127.0.0.1:{p.b_port}",
        "PACEVANT_B_TOKEN": p.values.get("B_API_KEY", ""),
        "PACEVANT_OPERATOR_TOKEN": p.values.get("PACEVANT_OPERATOR_TOKEN", ""),
        "PACEVANT_INTERNAL_TOKEN": p.values.get("PACEVANT_INTERNAL_TOKEN", ""),
        "PACEVANT_ATTESTOR_KEY": signer,
        "PACEVANT_CHAIN_RPC_URL": p.rpc,
        "PACEVANT_RELAYER_ADDRESS": Account.from_key(relayer).address,
        "PACEVANT_MAX_BLOCK_DRIFT": p.drift,
        "PACEVANT_FUJI_VERIFICATION_RPC": p.values.get("PACEVANT_FUJI_VERIFICATION_RPC")
        or PUBLIC_RPC,
        "PACEVANT_COINGECKO_DEMO_KEY": p.values.get("PACEVANT_COINGECKO_DEMO_KEY", ""),
    }
    if source_root:
        values["PYTHONPATH"] = os.pathsep.join(
            (str(source_root / "backend/src"), str(source_root / "packages/contracts-api"))
        )
    values.update(
        {
            name: value
            for name, value in p.values.items()
            if name.startswith(("GROQ_", "GEMINI_", "XINGCHI_", "DEEPSEEK_"))
            or name.startswith("PACEVANT_SHIELD_")
            or name
            in {"PACEVANT_PLANNER_PROVIDER", "PACEVANT_AI_ROTATION_ORDER", "PACEVANT_REQUIRE_ITAG"}
        }
    )
    return safe_environment(values)


def backend_environment(p):
    """One runtime holds attestor + relayer, never the owner/deployer key."""
    values = a_environment(p) | b_environment(p)
    # b_environment strips provider secrets; retain only the explicit planner profile.
    values.pop("PACEVANT_B_URL", None)
    values.pop("PACEVANT_B_TOKEN", None)
    values["PACEVANT_DEMO_ENABLED"] = "0"
    for name in (
        "PACEVANT_MVP_MANIFEST_FILE",
        "PACEVANT_MVP_LIVE_ENABLED",
        "B_MAX_GAS_PER_TX",
        "B_MAX_GAS_PRICE_WEI",
        "B_MAX_TX_FEE_WEI",
        "B_MAX_DAILY_GAS_EXPENSE_WEI",
    ):
        if name in p.values:
            values[name] = p.values[name]
    return values
