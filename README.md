<p align="center">
  <img alt="image" src="https://github.com/Stell0/ns8-hermes-agent/blob/main/logo.png" />
</p>

# ns8-hermes-agent

`ns8-hermes-agent` is an NS8 module that manages one or more Hermes Agent runtimes.

<img width="1397" height="761" alt="image" src="https://github.com/user-attachments/assets/631c598a-9553-4a21-8ff5-f002568f0bbe" />

## Quickstart

Install the module with

```bash
add-module ghcr.io/stell0/hermes-agent:latest 1
```
Configure at least one agent from the UI or with:

```bash
api-cli run module/hermes-agent1/configure-module --data '{"agents":[{"id":1,"name":"Foo Bar","role":"developer","status":"start"}]}'
```

Configure the LLM provider from Hermes console
```bash
runagent -m hermes-agent1 podman exec -it hermes-1 hermes setup
```

Configure a messaging platform like Telegram from Hermes console
```bash
runagent -m hermes-agent1 podman exec -it hermes-1 hermes gateway setup
```
When you are done, exit the console and restart the agent to pick up the new configuration:

```bash
runagent -m hermes-agent1 systemctl --user restart hermes@1.service
```

## Accessing the agent console
You can access the Hermes console for an agent with:

```bash
runagent -m hermes-agent1 podman exec -it hermes-1 hermes
```

## Repository guidelines

The current implementation is intentionally small:

- One dedicated Podman pod per configured agent.
- One configured agent maps directly to one metadata file, one generated Hermes env file, one generated Hermes secrets env file, one Podman-managed Hermes home volume, one primary systemd user service, two sidecar services, one rootless Podman pod, and three rootless Podman containers.
- A fresh install is idle until at least one agent is configured with `status: start`.
- `SOUL.md` and the default Hermes home `.env` are seeded exactly once per agent volume during `configure-module` by a one-shot Hermes container that mounts the checked-in templates plus the generated public agent env file.
- The module reserves a fixed pool of 30 TCP ports and supports at most 30 agents.
- The module is now an NS8 account consumer and can bind one shared `user_domain` plus one per-agent `allowed_user` for published dashboard authentication.

## Current behavior

- `create-module` seeds minimal module state in `environment`, `secrets.env`, and `agents/`, records `TIMEZONE`, and discovers smarthost settings.
- `configure-module` validates the submitted agent list plus the shared dashboard virtualhost, optional shared `user_domain`, and optional `lets_encrypt` switch, binds the selected NS8 user domain when set, stores one metadata file per agent, generates per-agent runtime files, seeds first-time agent home content, reconciles Traefik dashboard routes, and enables or disables the corresponding `hermes@<id>.service` instances.
- `get-configuration` returns the shared `base_virtualhost`, the shared `user_domain`, the shared `lets_encrypt` setting, and the configured agents with their persisted desired `status` plus `allowed_user`.
- `get-agent-runtime` returns live per-agent `runtime_status` derived from the current systemd service state.
- `destroy-module` stops agent services, removes agent pods and containers including the auth sidecar, deletes managed Traefik routes, and deletes generated per-agent files plus per-agent Hermes home volumes.
- `update-module` backfills the module-owned 30-port TCP allocation on older instances that predate per-agent dashboard publishing.
- `discover-smarthost` still merges shared SMTP settings into `environment` and `secrets.env`.

## Generated state

Module-wide files:

- `environment`
- `secrets.env`

Per-agent files:

- `agents/<id>/metadata.json`
- `agent_<id>.env`
- `agent_<id>_secrets.env`

Per-agent Podman volume:

- `hermes-agent-<id>-home`, mounted at `/opt/data`
- bootstrap-managed content inside the volume includes the seeded `SOUL.md`, `.env`, and `config.yaml`, plus the runtime directory skeleton used by Hermes

