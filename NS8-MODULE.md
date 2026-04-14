# NS8 Module Notes

This document summarizes the current checked-in NS8 behavior for `ns8-hermes-agent`.

## Overview

`ns8-hermes-agent` is now a simple per-agent Hermes NS8 module with one Hermes container for each configured agent.

- No OpenViking runtime
- No hidden system agent
- No shared backend API service
- No companion frontend container
- One configured agent equals one runtime service and one container

The implementation keeps the module lifecycle explicit:

- `create-module`: initialize module state only
- `configure-module`: validate agent input, persist one metadata file per agent, and reconcile routes and services
- `get-configuration`: report the shared dashboard host plus configured agents, preserving desired status and exposing actual runtime state separately
- `destroy-module`: stop services, remove managed routes, and remove generated state

## Images

The module publishes:

- `ghcr.io/nethserver/hermes-agent`: the NS8 module image
- `ghcr.io/nethserver/hermes-agent-hermes`: the Hermes wrapper image built from `docker.io/nousresearch/hermes-agent:0.0.9`

`build-images.sh` builds only these two images.

The module image reserves 30 TCP ports and declares `traefik@node:routeadm node:portsadm` authorizations so it can publish one dashboard route per agent and repair the reserved port pool during upgrades.

## Input model

`configure-module` accepts:

```json
{
  "base_virtualhost": "agents.example.org",
  "agents": [
    {
      "id": 1,
      "name": "Foo Bar",
      "role": "developer",
      "status": "start"
    }
  ]
}
```

Rules:

- `base_virtualhost` is optional and must be a valid FQDN when present
- `id` must be an integer between `1` and `30`
- `name` accepts letters and spaces only
- `role` must match the shipped role list
- `status` is `start` or `stop`

## Output model

`get-configuration` returns:

```json
{
  "base_virtualhost": "agents.example.org",
  "agents": [
    {
      "id": 1,
      "name": "Foo Bar",
      "role": "developer",
      "status": "start",
      "runtime_status": "start"
    }
  ]
}
```

`base_virtualhost` is the shared Traefik host for all agent Hermes dashboard routes.
`status` is the persisted desired state.
`runtime_status` is derived from `systemctl --user is-active hermes-agent@<id>.service`.

## State files

Module-wide state:

- `environment`
- `secrets.env`

Per-agent state:

- `agents/<id>/metadata.json`
- `agents/<id>/home/SOUL.md`
- `agents/<id>/home/.env`
- `agent_<id>.env`
- `agent_<id>_secrets.env`

Shared SMTP values come from `discover-smarthost`:

- public SMTP keys are merged into `environment`
- `SMTP_PASSWORD` is written into `secrets.env`

`sync-agent-runtime` copies the relevant shared SMTP values into each generated Hermes env file and per-agent secrets file.

## Service model

The shipped unit is:

- `imageroot/systemd/user/hermes-agent@.service`

For agent `1`, the runtime looks like:

- systemd service: `hermes-agent@1.service`
- Hermes container: `hermes-agent-1`
- Hermes home bind mount: `%S/state/agents/1/home` mounted at `/opt/data`
- published dashboard port: `127.0.0.1:<allocated-port>` forwarded to container port `9119`

Restart supervision is owned by `hermes-agent@<id>.service` with `Restart=on-failure`; the Podman container launches do not set container-level restart policies.
The single Hermes container serves both `hermes gateway run` and the Hermes web dashboard.
If `base_virtualhost` is set, Traefik forwards `https://<base_virtualhost>/hermes-agent-N/` to the dashboard listener selected from the module-owned 30-port pool.

## Template seeding

The module seeds two files into each agent home when they do not already exist:

- `SOUL.md`, from `imageroot/templates/SOUL/<role>.md.in`
- `.env`, from `imageroot/templates/home.env.in`

Placeholder replacement is performed with `sed` inside `sync-agent-runtime`.
If a seeded `SOUL.md` or `.env` still matches the previously generated content, it is refreshed when the agent name or role changes; customized files are preserved.

## Action flow

### `create-module`

- loads JSON input and ignores its content
- persists `TIMEZONE`
- creates `agents/` and `secrets.env`
- runs `discover-smarthost`
- does not create or start any agent runtime
- relies on the module image label to reserve 30 TCP ports for later per-agent dashboard publishing

### `configure-module`

- validates the submitted agent list
- validates and persists `base_virtualhost` when present
- writes one `metadata.json` file per agent
- removes deleted agents and their managed Traefik routes
- runs `discover-smarthost`
- runs `sync-agent-runtime`
- creates or updates one Traefik route per configured agent when `base_virtualhost` is set so it reaches the Hermes dashboard, or deletes managed routes when it is cleared
- reloads the user systemd manager
- enables and starts `hermes-agent@<id>.service` only for agents with `status: start`
- disables and stops services for agents with `status: stop`

### `destroy-module`

- disables and stops every known `hermes-agent@<id>.service`
- removes every managed Traefik route
- removes every `hermes-agent-<id>` container if present
- removes generated per-agent env files and state directories

### `update-module`

- runs `update-module.d/10ensure_tcp_ports`
- backfills `TCP_PORT` and `TCP_PORTS_RANGE` on older instances that predate the per-agent dashboard port reservation
- uses the NS8 port-allocation API instead of inventing unmanaged host ports locally

## Testing contract

The checked-in tests cover:

- install with zero active agent services
- configure with zero agents
- create one started agent and verify service/container/files/route
- stop the agent and verify inactive runtime
- remove the agent and verify cleanup
- remove the module and verify instance cleanup