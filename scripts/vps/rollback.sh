#!/usr/bin/env bash
set -euo pipefail
if [[ -r /etc/pacevant/deploy.env ]]; then set -a; source /etc/pacevant/deploy.env; set +a; fi
sha=${1:?Usage: rollback.sh EXISTING_RELEASE_SHA}
[[ $sha =~ ^[0-9a-f]{40}$ ]] || { echo 'An exact commit SHA is required.' >&2; exit 1; }
release=/opt/pacevant/releases/$sha
[[ -x $release/.venv/bin/python && -f $release/frontend/dist/index.html ]] || { echo 'Release not built.' >&2; exit 1; }
sudo ln -sfn "$release" /opt/pacevant/current
sudo systemctl restart pacevant-judge
sudo systemctl reload nginx
sleep 3
bash "$release/scripts/vps/healthcheck.sh"
echo "ROLLED_BACK_COMMIT=$sha; persistent data retained."