Operator-visible runtime names are `hermes-pod-<id>` for the pod, `hermes-<id>` for the gateway container, `hermes-dashboard-<id>` for the internal dashboard container, `hermes-auth-<id>` for the published auth proxy container, and `hermes@.service` for the primary systemd unit. Managed Traefik route instance names remain `<module_id>-hermes-agent-<id>`, and the Hermes home volume name remains `hermes-agent-<id>-home` for compatibility across the refactor.

## Repository layout

- `imageroot/`: NS8 actions, helper scripts, templates, event handler, state helper module, and the user systemd units.
- `containers/`: the Hermes wrapper image sources plus the dashboard auth proxy image.
- `ui/`: embedded Vue 2 admin UI.
- `tests/`: Robot Framework integration checks and focused Python unit tests.

See `STRUCTURE.md` for a file map.

## Build

Build the module image, auth proxy image, and Hermes wrapper image with:

```bash
bash build-images.sh
```

The Hermes wrapper image is built from `docker.io/nousresearch/hermes-agent:v2026.4.16`. When the dashboard container starts, the wrapper patches the upstream web sources under `/opt/hermes/web`, rebuilds the dashboard locally, and injects both `window.__HERMES_BASE_URL__` and an HTML `<base href>` into the served `index.html` so built assets resolve correctly under the shared virtualhost path.

The script uses:

- `REPOBASE`, default `ghcr.io/nethserver`
- `IMAGETAG`, default `latest`

## Install

Instantiate the module with:

```bash
add-module ghcr.io/nethserver/hermes-agent:latest 1
```

Example output:

```json
{"module_id": "hermes-agent1", "image_name": "hermes-agent", "image_url": "ghcr.io/nethserver/hermes-agent:latest"}
```

No agent is created during install.

## Configure

The `configure-module` payload accepts a shared `base_virtualhost`, an optional shared `user_domain`, an optional shared `lets_encrypt` boolean, and an `agents` array.

`base_virtualhost` is optional. When set, each configured agent is published at `https://<base_virtualhost>/hermes-N/` through Traefik, and the route forwards to that agent's Hermes web dashboard.
Submit an empty value to remove all managed dashboard routes.

`user_domain` is optional while dashboard publishing is disabled. When `base_virtualhost` is set and at least one agent exists, `user_domain` becomes required and must match an NS8 user domain visible through `agent.ldapproxy`.

`lets_encrypt` is optional. When `true`, Traefik requests a Let's Encrypt certificate for the shared dashboard host. The flag applies to the shared host, not to individual agents.
Changing the shared host, clearing it, or turning `lets_encrypt` off makes the module update or remove the managed routes and request any needed certificate cleanup on the Traefik side.

Each agent contains:

- `id`: integer starting from `1` and capped at `30`
- `name`: letters and spaces only
- `role`: one of `default`, `developer`, `marketing`, `sales`, `customer_support`, `social_media_manager`, `business_consultant`, or `researcher`
- `status`: `start` or `stop`
- `allowed_user`: bare username from the selected NS8 `user_domain`; required when `base_virtualhost` is set and at least one agent is published

Example:

```bash
api-cli run module/hermes-agent1/configure-module --data '{"base_virtualhost":"agents.example.org","user_domain":"example.org","lets_encrypt":true,"agents":[{"id":1,"name":"Foo Bar","role":"developer","status":"start","allowed_user":"alice"}]}'
```

That configuration will:

- store `agents/1/metadata.json`
- generate `agent_1.env` and `agent_1_secrets.env`
- bind the module to the selected NS8 user domain and validate `allowed_user` against that domain
- run a one-shot `podman run --entrypoint /bin/sh` seed step that mounts `hermes-agent-1-home:/opt/data`, mounts the checked-in templates at `/templates`, and creates `/opt/data/SOUL.md` plus `/opt/data/.env` only when they do not already exist
- create or update the Traefik route `https://agents.example.org/hermes-1/`
- enable and start `hermes@1.service`
- create one rootless Podman pod, `hermes-pod-1`, containing the gateway container `hermes-1`, the internal dashboard container `hermes-dashboard-1`, and the published auth proxy container `hermes-auth-1`

