#!/usr/bin/env bash
set -euo pipefail
sudo systemctl restart pacevant-judge
sleep 3
bash /opt/pacevant/current/scripts/vps/healthcheck.sh
