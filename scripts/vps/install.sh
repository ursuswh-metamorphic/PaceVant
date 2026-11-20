#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run installation with sudo.' >&2; exit 1; }
[[ $(uname -m) == x86_64 ]] || { echo 'This toolchain is pinned for Linux x86_64.' >&2; exit 1; }
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git nginx build-essential pkg-config libssl-dev libstdc++6 xz-utils certbot python3-certbot-nginx
id pacevant >/dev/null 2>&1 || useradd --system --home /var/lib/pacevant --shell /usr/sbin/nologin pacevant
install -d -m 0755 /opt/pacevant/bin /opt/pacevant/releases
install -d -o pacevant -g pacevant -m 0700 /var/lib/pacevant /var/cache/pacevant
install -d -o root -g pacevant -m 0750 /etc/pacevant
if [[ ! -x /opt/pacevant/bin/uv ]]; then
  curl --proto '=https' --tlsv1.2 -LsSf https://astral.sh/uv/0.12.10/install.sh | env UV_INSTALL_DIR=/opt/pacevant/bin UV_NO_MODIFY_PATH=1 sh
fi
# Managed Python is installed outside /root so systemd ProtectHome does not hide it.
UV_PYTHON_INSTALL_DIR=/opt/pacevant/python /opt/pacevant/bin/uv python install 3.12
tool_tmp=$(mktemp -d)
trap 'rm -rf -- "$tool_tmp"' EXIT
node_version=v24.21.0
node_archive=node-${node_version}-linux-x64.tar.xz
curl --proto '=https' --tlsv1.2 -fsSLo "$tool_tmp/$node_archive" "https://nodejs.org/dist/$node_version/$node_archive"
curl --proto '=https' --tlsv1.2 -fsSLo "$tool_tmp/SHASUMS256.txt" "https://nodejs.org/dist/$node_version/SHASUMS256.txt"
(cd "$tool_tmp" && grep " $node_archive\$" SHASUMS256.txt | sha256sum -c -)
tar -xf "$tool_tmp/$node_archive" -C /opt/pacevant
ln -sfn "/opt/pacevant/node-${node_version}-linux-x64/bin/node" /opt/pacevant/bin/node
ln -sfn "/opt/pacevant/node-${node_version}-linux-x64/bin/npm" /opt/pacevant/bin/npm
# Foundry release is pinned; fetch digest through GitHub release metadata, then verify.
curl --proto '=https' --tlsv1.2 -fsSLo "$tool_tmp/foundry-release.json" https://api.github.com/repos/foundry-rs/foundry/releases/tags/v1.7.1
/opt/pacevant/bin/uv run --no-project --python 3.12 python - "$tool_tmp" <<'PY'
import hashlib,json,pathlib,sys,urllib.request
directory=pathlib.Path(sys.argv[1]); release=json.loads((directory/'foundry-release.json').read_text())
asset=next(a for a in release['assets'] if a['name']=='foundry_v1.7.1_linux_amd64.tar.gz')
expected=asset.get('digest','')
if not expected.startswith('sha256:'): raise SystemExit('Missing trusted Foundry release digest; stop for review')
with urllib.request.urlopen(asset['browser_download_url'],timeout=60) as response: data=response.read()
if hashlib.sha256(data).hexdigest()!=expected.split(':',1)[1]: raise SystemExit('Foundry checksum mismatch')
(directory/'foundry.tar.gz').write_bytes(data)
PY
tar -xzf "$tool_tmp/foundry.tar.gz" -C /opt/pacevant/bin forge anvil cast
chmod -R a+rX /opt/pacevant/python
echo 'Native tools installed. Clone the repository, create the private model-only env, then run scripts/vps/deploy.sh.'
