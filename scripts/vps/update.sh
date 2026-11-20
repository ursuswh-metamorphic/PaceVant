#!/usr/bin/env bash
set -euo pipefail
repo=${PACEVANT_SOURCE_DIR:-/opt/pacevant-source}
cd "$repo"
[[ -z $(git status --porcelain) ]] || { echo 'Source has local changes; review them before updating.' >&2; exit 1; }
[[ $(git branch --show-current) == develop ]] || { echo 'Expected develop branch.' >&2; exit 1; }
git pull --ff-only origin develop
exec bash scripts/vps/deploy.sh
