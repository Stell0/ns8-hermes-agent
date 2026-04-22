# Structure

This document maps the current layout.

## Root files

- `AGENTS.md`: repo-wide instructions.
- `README.md`: operator-facing overview and usage notes.
- `STRUCTURE.md`: this file.
- `NS8-MODULE.md`: implementation-oriented NS8 lifecycle notes.
- `NS8_RESOURCE_MAP.md`: NS8 reference index.
- `HERMES_RESOURCE_MAP.md`: Hermes reference index.
- `build-images.sh`: builds the module image plus the auth proxy and Hermes wrapper component images.
- `test-module.sh`: runs the module test suite.
- `renovate.json`: Renovate configuration.

## `imageroot/`

`imageroot/` is copied into the installed NS8 module image.

- `AGENTS.md`: local runtime instructions.

### `imageroot/actions/`

- `create-module/10initialize-state`: initializes `TIMEZONE` and creates the base state directory and shared secrets file.
- `create-module/20discover-smarthost`: refreshes shared SMTP settings after initialization.
- `configure-module/10validate-input`: validates the submitted `base_virtualhost`, optional shared `user_domain`, optional shared `lets_encrypt`, and agent list including per-agent `allowed_user`.
- `configure-module/20persist-shared-env`: persists the shared virtualhost, optional shared `user_domain`, plus `lets_encrypt`, tracks previous route values for cleanup, and backfills `TIMEZONE`.
- `configure-module/25configure-user-domain`: binds or unbinds the module from the selected NS8 user domain after shared settings are persisted.
- `configure-module/30remove-deleted-routes`: removes managed Traefik routes for removed agents when routing is active, including one-time certificate cleanup when the last managed route disappears.
- `configure-module/40remove-deleted-agents`: stops removed services, removes removed pods and containers, cleans legacy single-container leftovers, and delegates generated-state cleanup.
- `configure-module/50write-agent-metadata`: stores one metadata file per desired agent, including persisted `allowed_user`.
- `configure-module/60refresh-shared-settings`: refreshes shared SMTP settings via `discover-smarthost`.
- `configure-module/70sync-agent-runtime`: regenerates `agent_<id>.env` and `agent_<id>_secrets.env`, including the live auth proxy LDAP runtime env, bind secrets, and per-agent `AGENT_ALLOWED_USER` when a shared `user_domain` is configured.
- `configure-module/75seed-agent-home`: runs a one-shot Hermes container to seed strict first-write-only `/opt/data/SOUL.md` and `/opt/data/.env` content from checked-in templates.
- `configure-module/80reload-systemd`: reloads the user systemd manager.
- `configure-module/90reconcile-desired-routes`: creates, updates, or deletes per-agent Traefik routes for the desired configuration, including `lets_encrypt` cleanup when the shared host or TLS mode changes.
- `configure-module/95reconcile-agent-services`: enables, starts, stops, or disables per-agent services to match desired state.
- `configure-module/validate-input.json`: input schema for the shared `base_virtualhost`, optional `user_domain`, shared `lets_encrypt`, and the Hermes `agents` payload including `allowed_user`.
- `get-configuration/20read`: returns the shared dashboard virtualhost, shared `user_domain`, shared `lets_encrypt` setting, and configured agents with desired persisted status plus `allowed_user`.
- `get-configuration/validate-output.json`: output schema for the shared dashboard virtualhost, shared `user_domain`, shared `lets_encrypt` flag, and the Hermes `agents` response.
- `get-agent-runtime/10read`: returns live per-agent runtime status derived from systemd.
- `get-agent-runtime/validate-output.json`: output schema for the live runtime status response.
- `list-user-domains/10read`: returns the NS8 user domains available through `agent.ldapproxy` for the UI selector.
- `list-user-domains/validate-output.json`: output schema for the shared user-domain selector response.
- `list-domain-users/10read`: returns the sorted users available in the selected NS8 user domain.
- `list-domain-users/validate-input.json`: input schema for the domain-user lookup action.
- `list-domain-users/validate-output.json`: output schema for the domain-user lookup action.
- `destroy-module/10remove-routes`: removes managed Traefik routes for all known agents, including shared certificate cleanup when `lets_encrypt` is enabled.
- `destroy-module/20stop-services`: stops known services and removes known pods and containers, including legacy single-container leftovers.
- `destroy-module/30remove-agent-state`: delegates generated file, directory, and volume cleanup for each known agent.
- `destroy-module/40remove-agents-root`: removes the top-level `agents/` directory.

