# NS8 Module Notes

This document summarizes the current checked-in NS8 behavior for `ns8-hermes-agent`.

## Overview

`ns8-hermes-agent` is now a simple per-agent Hermes NS8 module with one Podman pod for each configured agent.

- No OpenViking runtime
- No hidden system agent
- No shared backend API service
- No standalone dashboard sidecar runtime; the per-agent Hermes container runs dashboard and gateway together
- One configured agent equals one primary `hermes@<id>.service`, one per-agent pod owner unit, one pod, and one Hermes container, plus the shared auth service and container when publishing is active

The implementation keeps the module lifecycle explicit:

- `create-module`: initialize module state only
- `configure-module`: validate agent input, persist shared dashboard settings plus one metadata file per agent, bind the selected user domain, seed first-time agent home content, and reconcile routes and services
- `get-configuration`: report the shared dashboard host, shared `user_domain`, shared `lets_encrypt` flag, and configured agents, preserving desired status only
- `get-agent-runtime`: report live per-agent runtime state derived from systemd
- `destroy-module`: stop services, remove managed routes, and remove generated state

## Images

The module publishes:

- `ghcr.io/nethserver/hermes-agent`: the NS8 module image
- `ghcr.io/nethserver/hermes-agent-auth`: the shared dashboard auth proxy image
- `ghcr.io/nethserver/hermes-agent-hermes`: the Hermes wrapper image built from `docker.io/nousresearch/hermes-agent:v2026.4.23`
- `ghcr.io/nethserver/hermes-agent-socket`: the per-agent dashboard socket relay image

`build-images.sh` builds all four images.

The module image reserves one TCP port and declares `cluster:accountconsumer traefik@node:routeadm node:portsadm` authorizations so it can bind one NS8 user domain and publish one shared auth route.

## Input model

`configure-module` accepts:

```json
{
  "base_virtualhost": "agents.example.org",
  "user_domain": "example.org",
  "lets_encrypt": true,
  "agents": [
    {
      "id": 1,
      "name": "Foo Bar",
      "role": "developer",
      "status": "start",
      "allowed_user": "alice"
    }
  ]
}
```

Rules:

- `base_virtualhost` is optional and must be a valid FQDN when present
- `user_domain` is optional while dashboard publishing is disabled; when `base_virtualhost` is set and at least one agent exists it becomes required and must resolve through `agent.ldapproxy`
- `lets_encrypt` is optional and must be boolean when present
- `id` must be an integer between `1` and `30`
- `name` accepts letters and spaces only
- `role` must match the shipped role list
- `status` is `start` or `stop`
- `allowed_user` is a bare username from the selected `user_domain`; it is required for each published agent, validated against LDAP, and must be unique across the published agent set

## Output model

`get-configuration` returns:

```json
{
  "base_virtualhost": "agents.example.org",
  "user_domain": "example.org",
  "lets_encrypt": true,
  "agents": [
    {
      "id": 1,
      "name": "Foo Bar",
      "role": "developer",
      "status": "start",
      "allowed_user": "alice"
    }
  ]
}
```

`base_virtualhost` is the shared Traefik host for the module's shared auth entrypoint.
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
- ownership is repaired by a one-shot root helper from the configured Hermes image so `/opt/data` matches that image's dynamic `hermes` UID/GID rather than a hardcoded UID

The active managed Traefik route instance is `<module_id>-hermes-auth`. Hermes home volume names are `hermes-agent-<id>-home`.

Shared auth state files:

- `authproxy.env`
- `authproxy_secrets.env`
- `authproxy_agents.json`

Shared SMTP values come from `discover-smarthost`:

- public SMTP keys are merged into `environment`
- `SMTP_PASSWORD` is written into `secrets.env`

`sync-agent-runtime` copies the relevant shared SMTP values into each generated Hermes env file and per-agent secrets file, generates the shared auth runtime files, and ensures `HERMES_AUTH_SESSION_SECRET` exists in `secrets.env`.
When `USER_DOMAIN` is configured, `sync-agent-runtime` also writes these public env keys into each generated `agent_<id>.env` file:

- `AGENT_ALLOWED_USER`
- `USER_DOMAIN`
- `LDAP_HOST`
- `LDAP_PORT`
- `LDAP_BASE_DN`
- `LDAP_SCHEMA`

and these LDAP bind values into each generated `agent_<id>_secrets.env` file:

- `LDAP_BIND_DN`
- `LDAP_BIND_PASSWORD`

## Service model

The shipped units are:

- `imageroot/systemd/user/hermes@.service`
- `imageroot/systemd/user/hermes-socket@.service`
- `imageroot/systemd/user/hermes-auth.service`
- `imageroot/systemd/user/hermes-pod@.service`

For agent `1`, the runtime looks like:

- primary systemd service: `hermes@1.service`
- per-agent socket relay service: `hermes-socket@1.service`
- Podman pod: `hermes-pod-1`
- Hermes container: `hermes-1`
- dashboard socket relay container: `hermes-socket-1`
- Hermes home named volume: `hermes-agent-1-home` mounted at `/opt/data`
- shared auth listener: `127.0.0.1:${TCP_PORT}` forwarded to auth proxy port `9119`
- dashboard socket: `%S/state/dashboard-sockets/agent-1.sock`, mounted into the auth container as `/sockets/agent-1.sock`
- shared auth proxy service: `hermes-auth.service`
- Hermes auth proxy container: `hermes-auth`

