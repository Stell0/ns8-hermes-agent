# NS8 Module Reference — ns8-hermes-agent

This document describes the current checked-in NS8 module implementation for
`ns8-hermes-agent`. Treat the repository tree as the source of truth.

## Scope

The current module is a rootless NS8 application scaffold that manages a stored
roster of agents plus shared OpenViking embedding settings. Each configured
user-facing agent can own one isolated Hermes runtime container managed by
systemd user units, while one shared OpenViking runtime is reused across all
agents inside the same module instance and one reserved always-on Hermes
runtime is kept for the shared OpenViking backend.

The current runtime includes:

- `create-module`, `configure-module`, `get-configuration`, and `destroy-module`
- smarthost discovery and one `smarthost-changed` event handler
- generated per-agent env and secrets files plus one shared OpenViking config
- user systemd units for one shared OpenViking service, one reserved Hermes backend service, and one Hermes runtime service per user-facing agent
- two wrapper container images: Hermes and OpenViking
- an embedded Vue 2 admin UI
- a Robot Framework smoke test focused on the shared OpenViking plus per-agent runtime contract

The current runtime does not publish a Traefik route or expose an HTTP endpoint.

## NS8 Concepts Used Here

### Module instance

Each installed instance gets a module identifier such as `hermes-agent1`.

### Actions

Actions live under `imageroot/actions/<action-name>/` and run numbered steps in
lexical order.

### Systemd user units

Because the module is rootless, long-running services are managed with
`systemctl --user` under the module user account.

### Events

Event handlers live under `imageroot/events/<event-name>/` and are composed of
numbered executable steps.

## Repository Components Relevant To NS8

- `build-images.sh`: builds the module image and two wrapper images
- `imageroot/actions/`: action implementations for create, configure, read, and destroy
- `imageroot/bin/`: runtime helper scripts
- `imageroot/pypkg/`: shared Python runtime helpers
- `imageroot/systemd/user/`: templated systemd target and service units
- `ui/`: embedded NS8 admin UI
- `tests/`: Robot Framework smoke suite

## Image Build And Packaging

`build-images.sh` builds three images:

| Image | Purpose |
|------|---------|
| `ghcr.io/nethserver/hermes-agent` | Main NS8 module image with `imageroot/` and the compiled UI bundle. |
| `ghcr.io/nethserver/hermes-agent-hermes` | Thin wrapper around the upstream Hermes image that preserves the upstream entrypoint and defaults to `gateway run`. |
| `ghcr.io/nethserver/hermes-agent-openviking` | OpenViking wrapper image. |

The module image currently sets these relevant NS8 labels:

- `org.nethserver.rootfull=0`
- `org.nethserver.tcp-ports-demand=1`
- `org.nethserver.images=<wrapper image list>`

The practical effect is:

- the module runs rootless
- the core allocates one TCP port and exposes it as `TCP_PORT`
- the core pulls the additional wrapper images on install and update
- the pulled image URLs are exposed as environment variables such as
  `HERMES_AGENT_HERMES_IMAGE` and `HERMES_AGENT_OPENVIKING_IMAGE`

The current image does not declare `org.nethserver.volumes`, so the per-agent
named volumes created by the runtime stay internal to the module and are not
currently surfaced for NS8 additional-disk assignment.

The current image requests one TCP port for the shared OpenViking localhost
publish mapping and does not request Traefik route authorizations.

## Lifecycle Summary

```text
add-module
  -> create-module
       - pulls the module image and the wrapper images
       - installs imageroot and UI assets
    - persists NS8 `TCP_PORT` into `OPENVIKING_PORT`
    - records the effective `TIMEZONE` for the shared runtime services
  -> configure-module
       - validates and persists the agent roster in environment
       - discovers smarthost settings
    - writes systemd.env, one shared OpenViking config, and the per-agent env and secrets files used during reconciliation
       - starts or stops per-agent systemd targets based on desired status
    - removes stopped or deleted agent runtime files, named volumes, and OpenViking tenant accounts
  -> module running
       - get-configuration returns the stored roster with actual runtime status
       - smarthost-changed refreshes active per-agent targets only
  -> destroy-module
       - stops and disables per-agent targets
    - removes runtime containers, per-agent named volumes, shared OpenViking runtime state, and generated runtime files
       - core removes the rootless module state and service user
```

