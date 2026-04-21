#!/bin/bash
# Docker/Podman entrypoint: bootstrap config files into the mounted volume, then run hermes.
set -e

HERMES_HOME="${HERMES_HOME:-/opt/data}"
INSTALL_DIR="/opt/hermes"
PACKAGED_WEB_DIST="${INSTALL_DIR}/ns8-web-dist"

source "${INSTALL_DIR}/.venv/bin/activate"

if [ -d "$PACKAGED_WEB_DIST" ]; then
    export HERMES_WEB_DIST="$PACKAGED_WEB_DIST"

    if [ -n "${BASE_URL:-}" ]; then
        export HERMES_WEB_DIST="/tmp/hermes-web-dist"
        rm -rf "$HERMES_WEB_DIST"
        cp -a "$PACKAGED_WEB_DIST" "$HERMES_WEB_DIST"

        python3 - "$HERMES_WEB_DIST/index.html" "$BASE_URL" <<'PY'
import json
import sys
from pathlib import Path

index_path = Path(sys.argv[1])
base_url = sys.argv[2].rstrip("/") or "/"
base_href = f"{base_url.rstrip('/')}/" if base_url != "/" else "/"
marker = "window.__HERMES_BASE_URL__"
script = f"<script>{marker}={json.dumps(base_url)};</script>"
base_tag = f"<base href={json.dumps(base_href)} />"

html = index_path.read_text(encoding="utf-8")
if "<base href=" not in html:
    html = html.replace("</head>", f"{base_tag}</head>", 1)
if marker not in html:
    html = html.replace("</head>", f"{script}</head>", 1)
    index_path.write_text(html, encoding="utf-8")
elif "<base href=" not in html:
    index_path.write_text(html, encoding="utf-8")
PY
    fi
fi

# Create essential directory structure.  Cache and platform directories
# (cache/images, cache/audio, platforms/whatsapp, etc.) are created on
# demand by the application — don't pre-create them here so new installs
# get the consolidated layout from get_hermes_dir().
# The "home/" subdirectory is a per-profile HOME for subprocesses (git,
# ssh, gh, npm …).  Without it those tools write to /root which is
# ephemeral and shared across profiles.  See issue #4426.
mkdir -p "$HERMES_HOME"/{cron,sessions,logs,hooks,memories,skills,skins,plans,workspace,home}

# .env
if [ ! -f "$HERMES_HOME/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$HERMES_HOME/.env"
fi

# config.yaml
if [ ! -f "$HERMES_HOME/config.yaml" ]; then
    cp "$INSTALL_DIR/cli-config.yaml.example" "$HERMES_HOME/config.yaml"
fi

# SOUL.md
if [ ! -f "$HERMES_HOME/SOUL.md" ]; then
    cp "$INSTALL_DIR/docker/SOUL.md" "$HERMES_HOME/SOUL.md"
fi

# Sync bundled skills (manifest-based so user edits are preserved)
if [ -d "$INSTALL_DIR/skills" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py"
fi

exec hermes "$@"