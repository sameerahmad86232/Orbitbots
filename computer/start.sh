#!/bin/bash
set -euo pipefail
: "${ORBIT_TOKEN:?Set a long random ORBIT_TOKEN before starting}"
pids=()
cleanup(){ trap - TERM INT EXIT; if ((${#pids[@]})); then kill "${pids[@]}" 2>/dev/null || true; wait 2>/dev/null || true; fi; }
trap cleanup TERM INT EXIT
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp & pids+=($!)
for n in {1..50}; do if xdpyinfo >/dev/null 2>&1; then break; fi; sleep .1; done
openbox >/tmp/openbox.log 2>&1 & pids+=($!)
if [[ -n "${ORBIT_CA_CERT:-}" ]]; then
 mkdir -p "$HOME/.pki/nssdb"
 certutil -N -d "sql:$HOME/.pki/nssdb" --empty-password 2>/dev/null || true
 certutil -A -d "sql:$HOME/.pki/nssdb" -n OrbitDeploymentCA -t 'C,,' -i "$ORBIT_CA_CERT"
fi
browser_proxy=()
if [[ -n "${ORBIT_BROWSER_PROXY:-}" ]]; then browser_proxy=("--proxy-server=$ORBIT_BROWSER_PROXY" '--proxy-bypass-list=localhost;127.0.0.1;[::1]'); fi
# This volume belongs to one container only. Remove locks from its prior instance.
mkdir -p /data/chromium
rm -f /data/chromium/SingletonLock /data/chromium/SingletonSocket /data/chromium/SingletonCookie
chromium "${browser_proxy[@]}" --no-sandbox --disable-dev-shm-usage --no-first-run --disable-features=Translate --password-store=basic --user-data-dir=/data/chromium --start-maximized about:blank >/tmp/chromium.log 2>&1 & pids+=($!)
uvicorn server:app --host 0.0.0.0 --port 8080 --no-access-log & pids+=($!)
# Restart the container rather than presenting a dead browser/display as healthy.
wait -n "${pids[@]}"
exit 1
