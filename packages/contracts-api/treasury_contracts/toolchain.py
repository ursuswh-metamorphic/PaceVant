"""Resolve native Foundry tools without starting Node.js or npm."""

import os
import platform
import shutil
from pathlib import Path


def foundry_binary(tool, root=None):
    if tool not in {"forge", "anvil", "cast"}:
        raise ValueError("Unsupported Foundry tool")
    root = Path(root) if root else Path(__file__).resolve().parents[3]
    configured = os.environ.get(f"TREASURY_{tool.upper()}_BINARY")
    if tool == "anvil":
        configured = configured or os.environ.get("B_ANVIL_BINARY")
    if configured:
        resolved = shutil.which(configured)
        if resolved or Path(configured).is_file():
            return resolved or str(Path(configured).resolve())
        raise FileNotFoundError(f"Configured {tool} binary does not exist")
    suffix = ".exe" if os.name == "nt" else ""
    directory = os.environ.get("TREASURY_FOUNDRY_BIN_DIR")
    if directory:
        candidate = Path(directory) / (tool + suffix)
        if not candidate.is_file():
            raise FileNotFoundError(f"{tool} is missing from TREASURY_FOUNDRY_BIN_DIR")
        return str(candidate.resolve())
    installed = shutil.which(tool)
    if installed:
        return installed
    candidate = root / ".tools/foundry" / (tool + suffix)
    if candidate.is_file():
        return str(candidate)
    # Compatibility with existing developer installs. This starts the native
    # executable directly; Node.js is never invoked and is absent from Docker.
    system = "win32" if os.name == "nt" else "darwin" if platform.system() == "Darwin" else "linux"
    arch = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "amd64"
    candidate = root / f"node_modules/@foundry-rs/{tool}-{system}-{arch}/bin" / (tool + suffix)
    if candidate.is_file():
        return str(candidate)
    raise FileNotFoundError(
        f"Native {tool} not installed; install Foundry v1.7.1 or set TREASURY_FOUNDRY_BIN_DIR"
    )
