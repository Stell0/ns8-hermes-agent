# Structure

This document maps the current layout.

## Root files

- `AGENTS.md`: repo-wide instructions.
- `README.md`: operator-facing overview and usage notes.
- `STRUCTURE.md`: this file.
- `NS8-MODULE.md`: implementation-oriented NS8 lifecycle notes.
- `NS8_RESOURCE_MAP.md`: NS8 reference index.
- `HERMES_RESOURCE_MAP.md`: Hermes reference index.
- `build-images.sh`: builds the module image plus the Hermes and Open WebUI wrapper images.
- `test-module.sh`: runs the module test suite.
- `renovate.json`: Renovate configuration.

## `imageroot/`

`imageroot/` is copied into the installed NS8 module image.

- `AGENTS.md`: local runtime instructions.

### `imageroot/actions/`

- `create-module/20create`: initializes `TIMEZONE`, creates base state files and directories, and discovers smarthost settings.
- `configure-module/20configure`: validates the submitted `base_virtualhost` and agent list, stores one metadata file per agent, synchronizes runtime files, reconciles managed Traefik routes, and reconciles per-agent services.
- `configure-module/validate-input.json`: input schema for the shared `base_virtualhost` plus the Hermes `agents` payload.
- `get-configuration/20read`: returns the shared WebUI virtualhost plus configured agents with actual runtime status from systemd.
- `get-configuration/validate-output.json`: output schema for the shared WebUI virtualhost plus the Hermes `agents` response.
- `destroy-module/20destroy`: stops services, removes pods and containers, deletes managed routes, and deletes generated per-agent files and directories.

### `imageroot/bin/`

- `discover-smarthost`: reads cluster smarthost settings and writes public values into `environment` and `SMTP_PASSWORD` into `secrets.env`.
- `sync-agent-runtime`: writes `agent_<id>.env`, `agent_<id>_openwebui.env`, `agent_<id>_secrets.env`, and `agent_<id>_openwebui_secrets.env`, seeds each Hermes home from the checked-in role-specific SOUL templates plus the default home env template, and prepares each Open WebUI data directory.

### `imageroot/events/`

- `smarthost-changed/10reload_services`: refreshes shared SMTP settings and restarts active agent services.

### `imageroot/pypkg/`

- `hermes_agent_state.py`: small shared helper for validation, env/json file handling, path naming, and service-state checks.

### `imageroot/update-module.d/`

- `10ensure_tcp_ports`: backfills the managed 30-port TCP allocation during upgrades when older instances are missing `TCP_PORT` or `TCP_PORTS_RANGE`.

### `imageroot/systemd/user/`

- `hermes-agent@.service`: one runtime service per configured agent.

### `imageroot/templates/`

- `SOUL/`: checked-in role-specific templates used to seed `SOUL.md` with `sed`.
- `home.env.in`: checked-in template used to seed the default Hermes home `.env` with `sed`.

## `containers/`

- `containers/hermes/Containerfile`: Hermes wrapper image that keeps the upstream Hermes entrypoint and defaults to gateway mode.
- `containers/open-webui/Containerfile`: Open WebUI wrapper image used as the per-agent web frontend container.

## `ui/`

The embedded admin UI uses Vue 2 and Vue CLI.

- `AGENTS.md`: local UI instructions.
- `public/metadata.json`: module metadata used by the UI shell.
- `public/i18n/`: translation files.
- `src/router/index.js`: routes for status, settings, and about.
- `src/store/index.js`: embedded module context store.
- `src/views/Settings.vue`: shared WebUI virtualhost configuration plus the agent list, create/edit/delete modals, and start/stop state management.

## `tests/`

- `__init__.robot`: Robot Framework initialization file.
- `kickstart.robot`: end-to-end module lifecycle checks.
- `pythonreq.txt`: Python dependencies for the test runner.
- `test_runtime_validation.py`: focused unit tests for state helpers, route wiring, and runtime file seeding.