## Actions

### `create-module`

**Path**: `imageroot/actions/create-module/`

| Step | File | Purpose |
|------|------|---------|
| 20 | `20create` | Validates the NS8-provided `TCP_PORT`, persists it as `OPENVIKING_PORT`, and records the effective `TIMEZONE` in `environment` for the shared runtime services. |

If an existing instance already has `TCP_PORT` but lacks `OPENVIKING_PORT`,
runtime reconciliation backfills the alias once before starting services.

### `configure-module`

**Path**: `imageroot/actions/configure-module/`

Accepted payload shape:

```json
{
  "agents": [
    {
      "id": 1,
      "name": "Foo Bar",
      "role": "developer",
      "status": "start",
      "use_default_gateway_for_llm": true
    }
  ],
  "openviking": {
    "embedding": {
      "provider": "jina",
      "api_key": "test-key"
    }
  }
}
```

Each agent must contain:

- `id`: integer greater than or equal to `1`
- `name`: non-empty string matching `^[A-Za-z ]+$`
- `role`: `default`, `developer`, `marketing`, `sales`, `customer_support`, `social_media_manager`, `business_consultant`, or `researcher`
- `status`: `start` or `stop`
- `use_default_gateway_for_llm`: boolean; when `true`, the agent is configured
  to use the module's hidden shared Hermes API gateway as its main LLM endpoint
- optional hidden backend fields `account`, `user`, and `agent_id`: auto-generated today and persisted so future UI work can expose them explicitly

For each started user-facing agent, the module also seeds `/opt/data/SOUL.md`
with a role-specific identity profile. If the agent name or role changes later,
the module regenerates that file only when the existing content still matches
the previous module-generated seed; customized SOUL content is preserved.

Steps:

| Step | File | Purpose |
|------|------|---------|
| 20 | `20configure` | Validates the payload, persists `AGENTS_LIST` into `environment`, and stores the shared OpenViking embedding provider and secret. |
| 80 | `80start_services` | Delegates lifecycle reconciliation to `start-agent-services`. |

The persisted roster format is:

```text
AGENTS_LIST=1:Foo Bar:developer:start:agent-1:agent-1:agent-1:true,2:Alice User:default:stop:agent-2:agent-2:agent-2:false
```

The stored `status` is the desired state. The runtime status returned later by
`get-configuration` is derived from systemd.

### `get-configuration`

**Path**: `imageroot/actions/get-configuration/`

| Step | File | Purpose |
|------|------|---------|
| 20 | `20read` | Parses `AGENTS_LIST` from `environment`, synthesizes the reserved backend agent, and returns the roster with actual runtime status from systemd plus shared OpenViking embedding state. |

Example output:

```json
{
  "agents": [
    {
      "id": 0,
      "name": "OpenViking Backend",
      "role": "default",
      "status": "start",
      "account": "system",
      "user": "system",
      "agent_id": "openviking-backend",
      "use_default_gateway_for_llm": false,
      "hidden": true,
      "protected": true,
      "system": true
    },
    {
      "id": 1,
      "name": "Foo Bar",
      "role": "developer",
      "status": "start",
      "account": "agent-1",
      "user": "agent-1",
      "agent_id": "agent-1",
      "use_default_gateway_for_llm": true,
      "hidden": false,
      "protected": false,
      "system": false
    },
    {
      "id": 2,
      "name": "Alice User",
      "role": "default",
      "status": "stop",
      "account": "agent-2",
      "user": "agent-2",
      "agent_id": "agent-2",
      "use_default_gateway_for_llm": false,
      "hidden": false,
      "protected": false,
      "system": false
    }
  ],
  "openviking": {
    "embedding": {
      "provider": "jina",
      "api_key_configured": true
    }
  }
}
```

`start` means the shared OpenViking service and that agent's Hermes service are
active. Otherwise the action returns `stop`. The reserved backend agent is
returned as a hidden, protected, system-owned entry so the UI can preserve it
without exposing it for normal management.

### `destroy-module`

**Path**: `imageroot/actions/destroy-module/`

