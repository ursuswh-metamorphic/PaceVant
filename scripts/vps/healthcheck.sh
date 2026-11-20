#!/usr/bin/env bash
set -euo pipefail
if [[ -r /etc/pacevant/deploy.env ]]; then source /etc/pacevant/deploy.env; fi
base=${1:-http://127.0.0.1:8000}
curl --fail --silent --show-error --max-time 3 --retry 15 --retry-connrefused --retry-delay 1 --retry-max-time 30 "$base/healthz" >/dev/null
curl --fail --silent --show-error --max-time 10 "$base/judge/config" >/dev/null
curl --fail --silent --show-error --max-time 10 "${PACEVANT_FRONTEND_URL:-http://127.0.0.1}/" | grep -q 'PaceVant'
status=$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 15 "$base/readyz")
if [[ $status == 200 ]]; then
  echo 'Liveness, frontend/API and configured judge readiness passed.'
elif [[ $status == 503 ]]; then
  echo 'Application serves correctly; live fork not configured. Inspect /readyz; recorded evidence may still be used.'
else
  echo "Readiness request failed: $status" >&2; exit 1
fi
df -h /var/lib/pacevant
