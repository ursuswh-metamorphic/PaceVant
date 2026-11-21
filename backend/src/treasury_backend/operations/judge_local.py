"""Explicit local development: optional model-only .env, isolated Fuji forks only."""
import argparse
import os
from pathlib import Path

import uvicorn
from dotenv import dotenv_values

from treasury_backend.paths import ROOT

MODEL_PREFIXES = ("PACEVANT_SHIELD_", "GROQ_", "GEMINI_", "XINGCHI_", "DEEPSEEK_")


def model_environment(path):
    return {key: value for key, value in dotenv_values(path, interpolate=False).items()
            if key.startswith(MODEL_PREFIXES) and value}


def main():
    parser = argparse.ArgumentParser(description="Local judge: real models and isolated forks, no public signing keys")
    parser.add_argument("--port", type=int, default=18040)
    parser.add_argument("--model-env", type=Path, default=ROOT / ".env")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/judge-local")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    # Never load serving/Owner wallet credentials from the source environment.
    for key in list(os.environ):
        if any(word in key.upper() for word in ("PRIVATE_KEY", "ATTESTOR_KEY")):
            os.environ.pop(key, None)
    if args.model_env.exists():
        os.environ.update(model_environment(args.model_env))
    os.environ.update(
        PACEVANT_JUDGE_ENABLED="1", PACEVANT_JUDGE_SECURE_COOKIE="0",
        PACEVANT_JUDGE_EXECUTION_MODE="ANVIL_FORK", PACEVANT_JUDGE_DATA_DIR=str(args.data_dir),
        PACEVANT_JUDGE_ORACLE_WAIT_SECONDS="90", PACEVANT_JUDGE_TIMEOUT_SECONDS="360",
    )
    os.environ.pop("PACEVANT_MVP_LIVE_ENABLED", None)
    uvicorn.run("treasury_backend.api.judge:create_app", factory=True, host="127.0.0.1", port=args.port,
                workers=1, access_log=False, timeout_graceful_shutdown=20)


if __name__ == "__main__":
    main()
