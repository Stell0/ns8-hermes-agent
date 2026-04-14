#!/usr/bin/env bash

set -euo pipefail

DASHBOARD_BIND_HOST="127.0.0.1"
DASHBOARD_BIND_PORT="${HERMES_AGENT_DASHBOARD_BIND_PORT:-19119}"
DASHBOARD_PROXY_PORT="${HERMES_AGENT_DASHBOARD_PROXY_PORT:-9119}"

cleanup() {
    local exit_code="$1"

    trap - EXIT INT TERM
    for pid in "${dashboard_pid:-}" "${proxy_pid:-}" "${gateway_pid:-}"; do
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
        fi
    done

    wait "${dashboard_pid:-}" 2>/dev/null || true
    wait "${proxy_pid:-}" 2>/dev/null || true
    wait "${gateway_pid:-}" 2>/dev/null || true
    exit "${exit_code}"
}

trap 'cleanup 143' INT TERM
trap 'cleanup $?' EXIT

hermes dashboard --host "${DASHBOARD_BIND_HOST}" --port "${DASHBOARD_BIND_PORT}" --no-open &
dashboard_pid=$!

python3 /usr/local/bin/hermes-dashboard-proxy.py \
    --listen-host 0.0.0.0 \
    --listen-port "${DASHBOARD_PROXY_PORT}" \
    --dashboard-host "${DASHBOARD_BIND_HOST}" \
    --dashboard-port "${DASHBOARD_BIND_PORT}" &
proxy_pid=$!

hermes gateway run &
gateway_pid=$!

wait -n "${dashboard_pid}" "${proxy_pid}" "${gateway_pid}"
cleanup "$?"