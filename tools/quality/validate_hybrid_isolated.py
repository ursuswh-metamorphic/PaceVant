"""Run LOCAL regressions without loading the operator's .env or public-chain keys."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from treasury_contracts.toolchain import foundry_binary

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.output = args.output.resolve()
    environment = {k:v for k,v in os.environ.items() if not k.startswith(("PACEVANT_", "B_", "GEMINI_", "DEEPSEEK_", "XINGCHI_", "OPENAI_"))}
    for tool in ("anvil", "forge"):
        environment[f"TREASURY_{tool.upper()}_BINARY"] = foundry_binary(tool, ROOT)
    environment["PYTHONIOENCODING"] = "utf-8"
    with tempfile.TemporaryDirectory(prefix="pacevant-hybrid-validation-", ignore_cleanup_errors=True) as directory:
        target = Path(directory)
        for name in ("backend", "packages", "fixtures", "tools", "contracts", "frontend", "docs", "evidence", "scripts", "deployments", ".github", "lib", "out", "cache-foundry"):
            source = ROOT / name
            if source.is_dir():
                shutil.copytree(source, target / name, ignore=shutil.ignore_patterns(".env", ".env.*", "__pycache__", "*.sqlite*", "*.log", ".pytest_cache", ".venv", "node_modules"))
        for source in ROOT.iterdir():
            if source.is_file() and source.name in {"pyproject.toml","uv.lock","package.json","package-lock.json","foundry.toml","README.md","Dockerfile",".gitattributes",".gitignore",".env.example"}:
                shutil.copy2(source, target / source.name)
        native = target / ".tools/foundry"
        native.mkdir(parents=True)
        for tool in ("anvil", "forge"):
            source = Path(foundry_binary(tool, ROOT))
            shutil.copy2(source, native / source.name)
        environment["PYTHONPATH"] = os.pathsep.join((str(target / "backend/src"), str(target / "packages/contracts-api")))
        commands = [
            ("python", [sys.executable, "-m", "pytest", "-q", "--tb=short", f"--junitxml={args.output / 'python.xml'}"]),
            ("solidity", [foundry_binary("forge", ROOT), "test", "-vv"]),
        ]
        failures = []
        for name, command in commands:
            with (args.output / f"{name}.log").open("w", encoding="utf8") as log:
                result = subprocess.run(command, cwd=target, env=environment, stdout=log, stderr=subprocess.STDOUT)
            print(name, "exit", result.returncode, flush=True)
            if result.returncode:
                failures.append(name)
        if failures:
            raise SystemExit("Failed: " + ",".join(failures))


if __name__ == "__main__":
    main()
