# Structure

This document maps the current checked-in layout. It does not describe planned
Hermes manager components that are not yet present in the tree.

## Root files

- `AGENTS.md`: repo-wide instructions.
- `NS8_RESOURCE_MAP.md`: NS8-specific documentation index for actions, UI, build flow, and module patterns.
- `HERMES_RESOURCE_MAP.md`: Hermes-specific documentation index for container behavior, runtime setup, and agent integration.
- `OPENVIKING_RESOURCE_MAP.md`: OpenViking documentation index for tenant, server, and deployment behavior.
- `README.md`: current project status and usage notes.
- `STRUCTURE.md`: this file.
- `build-images.sh`: builds the module image and the two wrapper images, and requests one NS8-managed TCP port for the module image.
- `test-module.sh`: runs the Robot Framework module test.
- `renovate.json`: Renovate configuration.

## `.github/`

- `agents/researcher.agent.md`: custom agent that searches `*_RESOURCE_MAP.md` files, browses documentation, and gathers prior art before implementation.
- `agents/security-expert.agent.md`: custom agent that reviews changes for security risks and applies or reports minimal mitigations.
- `agents/tester.agent.md`: custom agent that adds or updates unit and Robot Framework integration tests and runs the relevant test commands.
- `agents/docs-maintainer.agent.md`: custom agent that keeps checked-in Markdown docs aligned with the implementation.
- `agents/code-reviewer.agent.md`: custom agent that reviews diffs for minimality, readability, and maintainability.
- `agents/committer.agent.md`: custom agent that reviews git changes and creates Conventional Commits.
- `workflows/`: GitHub Actions workflows for image publishing, API-doc build and cleanup, registry cleanup, module and infrastructure tests, and UI build checks.

## `imageroot/`

`imageroot/` is copied into the installed NS8 module image.

- `AGENTS.md`: local runtime instructions.

### `imageroot/actions/`

- `create-module/20create`: validates the NS8-provided `TCP_PORT` and persists it to `OPENVIKING_PORT` in `environment` for the shared OpenViking service.
- `configure-module/20configure`: validates the user-facing `agents` payload plus shared `openviking` settings, persists `AGENTS_LIST`, and stores the shared embedding provider and secret.
- `configure-module/80start_services`: shell wrapper that delegates per-agent runtime reconciliation to `start-agent-services`.
- `configure-module/validate-input.json`: input schema for `configure-module`, including agent validation and the per-agent `use_default_gateway_for_llm` flag.
- `get-configuration/20read`: parses `AGENTS_LIST` from `environment`, synthesizes the hidden reserved system agent, and returns the current agents plus shared OpenViking embedding state.
- `get-configuration/validate-output.json`: output schema for the structured `agents` and shared `openviking` response, including the per-agent shared-gateway flag.
- `destroy-module/20destroy`: stops and cleans all per-agent units, runtime containers, named volumes, generated runtime files, and the shared OpenViking runtime.

### `imageroot/bin/`

- `discover-smarthost`: reads cluster smarthost settings, merges public values into `environment`, and writes `SMTP_PASSWORD` to `secrets.env`.
- `sync-agent-runtime`: writes `agent-<id>.env`, `agent-<id>_secrets.env`, one shared `openviking.conf`, and `systemd.env` from the stored configuration, generating and preserving one shared OpenViking root key, one reserved Hermes API key for the hidden system backend, per-agent tenant metadata, and Hermes-native config in each agent volume for agents that opt into the shared LLM gateway.
- `ensure-openviking-tenant`: waits for the shared OpenViking service, provisions the per-agent account and user if needed, and writes the tenant API key to `agent-<id>_secrets.env`.
- `start-agent-services`: reconciles the shared OpenViking service, the dedicated system Hermes backend service, and per-agent systemd targets after `configure-module`.
- `reload-agent-services`: refreshes active agent targets after smarthost changes.

### `imageroot/pypkg/`

- `hermes_agent_runtime.py`: shared runtime helpers for validation, `AGENTS_LIST` parsing, hidden system-agent synthesis, shared embedding settings, runtime-file generation, Hermes config synchronization for opted-in agents, shared OpenViking provisioning, per-agent volume naming and cleanup, and systemd status checks.

### `imageroot/events/`

- `smarthost-changed/10reload_services`: shell wrapper that refreshes only active per-agent targets when cluster smarthost settings change.

### `imageroot/systemd/user/`

- `hermes-agent@.target`: per-agent umbrella target.
- `hermes-agent-openviking.service`: runs the shared OpenViking container with one shared named data volume and one generated `ov.conf` bind mount.
- `hermes-agent-hermes@.service`: runs the Hermes runtime container in gateway mode with the per-agent Hermes state volume mounted at `/opt/data`.
- `hermes-agent-hermes-system.service`: runs the reserved always-on Hermes runtime that exposes the module-local API server consumed by shared OpenViking.

## `containers/`

Thin component wrapper images used by the module image labels:

- `containers/hermes/Containerfile`: wrapper around the upstream Hermes runtime image that preserves the upstream `/opt/data` bootstrap entrypoint and defaults to gateway mode.
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
- `src/views/Settings.vue`: shared OpenViking embedding settings plus agent-management settings view with table actions, create and edit modals, hidden system-agent filtering, per-agent shared-gateway checkbox, warning UX, and `configure-module` integration.
- `src/components/`: side menu components.
- `src/i18n/index.js`: runtime language loading.
- `src/styles/`: shared Carbon utility styles.
- `src/assets/`: static UI assets.

## `tests/`

- `__init__.robot`: Robot Framework initialization file.
- `kickstart.robot`: install, configure, shared OpenViking, reserved backend runtime, embedding configuration, hidden tenant metadata, lifecycle, tenant-isolation, persistent-volume, cleanup, and remove test flow.
- `pythonreq.txt`: Python dependencies used by the test runner.
