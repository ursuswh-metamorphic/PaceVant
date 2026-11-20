"""Check the current documentation pack without loading env, apps or network clients."""

import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def matches(path, expected, lf_expected=None):
    if not path.is_file():
        return False
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest() == expected or (
        lf_expected is not None
        and hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == lf_expected
    )


def slug(value):
    return re.sub(r"[^\w\- ]", "", value.lower()).replace(" ", "-")


def main():
    manifest = json.loads((DOCS / "DOCUMENTATION_MANIFEST.json").read_text(encoding="utf-8"))
    entries = {entry["path"]: entry for entry in manifest["files"]}
    errors, historical_missing = [], []
    historical_count = links_checked = artifact_count = 0
    expected = {p.relative_to(ROOT).as_posix() for p in DOCS.rglob("*") if p.is_file()}
    missing = expected - entries.keys()
    if missing:
        errors.append({"unclassified_docs": sorted(missing)})
    listed = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode().split("\0")
    for name in listed:
        if name.endswith(".md") and not name.startswith("Proof-Gated-Signing/"):
            if (ROOT / name).is_file() and name not in entries:
                errors.append({"unclassified_markdown": name})
    for name, entry in entries.items():
        path = ROOT / name
        if not path.is_file():
            errors.append({"missing_file": name})
            continue
        if entry.get("sha256"):
            artifact_count += 1
            if not matches(path, entry["sha256"], entry.get("sha256_lf_checkout")):
                errors.append({"artifact_changed": name})
        if path.suffix != ".md":
            continue
        content = path.read_text(encoding="utf-8-sig")
        historical = entry["status"].startswith("HISTORICAL")
        historical_count += historical
        if f'DOC STATUS: {entry["status"]}' not in content[:1800]:
            errors.append({"status_banner_mismatch": name})
        if "\ufffd" in content:
            errors.append({"invalid_encoding_marker": name})
        text = re.sub(r"```.*?```", "", content, flags=re.S)
        text = re.sub(r"`[^`\n]*`", "", text)
        for target in re.findall(r"!?\[[^\]\n]*\]\(([^\)\n]+)\)", text):
            target = target.strip().split(' "')[0].strip("<>")
            url = urlsplit(target)
            if url.scheme or target.startswith("//"):
                continue
            dest = (path.parent / unquote(url.path)).resolve() if url.path else path
            links_checked += 1
            if not dest.exists():
                row = {"file": name, "target": target}
                (historical_missing if historical else errors).append(row)
            elif url.fragment and dest.suffix == ".md" and not historical:
                headings = re.findall(r"^#{1,6} (.+)$", dest.read_text(encoding="utf-8-sig"), re.M)
                anchors = {slug(h) for h in headings}
                if unquote(url.fragment) not in anchors:
                    errors.append({"file": name, "missing_anchor": target})
    inventory = json.loads((DOCS / "current-system-inventory.json").read_text(encoding="utf-8"))
    for name, expected_hash in inventory["source_files"].items():
        if not matches(ROOT / name, expected_hash, inventory.get("source_files_lf_sha256", {}).get(name)):
            errors.append({"source_inventory_stale": name})
    api = json.loads((DOCS / "current-api-catalog.json").read_text(encoding="utf-8"))
    for name, expected_hash in api["source_files_sha256"].items():
        if not matches(ROOT / name, expected_hash, api.get("source_files_lf_sha256", {}).get(name)):
            errors.append({"api_catalog_stale": name})
    keys = {(r["method"], r["path"]) for r in api["routes"]}
    if len(keys) != len(api["routes"]) or len(keys) != api["route_count"]:
        errors.append({"api_catalog": "duplicate routes or count mismatch"})
    for route in api["routes"]:
        source = ROOT / route["source"]
        if not source.is_file() or route["path"].removeprefix("/execution") not in source.read_text(encoding="utf-8"):
            errors.append({"api_source_missing": route["path"]})
    result = {
        "status": "PASS" if not errors else "FAIL",
        "scope": "Static documentation only; no env, RPC, models, workflow or transactions",
        "manifest_entries": len(entries),
        "historical_markdown": historical_count,
        "local_links_checked": links_checked,
        "hashed_artifacts_verified": artifact_count,
        "source_fingerprints_verified": len(inventory["source_files"]),
        "api_routes": len(keys),
        "historical_missing_local_targets": historical_missing,
        "errors": errors,
    }
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
