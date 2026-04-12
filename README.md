<img width="1397" height="761" alt="image" src="https://github.com/user-attachments/assets/631c598a-9553-4a21-8ff5-f002568f0bbe" />

# ns8-hermes-agent

`ns8-hermes-agent` is an NS8 module that manages one or more Hermes Agent runtimes.

## Quickstart

Install the module with

```bash
add-module ghcr.io/Stell0/ns8-hermes-agent:latest 1
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
runagent -m hermes-agent1 podman exec -it hermes-agent-1 hermes gateway stop
```

## Accessing the agent console
You can access the Hermes console for an agent with:

```bash
runagent -m hermes-agent1 podman exec -it hermes-agent-1 hermes
```

## Repository guidelines

The current implementation is intentionally small:

- Hermes only.
- One configured agent maps directly to one metadata file, one generated public env file, one generated secrets file, one Hermes home directory, one systemd user service, and one rootless Podman container.
- A fresh install is idle until at least one agent is configured with `status: start`.
- `SOUL.md` and the default Hermes home `.env` are seeded from checked-in templates with `sed` placeholder replacement.

## Current behavior

- `create-module` seeds minimal module state in `environment`, `secrets.env`, and `agents/`, records `TIMEZONE`, and discovers smarthost settings.
- `configure-module` validates the submitted agent list, stores one metadata file per agent, generates per-agent runtime files, and enables or disables the corresponding `hermes-agent@<id>.service` instances.
- `get-configuration` returns the configured agents, keeps the persisted desired `status`, and reports actual runtime state separately as `runtime_status`.
- `destroy-module` stops agent services, removes agent containers, and deletes generated per-agent files and directories.
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

Operator-visible runtime names are `hermes-agent-<id>` for containers. The shipped systemd unit is the internal template `hermes-agent@.service`.

## Repository layout

- `imageroot/`: NS8 actions, helper scripts, templates, event handler, state helper module, and the user systemd unit.
- `containers/`: the Hermes wrapper image only.
- `ui/`: embedded Vue 2 admin UI.
- `tests/`: Robot Framework integration checks and focused Python unit tests.

See `STRUCTURE.md` for a file map.

## Build

Build the module image and Hermes wrapper image with:

```bash
bash build-images.sh
```

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

The `configure-module` payload is now only an `agents` array.

Each agent contains:

- `id`: integer starting from `1`
- `name`: letters and spaces only
- `role`: one of `default`, `developer`, `marketing`, `sales`, `customer_support`, `social_media_manager`, `business_consultant`, or `researcher`
- `status`: `start` or `stop`

Example:

```bash
api-cli run module/hermes-agent1/configure-module --data '{"agents":[{"id":1,"name":"Foo Bar","role":"developer","status":"start"}]}'
```

That configuration will:

- store `agents/1/metadata.json`
- generate `agent_1.env` and `agent_1_secrets.env`
- seed `agents/1/home/SOUL.md` and `agents/1/home/.env` if they do not already exist
- enable and start `hermes-agent@1.service`
- run one rootless Podman container named `hermes-agent-1`

Read the current configuration with:

```bash
api-cli run module/hermes-agent1/get-configuration --data '{}'
```

Example output:

```json
{"agents": [{"id": 1, "name": "Foo Bar", "role": "developer", "status": "start", "runtime_status": "start"}]}
```

`status` is the persisted desired state. `runtime_status` is derived from the actual systemd service state.

## Runtime unit

The shipped user unit is `imageroot/systemd/user/hermes-agent@.service`.

Each started agent runs:

- one `systemctl --user` service instance: `hermes-agent@<id>.service`
- one container: `hermes-agent-<id>`
- one bind-mounted Hermes home directory at `/opt/data`

There is no shared target, shared backend service, or shared sidecar container.

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
- one started agent produces one service, one container, and one isolated file set
- stopping an agent disables the runtime without deleting its files
- removing an agent cleans the runtime files
- removing the module cleans the instance state

## Uninstall

Remove the instance with:

```bash
remove-module --no-preserve hermes-agent1
```
