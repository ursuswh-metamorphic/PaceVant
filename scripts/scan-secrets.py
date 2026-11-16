"""Scan current source against configured secrets without printing secret values."""

from pathlib import Path
import json
import subprocess
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
secrets = set()
for env in root.glob(".env*"):
    if "example" in env.name or not env.is_file():
        continue
    for name, value in dotenv_values(env).items():
        if value and len(value) >= 16 and ("PRIVATE_KEY" in name or "API_KEY" in name):
            secrets.add(value.lower())
            if value.startswith("0x"):
                secrets.add(value[2:].lower())
files = (
    subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
    )
    .decode()
    .split("\0")
)
files = [name for name in files if name and (root / name).is_file()]
leaks = []
for name in files:
    file = root / name
    text = file.read_bytes().decode("utf-8", errors="ignore").lower()
    if any(value in text for value in secrets):
        leaks.append(name)
ignored = {
    name: subprocess.run(["git", "check-ignore", "--quiet", name], cwd=root).returncode
    == 0
    for name in [
        ".env",
        ".env.lock",
        ".execution-data/local-keys.json",
        ".execution-data-fuji/state.sqlite3",
    ]
}
result = {
    "status": "PASS" if not leaks and all(ignored.values()) else "FAIL",
    "files_checked": len(files),
    "configured_secrets_found": len(secrets),
    "leaked_files": leaks,
    "ignored_secret_paths": ignored,
}
print(json.dumps(result, indent=2))
(root / "evidence/execution-plane-secret-scan.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8"
)
raise SystemExit(0 if result["status"] == "PASS" else 1)