| Step | File | Purpose |
|------|------|---------|
| 20 | `20destroy` | Stops and disables all known per-agent targets, removes runtime containers and per-agent named volumes, deletes generated per-agent runtime files, and removes the shared OpenViking runtime state. |

### Base actions used but not customized

The current repository does not customize:

- `get-status`
- `update-module`

No `update-module.d/` scripts are currently shipped.

The current checked-in refactor covers fresh installs only. No in-place upgrade
path from the older split Hermes plus gateway runtime is implemented here.

## Runtime State Files

The module runtime uses these state files:

- `environment`: shared NS8 state; stores `AGENTS_LIST` and public smarthost
  settings plus the NS8-allocated `OPENVIKING_PORT` alias, the effective `TIMEZONE`, and the reserved Hermes API publish port
- `secrets.env`: shared sensitive values such as `SMTP_PASSWORD`, the shared `OPENVIKING_ROOT_API_KEY`, and the shared OpenViking embedding API key
- `systemd.env`: generated controlled subset of environment values used only by
  systemd units
- `agent-<id>.env`: per-agent public runtime env file, including local
  OpenViking client settings for Hermes (`OPENVIKING_ENDPOINT`,
  `OPENVIKING_ACCOUNT`, `OPENVIKING_USER`, and `OPENVIKING_AGENT_ID`)
- `agent-<id>_secrets.env`: per-agent sensitive runtime env file, including a
  preserved tenant-scoped `OPENVIKING_API_KEY`; `agent-0_secrets.env` also stores the reserved Hermes `API_SERVER_KEY`
- `openviking.conf`: shared OpenViking server config bind-mounted into the shared
  OpenViking container with the matching `server.root_api_key`, a fixed `vlm` block targeting the reserved Hermes backend, and an optional `embedding.dense` block from shared module settings

Containers load only the per-agent env and secrets files. They do not load the
shared `environment` or shared `secrets.env` directly. The shared OpenViking
container bind-mounts `openviking.conf` at `/app/ov.conf`.

## Helper Scripts And Shared Runtime Code

### `discover-smarthost`

**Path**: `imageroot/bin/discover-smarthost`

This helper:

- connects to the local Redis replica
- reads cluster SMTP settings through the NS8 agent helpers
- writes public SMTP values into `environment`
- writes `SMTP_PASSWORD` into `secrets.env`
- removes the legacy `smarthost.env` file if present

### `sync-agent-runtime`

**Path**: `imageroot/bin/sync-agent-runtime`

This helper:

- reads the stored agent roster
- writes `systemd.env` from controlled image variables plus the create-module-persisted OpenViking port and reserved Hermes API publish port
- passes through the saved `TIMEZONE` from `environment` so the shared OpenViking and Hermes containers run with the same timezone
- writes `agent-<id>.env`, `agent-<id>_secrets.env`, and `openviking.conf`
- seeds `/opt/data/SOUL.md` for started user-facing agents using the selected role profile, while preserving customized files that no longer match the last module-generated seed
- runs `hermes config set ...` inside each opted-in agent volume so Hermes-native
  `config.yaml` and `.env` stay aligned with the hidden shared gateway endpoint
  and key when `use_default_gateway_for_llm` is enabled
- generates and preserves one shared `OPENVIKING_ROOT_API_KEY`
- generates and preserves the reserved Hermes API server key used by shared OpenViking
- removes stale per-agent runtime files for deleted agents

### `ensure-openviking-tenant`

**Path**: `imageroot/bin/ensure-openviking-tenant`

This helper:

- waits for the shared OpenViking service health endpoint
- creates or repairs the per-agent OpenViking account and admin user
- preserves an existing tenant key when it is still valid
- writes the tenant user key back into `agent-<id>_secrets.env`

### `start-agent-services`

**Path**: `imageroot/bin/start-agent-services`

This helper:

- refreshes smarthost data
- regenerates runtime env files
- reloads the user systemd daemon
- starts the shared OpenViking service whenever the reserved Hermes backend or any user agent requires it
- starts the dedicated `hermes-agent-hermes-system.service` reserved backend
- starts or stops `hermes-agent@<id>.target` based on the desired state
- cleans stale runtime files, runtime containers, per-agent named volumes, and removed-agent OpenViking accounts

### `reload-agent-services`

**Path**: `imageroot/bin/reload-agent-services`

