# Structure

This document maps the current layout.

## Root files

- `AGENTS.md`: repo-wide instructions.
- `README.md`: operator-facing overview and usage notes.
- `STRUCTURE.md`: this file.
- `NS8-MODULE.md`: implementation-oriented NS8 lifecycle notes.
- `NS8_RESOURCE_MAP.md`: NS8 reference index.
- `HERMES_RESOURCE_MAP.md`: Hermes reference index.
- `build-images.sh`: builds the module image plus the Hermes wrapper image.
- `test-module.sh`: runs the module test suite.
- `renovate.json`: Renovate configuration.

## `imageroot/`

`imageroot/` is copied into the installed NS8 module image.

- `AGENTS.md`: local runtime instructions.

### `imageroot/actions/`

- `create-module/10initialize-state`: initializes `TIMEZONE` and creates the base state directory and shared secrets file.
- `create-module/20discover-smarthost`: refreshes shared SMTP settings after initialization.
- `configure-module/10validate-input`: validates the submitted `base_virtualhost`, optional shared `lets_encrypt`, and agent list.
- `configure-module/20persist-shared-env`: persists the shared virtualhost plus `lets_encrypt`, tracks previous values for route cleanup, and backfills `TIMEZONE`.
- `configure-module/30remove-deleted-routes`: removes managed Traefik routes for removed agents when routing is active, including one-time certificate cleanup when the last managed route disappears.
- `configure-module/40remove-deleted-agents`: stops removed services, removes removed pods and containers, cleans legacy single-container leftovers, and delegates generated-state cleanup.
- `configure-module/50write-agent-metadata`: stores one metadata file per desired agent.
- `configure-module/60refresh-shared-settings`: refreshes shared SMTP settings via `discover-smarthost`.
- `configure-module/70sync-agent-runtime`: regenerates `agent_<id>.env` and `agent_<id>_secrets.env`.
- `configure-module/75seed-agent-home`: runs a one-shot Hermes container to seed strict first-write-only `/opt/data/SOUL.md` and `/opt/data/.env` content from checked-in templates.
- `configure-module/80reload-systemd`: reloads the user systemd manager.
- `configure-module/90reconcile-desired-routes`: creates, updates, or deletes per-agent Traefik routes for the desired configuration, including `lets_encrypt` cleanup when the shared host or TLS mode changes.
- `configure-module/95reconcile-agent-services`: enables, starts, stops, or disables per-agent services to match desired state.
- `configure-module/validate-input.json`: input schema for the shared `base_virtualhost`, `lets_encrypt`, and the Hermes `agents` payload.
- `get-configuration/20read`: returns the shared dashboard virtualhost, shared `lets_encrypt` setting, and configured agents with desired persisted status.
- `get-configuration/validate-output.json`: output schema for the shared dashboard virtualhost, shared `lets_encrypt` flag, and the Hermes `agents` response.
- `get-agent-runtime/10read`: returns live per-agent runtime status derived from systemd.
- `get-agent-runtime/validate-output.json`: output schema for the live runtime status response.
- `destroy-module/10remove-routes`: removes managed Traefik routes for all known agents, including shared certificate cleanup when `lets_encrypt` is enabled.
- `destroy-module/20stop-services`: stops known services and removes known pods and containers, including legacy single-container leftovers.
- `destroy-module/30remove-agent-state`: delegates generated file, directory, and volume cleanup for each known agent.
- `destroy-module/40remove-agents-root`: removes the top-level `agents/` directory.

### `imageroot/bin/`

- `discover-smarthost`: reads cluster smarthost settings and writes public values into `environment` and `SMTP_PASSWORD` into `secrets.env`.
- `remove-agent-state`: removes generated per-agent env files, agent state directories, and the per-agent Hermes home volume.
- `sync-agent-runtime`: writes `agent_<id>.env` and `agent_<id>_secrets.env` for each configured agent.

### `imageroot/events/`

- `smarthost-changed/10reload_services`: refreshes shared SMTP settings and restarts active agent services.

### `imageroot/pypkg/`

- `hermes_agent_state.py`: small shared helper for metadata validation, env/json file handling, path naming, TCP port derivation, and named-volume naming.

### `imageroot/update-module.d/`

- `10ensure_tcp_ports`: backfills the managed 30-port TCP allocation during upgrades when older instances are missing `TCP_PORT` or `TCP_PORTS_RANGE`.

### `imageroot/systemd/user/`

- `hermes@.service`: primary gateway service per configured agent.
- `hermes-dashboard@.service`: dashboard sidecar service per configured agent.
- `hermes-pod@.service`: per-agent pod owner unit that publishes the dashboard port.

### `imageroot/templates/`

- `SOUL/`: checked-in role-specific templates used to seed managed `SOUL.md` content.
- `home.env.in`: checked-in template used to seed the managed default Hermes home `.env`.

## `containers/`

- `containers/hermes/Containerfile`: Hermes wrapper image built from `docker.io/nousresearch/hermes-agent:v2026.4.16`.
- `containers/hermes/entrypoint.sh`: wrapper entrypoint that bootstraps the Hermes home volume before delegating to the upstream CLI.

## `ui/`

The embedded admin UI uses Vue 2 and Vue CLI.

- `AGENTS.md`: local UI instructions.
- `public/metadata.json`: module metadata used by the UI shell.
- `public/i18n/`: translation files.
- `src/router/index.js`: routes for status, settings, and about.
- `src/store/index.js`: embedded module context store.
- `src/views/Settings.vue`: shared dashboard virtualhost plus `lets_encrypt` configuration, the agent list, create/edit/delete modals, and start/stop state management.

## `tests/`

- `__init__.robot`: Robot Framework initialization file.
- `kickstart.robot`: end-to-end module lifecycle checks.
- `pythonreq.txt`: Python dependencies for the test runner.
- `test_runtime_validation.py`: focused unit tests for state helpers, configure-time seeding, route wiring, named-volume lifecycle, and the per-agent pod runtime contract.