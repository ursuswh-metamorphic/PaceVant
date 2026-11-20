#!/usr/bin/env bash
set -euo pipefail
repo=$(git rev-parse --show-toplevel)
[[ -z $(git -C "$repo" status --porcelain) ]] || { echo 'Working tree has changes; preserve/review them before deployment.' >&2; exit 1; }
[[ -r /etc/pacevant/judge.env ]] || sudo test -r /etc/pacevant/judge.env || { echo 'Create model-only /etc/pacevant/judge.env first.' >&2; exit 1; }
git -C "$repo" fetch origin develop
sha=$(git -C "$repo" rev-parse origin/develop)
release=/opt/pacevant/releases/$sha
previous=$(readlink -f /opt/pacevant/current || true)
if [[ $previous == "$release" ]]; then
  bash "$repo/scripts/vps/healthcheck.sh"
  echo "DEPLOYED_COMMIT=$sha (already active; source and virtualenv preserved)"
  exit 0
fi
switched=0
rollback_on_error() {
  local status=$?
  if [[ $switched == 1 && -n $previous && -d $previous ]]; then
    sudo ln -sfn "$previous" /opt/pacevant/current
    sudo systemctl restart pacevant-judge || true
    sudo systemctl reload nginx || true
    echo "Deployment failed; restored previous release $previous without deleting data." >&2
  fi
  exit "$status"
}
trap rollback_on_error ERR
export PATH=/opt/pacevant/bin:$PATH
export UV_PYTHON_INSTALL_DIR=/opt/pacevant/python
sudo mkdir -p "$release"
sudo chown "$(id -u):$(id -g)" "$release"
git -C "$repo" archive "$sha" | tar -x -C "$release"
cd "$release"
uv sync --locked --no-dev --python 3.12
npm ci --prefix frontend --no-audit --no-fund
npm run --prefix frontend build
uv run --locked python tools/contracts/bootstrap.py
uv run --locked python tools/contracts/foundry.py forge build
# Offline simulations use the compiler already installed during this build.
sudo install -d -o pacevant -g pacevant -m 0700 /var/lib/pacevant/.svm
if [[ -d ${HOME}/.svm ]]; then sudo cp -a "${HOME}/.svm/." /var/lib/pacevant/.svm/; fi
sudo chown -R pacevant:pacevant /var/lib/pacevant/.svm
sudo chmod -R a+rX "$release" /opt/pacevant/python
sudo install -m 0644 deploy/native/pacevant-judge.service /etc/systemd/system/pacevant-judge.service
sudo install -m 0644 deploy/native/proxy.conf /etc/nginx/snippets/pacevant-proxy.conf
# Preserve an existing domain/TLS server block; never overwrite installed certificates/config.
if ! sudo test -e /etc/nginx/sites-available/pacevant; then
  sudo install -m 0644 deploy/native/nginx.conf /etc/nginx/sites-available/pacevant
  sudo ln -s /etc/nginx/sites-available/pacevant /etc/nginx/sites-enabled/pacevant
fi
# Only retire Ubuntu's unmodified packaged welcome site. Preserve custom sites.
if [[ $(readlink -f /etc/nginx/sites-enabled/default || true) == /etc/nginx/sites-available/default ]]; then
  packaged_md5=$(dpkg-query -W -f='${Conffiles}\n' nginx-common | awk '$1=="/etc/nginx/sites-available/default" {print $2}')
  actual_md5=$(md5sum /etc/nginx/sites-available/default | awk '{print $1}')
  if [[ -n $packaged_md5 && $actual_md5 == "$packaged_md5" ]]; then
    sudo unlink /etc/nginx/sites-enabled/default
    echo 'Disabled the unmodified Ubuntu welcome site; its configuration file is preserved.'
  fi
fi
sudo nginx -t
sudo ln -sfn "$release" /opt/pacevant/current
switched=1
sudo systemctl daemon-reload
sudo systemctl enable pacevant-judge nginx
sudo systemctl restart pacevant-judge
sudo systemctl reload nginx
sleep 3
if ! bash scripts/vps/healthcheck.sh; then
  echo "Deployment smoke failed at $sha. Previous release: $previous" >&2
  if [[ -n $previous && -d $previous ]]; then
    sudo ln -sfn "$previous" /opt/pacevant/current
    sudo systemctl restart pacevant-judge
    echo 'Restored previous release; persistent databases were not removed.' >&2
  fi
  exit 1
fi
switched=0
echo "DEPLOYED_COMMIT=$sha"