This helper refreshes smarthost data and restarts only currently active agent
targets.

### Shared helper module

**Path**: `imageroot/pypkg/hermes_agent_runtime.py`

This module centralizes:

- agent validation
- `AGENTS_LIST` serialization and parsing
- hidden reserved system-agent synthesis and metadata
- shared OpenViking embedding settings validation and persistence
- runtime-file generation
- Hermes-native per-agent gateway client configuration through `hermes config set`
- shared OpenViking config and tenant provisioning
- per-agent named volume naming and cleanup
- systemd unit naming
- runtime status checks
- cleanup helpers

## Systemd User Units

The checked-in unit templates under `imageroot/systemd/user/` are:

- `hermes-agent@.target`: umbrella target for one agent stack
- `hermes-agent-openviking.service`: runs the shared OpenViking container
- `hermes-agent-hermes@.service`: runs the Hermes container in gateway mode
- `hermes-agent-hermes-system.service`: runs the reserved always-on Hermes container for the shared OpenViking backend

Starting `hermes-agent@1.target` ensures the shared OpenViking service is up,
provisions the agent tenant if needed, and starts the per-agent Hermes runtime
container.

The container services use `systemd.env` only for controlled image variables and
inject per-agent runtime data through:

- `%S/state/agent-%i.env`
- `%S/state/agent-%i_secrets.env`

The current persistent storage layout is:

- `hermes-agent-hermes@.service` mounts the per-agent named volume
  `hermes-agent-hermes-data-%i` at `/opt/data`
- `hermes-agent-hermes-system.service` mounts `hermes-agent-hermes-data-0` at `/opt/data` and publishes the Hermes API server only on `127.0.0.1:${HERMES_SYSTEM_API_PORT}` for module-internal use
- `hermes-agent-openviking.service` mounts the shared named volume
  `hermes-agent-openviking-data` at `/app/data`
- `hermes-agent-openviking.service` bind-mounts `%S/state/openviking.conf` at
  `/app/ov.conf`

The Hermes wrapper preserves the upstream Hermes Docker entrypoint and defaults
directly to `gateway run`, so the Hermes data volume is bootstrapped on first
start with default `.env`, `config.yaml`, `SOUL.md`, and bundled skills.

## Events

### `smarthost-changed`

**Path**: `imageroot/events/smarthost-changed/`

| Step | File | Purpose |
|------|------|---------|
| 10 | `10reload_services` | Delegates to `reload-agent-services` so only active agent targets are refreshed when shared SMTP settings change. |

## Embedded Admin UI

The module includes a Vue 2 based NS8 admin UI under `ui/`.

Current UI behavior relevant to the backend:

- the `Settings` view reads data through `get-configuration`
- the `Settings` view writes the visible agent roster plus shared OpenViking embedding settings through `configure-module`
- the `Settings` view filters the reserved system backend from the visible table and warns when the embedding provider changes after initial setup
- the UI already models `start` and `stop` status per agent
- the backend now persists desired status and returns actual runtime status plus hidden, protected, and system flags for each returned agent

## Testing

The checked-in smoke test is `tests/kickstart.robot`.

It validates this flow:

1. install the module
2. configure two agents with mixed `start` and `stop` state
3. verify shared runtime files plus running-agent runtime files exist
4. verify `get-configuration` reports actual runtime status and tenant metadata
5. verify the shared OpenViking service, the per-agent target, the runtime
  container service, and container state for the active agent, and verify
  inactive target plus absent runtime container state for the stopped agent
6. verify the active agent creates the expected named volumes and preserves
  Hermes and OpenViking data across `hermes-agent@<id>.target` restart
7. reconfigure the roster so both agents start and verify the shared OpenViking
  admin API enforces account isolation
8. reconfigure the roster to remove one agent and verify cleanup of the removed
  agent runtime, named volume, and OpenViking account
9. remove the module

## What Is Not Implemented In This Tree

The current repository does not implement these behaviors:

- no Traefik route management
- no HTTP endpoint published by the module itself
- no custom `create-module` or `get-status` steps
- no backup, restore, clone, or transfer-state helpers
- no firewall management hooks
- no LDAP or user-domain integration

If the module grows beyond this runtime, update this document from the checked-in
tree before describing additional lifecycle details.