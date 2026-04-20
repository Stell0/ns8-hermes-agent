# NS8 Module Notes

This document summarizes the current checked-in NS8 behavior for `ns8-hermes-agent`.

## Overview

`ns8-hermes-agent` is now a simple per-agent Hermes NS8 module with one Podman pod for each configured agent.

- No OpenViking runtime
- No hidden system agent
- No shared backend API service
- No shared frontend runtime outside the per-agent Hermes dashboard sidecar
- One configured agent equals one primary service, one dashboard sidecar service, one pod, and two containers

The implementation keeps the module lifecycle explicit:

- `create-module`: initialize module state only
- `configure-module`: validate agent input, persist shared dashboard settings plus one metadata file per agent, seed first-time agent home content, and reconcile routes and services
- `get-configuration`: report the shared dashboard host, shared `lets_encrypt` flag, and configured agents, preserving desired status only
- `get-agent-runtime`: report live per-agent runtime state derived from systemd
- `destroy-module`: stop services, remove managed routes, and remove generated state

## Images

The module publishes:

- `ghcr.io/nethserver/hermes-agent`: the NS8 module image
- `ghcr.io/nethserver/hermes-agent-hermes`: the Hermes wrapper image built from `docker.io/nousresearch/hermes-agent:v2026.4.16`

`build-images.sh` builds only these two images.

The module image reserves 30 TCP ports and declares `traefik@node:routeadm node:portsadm` authorizations so it can publish one dashboard route per agent and repair the reserved port pool during upgrades.

## Input model

`configure-module` accepts:

```json
{
  "base_virtualhost": "agents.example.org",
  "lets_encrypt": true,
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
- `lets_encrypt` is optional and must be boolean when present
- `id` must be an integer between `1` and `30`
- `name` accepts letters and spaces only
- `role` must match the shipped role list
- `status` is `start` or `stop`

## Output model

`get-configuration` returns:

```json
{
  "base_virtualhost": "agents.example.org",
  "lets_encrypt": true,
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

`base_virtualhost` is the shared Traefik host for all agent Hermes dashboard routes.
`lets_encrypt` controls whether Traefik should request a Let's Encrypt certificate for that shared host.
`status` is the persisted desired state.

`get-agent-runtime` returns:

```json
{
  "agents": [
    {
      "id": 1,
      "runtime_status": "start"
    }
  ]
}
```

`runtime_status` is derived from `systemctl --user is-active hermes@<id>.service`.

## State files

Module-wide state:

- `environment`
- `secrets.env`

Per-agent state files:

- `agents/<id>/metadata.json`
- `agent_<id>.env`
- `agent_<id>_secrets.env`

Per-agent Podman volume:

- `hermes-agent-<id>-home`, mounted at `/opt/data`
- bootstrap-managed content inside the volume includes the seeded `SOUL.md`, `.env`, and `config.yaml`, plus the runtime directory skeleton used by Hermes

Managed Traefik route instance names remain `<module_id>-hermes-agent-<id>`, and Hermes home volume names remain `hermes-agent-<id>-home` for compatibility across the runtime refactor.

Shared SMTP values come from `discover-smarthost`:

- public SMTP keys are merged into `environment`
- `SMTP_PASSWORD` is written into `secrets.env`

`sync-agent-runtime` copies the relevant shared SMTP values into each generated Hermes env file and per-agent secrets file.

## Service model

The shipped units are:

- `imageroot/systemd/user/hermes@.service`
- `imageroot/systemd/user/hermes-dashboard@.service`
- `imageroot/systemd/user/hermes-pod@.service`

For agent `1`, the runtime looks like:

- primary systemd service: `hermes@1.service`
- companion dashboard service: `hermes-dashboard@1.service`
- Podman pod: `hermes-pod-1`
- Hermes gateway container: `hermes-1`
- Hermes dashboard container: `hermes-dashboard-1`
- Hermes home named volume: `hermes-agent-1-home` mounted at `/opt/data`
- published dashboard port: `127.0.0.1:<allocated-port>` forwarded from the pod to container port `9119`

Restart supervision is owned by `hermes@<id>.service` and `hermes-dashboard@<id>.service` with `Restart=on-failure`; the Podman pod and container launches do not set container-level restart policies.
The service creates one Podman-managed volume per agent and mounts it with `--userns=keep-id`.
Managed `SOUL.md` and the default Hermes home `.env` are seeded in `configure-module/75seed-agent-home` before `hermes@<id>.service` starts. Later configure runs preserve existing files inside the volume.
The gateway container runs `hermes gateway run`, while the sidecar dashboard container runs `hermes dashboard --host 0.0.0.0` against the shared pod network namespace.
If `base_virtualhost` is set, Traefik forwards `https://<base_virtualhost>/hermes-N/` to the dashboard listener selected from the module-owned 30-port pool.

## Template seeding

The runtime manages two files inside each agent volume:

- `SOUL.md`, from `imageroot/templates/SOUL/<role>.md.in`
- `.env`, from `imageroot/templates/home.env.in`

Placeholder replacement is performed inside the one-shot `configure-module/75seed-agent-home` container by mounting the checked-in templates at `/templates` and the per-agent volume at `/opt/data`.
The seed step consumes only the generated public `agent_<id>.env` file plus `AGENT_ID`, `AGENT_NAME`, and `AGENT_ROLE` substitutions.
Seeding is strict first-write only: later agent edits preserve existing `SOUL.md` and `.env` content in the volume.

## Action flow

### `create-module`

- loads JSON input and ignores its content
- `10initialize-state`: persists `TIMEZONE` and creates `agents/` plus `secrets.env`
- `20discover-smarthost`: refreshes shared SMTP settings
- does not create or start any agent runtime
- relies on the module image label to reserve 30 TCP ports for later per-agent dashboard publishing

### `configure-module`

- `10validate-input`: validates the submitted agent list, optional shared virtualhost, and optional shared `lets_encrypt`
- `20persist-shared-env`: persists `base_virtualhost` plus `lets_encrypt`, tracks previous values for route cleanup, and backfills `TIMEZONE` when missing
- `30remove-deleted-routes`: deletes managed Traefik routes for removed agents when routing is active, including one-time certificate cleanup when all routes are removed
- `40remove-deleted-agents`: stops removed services, removes removed pods and containers, cleans legacy single-container leftovers, and delegates generated-state cleanup to `remove-agent-state`
- `50write-agent-metadata`: writes one `metadata.json` file per desired agent
- `60refresh-shared-settings`: runs `discover-smarthost`
- `70sync-agent-runtime`: runs `sync-agent-runtime`
- `75seed-agent-home`: runs a one-shot Hermes container to seed first-time `/opt/data/SOUL.md` and `/opt/data/.env` content from checked-in templates
- `80reload-systemd`: reloads the user systemd manager
- `90reconcile-desired-routes`: creates, updates, or clears one Traefik route per desired agent when `base_virtualhost` is configured or explicitly changed, including `lets_encrypt` cleanup for host changes or shared TLS disable events
- `95reconcile-agent-services`: enables and starts `hermes@<id>.service` for desired `start` agents and disables or stops the rest

### `get-configuration`

- `20read`: returns the shared `base_virtualhost` plus the configured agents with desired persisted status only

### `get-agent-runtime`

- `10read`: inspects `systemctl --user is-active hermes@<id>.service` for each configured agent and returns live `runtime_status`

### `destroy-module`

- `10remove-routes`: removes every managed Traefik route, including one-time certificate cleanup when shared `lets_encrypt` is enabled
- `20stop-services`: disables and stops every known `hermes@<id>.service`, stops each per-agent pod, removes the gateway and dashboard containers if present, and disables any legacy `hermes-agent@<id>.service` leftovers
- `30remove-agent-state`: delegates generated-state cleanup for each known agent to `remove-agent-state`
- `40remove-agents-root`: removes the top-level `agents/` directory

### `update-module`

- runs `update-module.d/10ensure_tcp_ports`
- backfills `TCP_PORT` and `TCP_PORTS_RANGE` on older instances that predate the per-agent dashboard port reservation
- uses the NS8 port-allocation API instead of inventing unmanaged host ports locally

## Testing contract

The checked-in tests cover:

- install with zero active agent services
- configure with zero agents
- create one started agent and verify service/container/volume/files/route
- stop the agent and verify inactive runtime with retained generated files and volume
- remove the agent and verify cleanup, including volume removal
- remove the module and verify instance cleanup