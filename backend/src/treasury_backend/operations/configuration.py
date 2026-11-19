"""Single .env, atomic updates and local/Fuji profiles. Never log secret values."""

import os
import tempfile
from pathlib import Path

from dotenv import dotenv_values, set_key
from filelock import FileLock

from treasury_backend.config.execution import ROOT


def portable_path(path: Path, root: Path = ROOT) -> str:
    path = path.resolve()
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def update_env(path: Path, updates: dict[str, str]):
    """Preserve unrelated variables/comments; readers see only a complete file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock", timeout=10):
        original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
        fd, temporary = tempfile.mkstemp(prefix=".env-update-", dir=path.parent)
        tmp = Path(temporary)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(original)
            for name, value in updates.items():
                set_key(tmp, name, value, quote_mode="always")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)


def migrate_env(root: Path = ROOT):
    """Merge retired split env files; conflicting nonempty values fail closed."""
    destination = root / ".env"
    current = dict(dotenv_values(destination)) if destination.exists() else {}
    updates = {}
    retired = []
    for mode in ("local", "fuji"):
        source = root / f".env.b.{mode}"
        if not source.is_file():
            continue
        for key, value in dotenv_values(source).items():
            if value is None or key == "B_MODE":
                continue
            target = key if key == "B_API_KEY" else key.replace("B_", f"B_{mode.upper()}_", 1)
            if key in {"B_DEPLOYMENT_FILE", "B_DATA_DIR"}:
                p = Path(value)
                value = portable_path(p if p.is_absolute() else root / p, root)
            existing = updates.get(target, current.get(target))
            if existing and existing != value:
                raise RuntimeError(f"Conflicting configuration for {target}; no file was changed")
            if not existing:
                updates[target] = value
        retired.append(source)
    defaults = {
        "B_MODE": "local",
        "B_LOCAL_RPC_URL": "http://127.0.0.1:8545",
        "B_LOCAL_DEPLOYMENT_FILE": "deployments/execution-local.json",
        "B_LOCAL_DATA_DIR": ".execution-data",
        "B_FUJI_RPC_URL": "${FUJI_RPC_URL}"
        if current.get("FUJI_RPC_URL")
        else "https://api.avax-test.network/ext/bc/C/rpc",
        "B_FUJI_DEPLOYMENT_FILE": "deployments/execution-fuji.json",
        "B_FUJI_DATA_DIR": ".execution-data-fuji",
        "B_FUJI_ATTESTOR_ADDRESS": "",
        "B_FUJI_RELAYER_PRIVATE_KEY": "${AGENT_PRIVATE_KEY}"
        if current.get("AGENT_PRIVATE_KEY")
        else "",
        "B_FUJI_OWNER_PRIVATE_KEY": "${DEPLOYER_PRIVATE_KEY}"
        if current.get("DEPLOYER_PRIVATE_KEY")
        else "",
    }
    for key, value in defaults.items():
        if key not in current and key not in updates:
            updates[key] = value
    if updates:
        update_env(destination, updates)
    # Confirm persisted values BEFORE removing the split source files.
    raw = dotenv_values(destination, interpolate=False)
    resolved = dotenv_values(destination)
    for key, value in updates.items():
        if raw.get(key) != value or key not in resolved:
            raise RuntimeError(f"Merged configuration missing {key}; source files retained")
    for source in retired:
        source.unlink()
    return {
        "env_file": ".env",
        "merged_files": [p.name for p in retired],
        "updated_keys": sorted(updates),
    }