### `imageroot/bin/`

- `discover-smarthost`: reads cluster smarthost settings and writes public values into `environment` and `SMTP_PASSWORD` into `secrets.env`.
- `remove-agent-state`: removes generated per-agent env files, agent state directories, and the per-agent Hermes home volume.
- `sync-agent-runtime`: writes `agent_<id>.env` and `agent_<id>_secrets.env` for each configured agent, including the live auth proxy LDAP env and bind secrets when `USER_DOMAIN` is set.

### `imageroot/events/`

- `smarthost-changed/10reload_services`: refreshes shared SMTP settings and restarts active agent services.

### `imageroot/pypkg/`

- `hermes_agent_state.py`: small shared helper for metadata validation, env/json file handling, path naming, TCP port derivation, and named-volume naming.
- `hermes_user_domain.py`: shared helper for user-domain normalization, `Ldapproxy` lookup, LDAP user listing, and generation of per-agent LDAP runtime env and bind secrets.

### `imageroot/update-module.d/`

- `10ensure_tcp_ports`: backfills the managed 31-port TCP allocation during upgrades when older instances are missing `TCP_PORT` or `TCP_PORTS_RANGE`.

### `imageroot/systemd/user/`

- `hermes@.service`: primary gateway service per configured agent.
- `hermes-dashboard@.service`: dashboard sidecar service per configured agent.
- `hermes-auth.service`: shared authentication proxy service for the shared virtualhost.
- `hermes-pod@.service`: per-agent pod owner unit that publishes the dashboard port.

### `imageroot/templates/`

- `SOUL/`: checked-in role-specific templates used to seed managed `SOUL.md` content.
- `home.env.in`: checked-in template used to seed the managed default Hermes home `.env`.

## `containers/`

- `containers/auth/Containerfile`: shared dashboard auth proxy image.
- `containers/auth/authproxy.py`: FastAPI auth proxy that authenticates the shared virtualhost against LDAP, issues a host-wide session cookie, preserves the dashboard upstream `Authorization` header, replaces any inbound `X-Hermes-Authenticated-User` value with a trusted value derived from the authenticated session username, logs auth attempts and outcomes to stdout, and proxies authenticated sessions to the assigned dashboard upstream from `authproxy_agents.json`.
- `containers/hermes/Containerfile`: Hermes wrapper image built from `docker.io/nousresearch/hermes-agent:v2026.4.16` without a dashboard source patch helper.
- `containers/hermes/entrypoint.sh`: wrapper entrypoint that bootstraps the Hermes home volume, exports the bundled `web_dist` when present, and then delegates to the upstream CLI.

## `ui/`

The embedded admin UI uses Vue 2 and Vue CLI.

- `AGENTS.md`: local UI instructions.
- `public/metadata.json`: module metadata used by the UI shell.
- `public/i18n/`: translation files.
- `src/router/index.js`: routes for status, settings, and about.
- `src/store/index.js`: embedded module context store.
- `src/views/Settings.vue`: shared dashboard virtualhost, shared `user_domain`, shared `lets_encrypt`, per-agent `allowed_user`, the agent list, create/edit/delete modals, and start/stop state management.

## `tests/`

- `__init__.robot`: Robot Framework initialization file.
- `kickstart.robot`: end-to-end module lifecycle checks.
- `pythonreq.txt`: Python dependencies for the test runner.
- `test_runtime_validation.py`: focused unit tests for state helpers, configure-time seeding, route wiring, named-volume lifecycle, and the per-agent pod runtime contract.