Read the current configuration with:

```bash
api-cli run module/hermes-agent1/get-configuration --data '{}'
```

Example output:

```json
{"base_virtualhost": "agents.example.org", "user_domain": "example.org", "lets_encrypt": true, "agents": [{"id": 1, "name": "Foo Bar", "role": "developer", "status": "start", "allowed_user": "alice"}]}
```

`status` is the persisted desired state.

Read live runtime state with:

```bash
api-cli run module/hermes-agent1/get-agent-runtime --data '{}'
```

Example output:

```json
{"agents": [{"id": 1, "runtime_status": "start"}]}
```

`runtime_status` is derived from the actual systemd service state.

## Accessing the dashboard

If `base_virtualhost` is configured, each agent dashboard is available at `https://<base_virtualhost>/hermes-N/`.
Access is authenticated against the shared `user_domain`, and each route only admits that agent's configured `allowed_user`.
The auth proxy logs `auth_attempt`, `auth_success`, and `auth_failed` events to standard output for troubleshooting published dashboard access.

## Runtime unit

The shipped user units are `imageroot/systemd/user/hermes@.service`, `imageroot/systemd/user/hermes-dashboard@.service`, `imageroot/systemd/user/hermes-auth@.service`, and `imageroot/systemd/user/hermes-pod@.service`.

Each started agent runs:

- one primary `systemctl --user` service instance: `hermes@<id>.service`
- one companion dashboard service instance: `hermes-dashboard@<id>.service`
- one companion auth proxy service instance: `hermes-auth@<id>.service`
- one Podman pod: `hermes-pod-<id>`
- one Hermes gateway container: `hermes-<id>`
- one Hermes dashboard container: `hermes-dashboard-<id>`
- one Hermes dashboard auth container: `hermes-auth-<id>`
- one Podman-managed Hermes home volume mounted at `/opt/data`
- one published dashboard port from the module-owned 30-port pool, forwarded from the pod to auth proxy port `9119`

Restart supervision is owned by the systemd user units with `Restart=on-failure`; the Podman pod and container launches do not set container-level restart policies.
The shipped services create one named volume per agent mounted at `/opt/data`.
Managed `SOUL.md` and home `.env` seeding runs before service start in `configure-module/75seed-agent-home`; later agent edits preserve existing files inside the volume.
The Hermes gateway container reads `agent_<id>.env` and `agent_<id>_secrets.env`. The dashboard container reads the shared volume, probes the gateway over the pod network namespace, stays internal on `127.0.0.1:9120`, patches the upstream web sources at container start, rebuilds the dashboard, and serves an `index.html` patched at runtime with both the dashboard base URL and an HTML base tag. The auth proxy container reads the generated per-agent auth env and secrets, authenticates the route against LDAP, logs auth events to stdout, and owns the published pod port `9119`.
If `base_virtualhost` is set, Traefik forwards `https://<base_virtualhost>/hermes-N/` to the pod-published auth proxy port with `strip_prefix` and `X-Forwarded-Prefix` headers so the dashboard stays prefix-aware.

## UI development

The embedded UI lives in `ui/`.

For local UI work:

```bash
cd ui
yarn install
yarn serve
```

For a production bundle:

```bash
cd ui
yarn install
yarn build
```

If required by your environment, set `NODE_OPTIONS=--openssl-legacy-provider` before running the UI toolchain.

## Testing

Run the module test with:

```bash
./test-module.sh <NODE_ADDR> ghcr.io/nethserver/hermes-agent:latest
```

The checked-in tests cover the pruned contract:

- install produces no active agent runtime
- zero agents keeps the module idle
- one started agent produces one pod, three services, three containers, one auth-proxied route with the configured shared TLS mode, one isolated volume, and one isolated generated file set
- stopping an agent disables the runtime without deleting its generated files or volume
- removing an agent cleans the runtime files and volume
- removing the module cleans the instance state

## Uninstall

Remove the instance with:

```bash
remove-module --no-preserve hermes-agent1
```
