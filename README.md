<img width="1397" height="761" alt="image" src="https://github.com/user-attachments/assets/631c598a-9553-4a21-8ff5-f002568f0bbe" />

# ns8-hermes-agent

`ns8-hermes-agent` is an NS8 module that manages one or more Hermes Agent runtimes.

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
runagent -m hermes-agent1 podman exec -it hermes-agent-1 hermes setup
```

Configure a messaging platform like Telegram from Hermes console
```bash
runagent -m hermes-agent1 podman exec -it hermes-agent-1 hermes gateway setup
```
When you are done, exit the console and restart the agent to pick up the new configuration:

```bash
runagent -m hermes-agent1 systemctl --user restart hermes-agent@1.service
```

## Accessing the agent console
You can access the Hermes console for an agent with:

```bash
runagent -m hermes-agent1 podman exec -it hermes-agent-1 hermes
```

## Repository guidelines

The current implementation is intentionally small:

- One dedicated Hermes container per configured agent.
- One configured agent maps directly to one metadata file, one generated Hermes env file, one generated Hermes secrets env file, one Hermes home directory, one systemd user service, and one rootless Podman container.
- A fresh install is idle until at least one agent is configured with `status: start`.
- `SOUL.md` is seeded from a checked-in role-specific template, and the default Hermes home `.env` is seeded from its checked-in template with `sed` placeholder replacement; previously generated files are refreshed on agent name or role changes unless the operator customized them.
- The module reserves a fixed pool of 30 TCP ports and supports at most 30 agents.

## Current behavior

- `create-module` seeds minimal module state in `environment`, `secrets.env`, and `agents/`, records `TIMEZONE`, and discovers smarthost settings.
- `configure-module` validates the submitted agent list and the shared dashboard virtualhost, stores one metadata file per agent, generates per-agent runtime files, reconciles Traefik dashboard routes, and enables or disables the corresponding `hermes-agent@<id>.service` instances.
- `get-configuration` returns the shared `base_virtualhost`, the configured agents, keeps the persisted desired `status`, and reports actual runtime state separately as `runtime_status`.
- `destroy-module` stops agent services, removes agent containers, deletes managed Traefik routes, and deletes generated per-agent files and directories.
- `update-module` backfills the module-owned 30-port TCP allocation on older instances that predate per-agent dashboard publishing.
- `discover-smarthost` still merges shared SMTP settings into `environment` and `secrets.env`.

## Generated state

Module-wide files:

- `environment`
- `secrets.env`

Per-agent files:

- `agents/<id>/metadata.json`
- `agents/<id>/home/SOUL.md`
- `agents/<id>/home/.env`
- `agent_<id>.env`
- `agent_<id>_secrets.env`

Operator-visible runtime names are `hermes-agent-<id>` for Hermes containers. The shipped systemd unit is the internal template `hermes-agent@.service`.

## Repository layout

- `imageroot/`: NS8 actions, helper scripts, templates, event handler, state helper module, and the user systemd unit.
- `containers/`: the Hermes wrapper image sources.
- `ui/`: embedded Vue 2 admin UI.
- `tests/`: Robot Framework integration checks and focused Python unit tests.

See `STRUCTURE.md` for a file map.

## Build

Build the module image and Hermes wrapper image with:

```bash
bash build-images.sh
```

The Hermes wrapper image is built from `docker.io/nousresearch/hermes-agent:0.0.9`.

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

The `configure-module` payload accepts a shared `base_virtualhost` and an `agents` array.

`base_virtualhost` is optional. When set, each configured agent is published at `https://<base_virtualhost>/hermes-agent-N/` through Traefik, and the route forwards to that agent's Hermes web dashboard.
Submit an empty value to remove all managed dashboard routes.

Each agent contains:

- `id`: integer starting from `1` and capped at `30`
- `name`: letters and spaces only
- `role`: one of `default`, `developer`, `marketing`, `sales`, `customer_support`, `social_media_manager`, `business_consultant`, or `researcher`
- `status`: `start` or `stop`

Example:

```bash
api-cli run module/hermes-agent1/configure-module --data '{"base_virtualhost":"agents.example.org","agents":[{"id":1,"name":"Foo Bar","role":"developer","status":"start"}]}'
```

That configuration will:

- store `agents/1/metadata.json`
- generate `agent_1.env` and `agent_1_secrets.env`
- seed `agents/1/home/SOUL.md` from the template for the agent role and `agents/1/home/.env` from the default home env template, then refresh those files on later name or role changes only when they still match the previous generated content
- create or update the Traefik route `https://agents.example.org/hermes-agent-1/`
- enable and start `hermes-agent@1.service`
- run one rootless Podman container, `hermes-agent-1`, that serves the Hermes gateway and web dashboard

Read the current configuration with:

```bash
api-cli run module/hermes-agent1/get-configuration --data '{}'
```

Example output:

```json
{"base_virtualhost": "agents.example.org", "agents": [{"id": 1, "name": "Foo Bar", "role": "developer", "status": "start", "runtime_status": "start"}]}
```

`status` is the persisted desired state. `runtime_status` is derived from the actual systemd service state.

## Accessing the dashboard

If `base_virtualhost` is configured, each agent dashboard is available at `https://<base_virtualhost>/hermes-agent-N/`.

## Runtime unit

The shipped user unit is `imageroot/systemd/user/hermes-agent@.service`.

Each started agent runs:

- one `systemctl --user` service instance: `hermes-agent@<id>.service`
- one Hermes container: `hermes-agent-<id>`
- one bind-mounted Hermes home directory at `/opt/data`
- one published dashboard port from the module-owned 30-port pool, forwarded to the container's Hermes dashboard on port `9119`

Restart supervision is owned by the systemd user unit with `Restart=on-failure`; the Podman container launches do not set container-level restart policies.
The Hermes container reads `agent_<id>.env` and `agent_<id>_secrets.env`.
If `base_virtualhost` is set, Traefik forwards `https://<base_virtualhost>/hermes-agent-N/` to that container's Hermes web dashboard.

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
- one started agent produces one service, one container, one route, and one isolated file set
- stopping an agent disables the runtime without deleting its files
- removing an agent cleans the runtime files
- removing the module cleans the instance state

## Uninstall

Remove the instance with:

```bash
remove-module --no-preserve hermes-agent1
```
