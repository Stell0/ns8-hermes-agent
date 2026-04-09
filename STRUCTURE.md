# Structure

This document maps the current checked-in layout. It does not describe planned
Hermes manager components that are not yet present in the tree.

## Root files

- `AGENTS.md`: repo-wide instructions.
- `README.md`: current project status and usage notes.
- `STRUCTURE.md`: this file.
- `build-images.sh`: builds the module image and the three wrapper images.
- `test-module.sh`: runs the Robot Framework module test.
- `renovate.json`: Renovate configuration.

## `imageroot/`

`imageroot/` is copied into the installed NS8 module image.

- `AGENTS.md`: local runtime instructions.

### `imageroot/actions/`

- `configure-module/20configure`: validates the `agents` payload and persists `AGENTS_LIST` with desired status into `environment`.
- `configure-module/80start_services`: shell wrapper that delegates per-agent runtime reconciliation to `start-agent-services`.
- `configure-module/validate-input.json`: input schema for `configure-module`, including agent validation.
- `get-configuration/20read`: parses `AGENTS_LIST` from `environment` and returns the current agents with persisted tenant metadata and actual systemd-backed status.
- `get-configuration/validate-output.json`: output schema for the structured `agents` response.
- `destroy-module/20destroy`: stops and cleans all per-agent units, pods, named volumes, generated runtime files, and the shared OpenViking runtime.

### `imageroot/bin/`

- `discover-smarthost`: reads cluster smarthost settings, merges public values into `environment`, and writes `SMTP_PASSWORD` to `secrets.env`.
- `sync-agent-runtime`: writes `agent-<id>.env`, `agent-<id>_secrets.env`, one shared `openviking.conf`, and `systemd.env` from the stored configuration, generating and preserving one shared OpenViking root key plus per-agent tenant metadata.
- `ensure-openviking-tenant`: waits for the shared OpenViking service, provisions the per-agent account and user if needed, and writes the tenant API key to `agent-<id>_secrets.env`.
- `start-agent-services`: reconciles the shared OpenViking service plus per-agent systemd targets and pods after `configure-module`.
- `reload-agent-services`: refreshes active agent targets after smarthost changes.

### `imageroot/pypkg/`

- `hermes_agent_runtime.py`: shared runtime helpers for validation, `AGENTS_LIST` parsing, runtime-file generation, shared OpenViking provisioning, per-agent volume naming and cleanup, and systemd status checks.

### `imageroot/events/`

- `smarthost-changed/10reload_services`: shell wrapper that refreshes only active per-agent targets when cluster smarthost settings change.

### `imageroot/systemd/user/`

- `hermes-agent@.target`: per-agent umbrella target.
- `hermes-agent-openviking.service`: runs the shared OpenViking container with one shared named data volume and one generated `ov.conf` bind mount.
- `hermes-agent-pod@.service`: creates and removes the Podman pod for one agent after ensuring the shared OpenViking tenant exists.
- `hermes-agent-hermes@.service`: runs the idle Hermes container inside the per-agent pod with the shared per-agent Hermes state volume mounted at `/opt/data`.
- `hermes-agent-gateway@.service`: runs the Hermes gateway container inside the per-agent pod with the same per-agent Hermes state volume mounted at `/opt/data`.

## `containers/`

Thin component wrapper images used by the module image labels:

- `containers/hermes/Containerfile`: wrapper around the upstream Hermes runtime image.
- `containers/gateway/Containerfile`: wrapper for Hermes gateway mode that keeps the upstream `/opt/data` bootstrap entrypoint.
- `containers/openviking/Containerfile`: wrapper around the upstream OpenViking image.

## `ui/`

The embedded admin UI currently uses Vue 2 and Vue CLI.

- `AGENTS.md`: local UI instructions.
- `README.md`: short UI development note.
- `package.json`: UI dependencies and scripts such as `serve`, `build`, and `watch`.
- `Containerfile`: UI image build file.
- `container-entrypoint.sh`: runs `yarn install` and then `watch` or `build`.
- `babel.config.js`, `vue.config.js`: UI build configuration.
- `public/metadata.json`: module metadata used by the UI shell.
- `public/i18n/`: translation files.
- `src/App.vue`: top-level embedded shell layout.
- `src/router/index.js`: router with `status`, `settings`, and `about` views.
- `src/store/index.js`: Vuex store for embedded module context.
- `src/views/`: page scaffolds for status, settings, and about.
- `src/views/Settings.vue`: agent-management settings view with table actions, modal creation, and `configure-module` integration.
- `src/components/`: side menu components.
- `src/i18n/index.js`: runtime language loading.
- `src/styles/`: shared Carbon utility styles.
- `src/assets/`: static UI assets.

## `tests/`

- `__init__.robot`: Robot Framework initialization file.
- `kickstart.robot`: install, configure, shared OpenViking, hidden tenant metadata, stopped-agent cleanup, tenant-isolation, persistent-volume, cleanup, and remove test flow.
- `pythonreq.txt`: Python dependencies used by the test runner.