Restart supervision is owned by `hermes@<id>.service` and `hermes-auth.service` with `Restart=on-failure`; the Podman pod and container launches do not set container-level restart policies.
The services invoke Podman and the runtime creates one Podman-managed volume per agent. Before each Hermes start, `hermes@<id>.service` runs `ensure-agent-home-ownership`, which uses the configured Hermes image to discover the current `hermes` UID/GID and repair `/opt/data` ownership without hardcoding numeric IDs.
Managed `SOUL.md` and the default Hermes home `.env` are seeded in `configure-module/75seed-agent-home` before `hermes@<id>.service` starts. Later configure runs preserve existing files inside the volume.
The Hermes container runs `hermes dashboard --host 127.0.0.1 --port 9120 --insecure --no-open -- gateway run` inside the pod. `hermes-socket@.service` joins the same pod, relays `127.0.0.1:9120` onto `%S/state/dashboard-sockets/agent-<id>.sock`, and the shared auth service mounts `%S/state/dashboard-sockets:/sockets:z`. The shared auth service listens on `9119`, authenticates access against the shared `user_domain` plus the generated `authproxy_agents.json` registry, preserves the dashboard upstream `Authorization` header, injects a trusted `X-Hermes-Authenticated-User` header derived from the authenticated session username while ignoring any client-supplied value for that header, and logs auth attempts plus outcomes to stdout while proxying to each agent's `upstream_socket`.
The Hermes wrapper no longer patches or rebuilds the upstream dashboard sources at container start.
If `base_virtualhost` is set, Traefik forwards `https://<base_virtualhost>/` to the shared auth listener on `TCP_PORT` using the route instance `<module>-hermes-auth`.

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
- relies on the module image label to reserve the shared auth listener `TCP_PORT`

### `configure-module`

- `10validate-input`: validates the submitted agent list, optional shared virtualhost, optional shared `user_domain`, and optional shared `lets_encrypt`
- `20persist-shared-env`: persists `base_virtualhost`, optional shared `user_domain`, plus `lets_encrypt`, tracks previous values for route cleanup, and backfills `TIMEZONE` when missing
- `25configure-user-domain`: binds or unbinds the module relation to the selected NS8 user domain
- `30remove-deleted-routes`: reserved lifecycle slot; removed-agent route cleanup is no longer needed because the module manages only the shared Traefik route
- `40remove-deleted-agents`: stops removed services, removes removed pods and containers including `hermes-socket-<id>`, and delegates generated-state cleanup to `remove-agent-state`
- `50write-agent-metadata`: writes one `metadata.json` file per desired agent, including persisted `allowed_user`
- `60refresh-shared-settings`: runs `discover-smarthost`
- `70sync-agent-runtime`: runs `sync-agent-runtime`, which now also fans out `AGENT_ALLOWED_USER` plus LDAP runtime env and secrets when `USER_DOMAIN` is set and writes `authproxy_agents.json` `upstream_socket` entries
- `75seed-agent-home`: runs a one-shot Hermes container to seed first-time `/opt/data/SOUL.md` and `/opt/data/.env` content from checked-in templates
- `80reload-systemd`: reloads the user systemd manager
- `90reconcile-desired-routes`: creates, updates, or clears the shared Traefik route instance `<module>-hermes-auth` when `base_virtualhost` is configured or explicitly changed, including `lets_encrypt` cleanup for host changes or shared TLS disable events
- `95reconcile-agent-services`: enables and starts both `hermes@<id>.service` and `hermes-socket@<id>.service` for desired `start` agents, disables or stops the rest, and manages the shared `hermes-auth.service` when publishing is active

### `list-user-domains`

- `10read`: lists user domains visible to the module through `agent.ldapproxy` for the admin UI selector

### `list-domain-users`

- `10read`: lists sorted LDAP users for the selected user domain so the admin UI can populate `allowed_user`

### `get-configuration`

- `20read`: returns the shared `base_virtualhost`, shared `user_domain`, and the configured agents with desired persisted status plus `allowed_user`

### `get-agent-runtime`

- `10read`: inspects `systemctl --user is-active hermes@<id>.service` for each configured agent and returns live `runtime_status`

### `destroy-module`

- `10remove-routes`: removes the shared Traefik route, including one-time certificate cleanup when shared `lets_encrypt` is enabled
- `20stop-services`: disables and stops every known `hermes@<id>.service`, stops each per-agent pod, removes the Hermes and auth proxy containers if present
- `30remove-agent-state`: delegates generated-state cleanup for each known agent to `remove-agent-state`
- `40remove-agents-root`: removes the top-level `agents/` directory

## Testing contract

The checked-in tests cover:

- install with zero active agent services
- configure with zero agents
- create one started agent and verify service/container/volume/files/route
- stop the agent and verify inactive runtime with retained generated files and volume
- remove the agent and verify cleanup, including volume removal
- remove the module and verify instance cleanup