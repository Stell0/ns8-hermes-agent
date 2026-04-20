<p align="center">
  <img alt="image" src="https://github.com/Stell0/ns8-hermes-agent/blob/main/logo.png" />
</p>

# ns8-hermes-agent

`ns8-hermes-agent` is an NS8 module that manages one or more Hermes Agent runtimes.

<img width="1397" height="761" alt="image" src="https://github.com/user-attachments/assets/631c598a-9553-4a21-8ff5-f002568f0bbe" />

## Quickstart

Install the module with

```bash
add-module ghcr.io/nethserver/hermes-agent:latest 1
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
- One configured agent maps directly to one metadata file, one generated Hermes env file, one generated Hermes secrets env file, one Podman-managed Hermes home volume, one primary systemd user service, one dashboard sidecar service, one rootless Podman pod, and two rootless Podman containers.
- A fresh install is idle until at least one agent is configured with `status: start`.
- `SOUL.md` and the default Hermes home `.env` are seeded exactly once per agent volume during `configure-module` by a one-shot Hermes container that mounts the checked-in templates plus the generated public agent env file.
- The module reserves a fixed pool of 30 TCP ports and supports at most 30 agents.

## Current behavior

- `create-module` seeds minimal module state in `environment`, `secrets.env`, and `agents/`, records `TIMEZONE`, and discovers smarthost settings.
- `configure-module` validates the submitted agent list plus the shared dashboard virtualhost and optional `lets_encrypt` switch, stores one metadata file per agent, generates per-agent runtime files, seeds first-time agent home content, reconciles Traefik dashboard routes, and enables or disables the corresponding `hermes@<id>.service` instances.
- `get-configuration` returns the shared `base_virtualhost`, the shared `lets_encrypt` setting, and the configured agents with their persisted desired `status`.
- `get-agent-runtime` returns live per-agent `runtime_status` derived from the current systemd service state.
- `destroy-module` stops agent services, removes agent pods and containers, deletes managed Traefik routes, and deletes generated per-agent files plus per-agent Hermes home volumes.
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

Operator-visible runtime names are `hermes-pod-<id>` for the pod, `hermes-<id>` for the gateway container, `hermes-dashboard-<id>` for the dashboard container, and `hermes@.service` for the primary systemd unit. Managed Traefik route instance names remain `<module_id>-hermes-agent-<id>`, and the Hermes home volume name remains `hermes-agent-<id>-home` for compatibility across the refactor.

## Repository layout

- `imageroot/`: NS8 actions, helper scripts, templates, event handler, state helper module, and the user systemd units.
- `containers/`: the Hermes wrapper image sources.
- `ui/`: embedded Vue 2 admin UI.
- `tests/`: Robot Framework integration checks and focused Python unit tests.

See `STRUCTURE.md` for a file map.

## Build

Build the module image and Hermes wrapper image with:

```bash
bash build-images.sh
```

The Hermes wrapper image is built from `docker.io/nousresearch/hermes-agent:v2026.4.16`.

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

The `configure-module` payload accepts a shared `base_virtualhost`, an optional shared `lets_encrypt` boolean, and an `agents` array.

`base_virtualhost` is optional. When set, each configured agent is published at `https://<base_virtualhost>/hermes-N/` through Traefik, and the route forwards to that agent's Hermes web dashboard.
Submit an empty value to remove all managed dashboard routes.

`lets_encrypt` is optional. When `true`, Traefik requests a Let's Encrypt certificate for the shared dashboard host. The flag applies to the shared host, not to individual agents.
Changing the shared host, clearing it, or turning `lets_encrypt` off makes the module update or remove the managed routes and request any needed certificate cleanup on the Traefik side.

Each agent contains:

- `id`: integer starting from `1` and capped at `30`
- `name`: letters and spaces only
- `role`: one of `default`, `developer`, `marketing`, `sales`, `customer_support`, `social_media_manager`, `business_consultant`, or `researcher`
- `status`: `start` or `stop`

Example:

```bash
api-cli run module/hermes-agent1/configure-module --data '{"base_virtualhost":"agents.example.org","lets_encrypt":true,"agents":[{"id":1,"name":"Foo Bar","role":"developer","status":"start"}]}'
```

That configuration will:

- store `agents/1/metadata.json`
- generate `agent_1.env` and `agent_1_secrets.env`
- run a one-shot `podman run --entrypoint /bin/sh` seed step that mounts `hermes-agent-1-home:/opt/data`, mounts the checked-in templates at `/templates`, and creates `/opt/data/SOUL.md` plus `/opt/data/.env` only when they do not already exist
- create or update the Traefik route `https://agents.example.org/hermes-1/`
- enable and start `hermes@1.service`
- create one rootless Podman pod, `hermes-pod-1`, containing the gateway container `hermes-1` and the dashboard container `hermes-dashboard-1`

Read the current configuration with:

```bash
api-cli run module/hermes-agent1/get-configuration --data '{}'
```

Example output:

```json
{"base_virtualhost": "agents.example.org", "lets_encrypt": true, "agents": [{"id": 1, "name": "Foo Bar", "role": "developer", "status": "start"}]}
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

## Runtime unit

The shipped user units are `imageroot/systemd/user/hermes@.service`, `imageroot/systemd/user/hermes-dashboard@.service`, and `imageroot/systemd/user/hermes-pod@.service`.

Each started agent runs:

- one primary `systemctl --user` service instance: `hermes@<id>.service`
- one companion dashboard service instance: `hermes-dashboard@<id>.service`
- one Podman pod: `hermes-pod-<id>`
- one Hermes gateway container: `hermes-<id>`
- one Hermes dashboard container: `hermes-dashboard-<id>`
- one Podman-managed Hermes home volume mounted at `/opt/data`
- one published dashboard port from the module-owned 30-port pool, forwarded from the pod to container port `9119`

Restart supervision is owned by the systemd user units with `Restart=on-failure`; the Podman pod and container launches do not set container-level restart policies.
The service creates one named volume per agent and mounts it at `/opt/data` with a keep-id user namespace.
Managed `SOUL.md` and home `.env` seeding runs before service start in `configure-module/75seed-agent-home`; later agent edits preserve existing files inside the volume.
The Hermes gateway container reads `agent_<id>.env` and `agent_<id>_secrets.env`; the dashboard container reads the shared volume and probes the gateway over the pod network namespace.
If `base_virtualhost` is set, Traefik forwards `https://<base_virtualhost>/hermes-N/` to the pod-published dashboard port.

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
- one started agent produces one pod, two services, two containers, one route with the configured shared TLS mode, one isolated volume, and one isolated generated file set
- stopping an agent disables the runtime without deleting its generated files or volume
- removing an agent cleans the runtime files and volume
- removing the module cleans the instance state

## Uninstall

Remove the instance with:

```bash
remove-module --no-preserve hermes-agent1
```
