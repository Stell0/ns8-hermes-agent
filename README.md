<p align="center">
  <img alt="image" src="https://github.com/Stell0/ns8-hermes-agent/blob/main/logo.png" />
</p>

# ns8-hermes-agent

`ns8-hermes-agent` is an NS8 module that manages one or more [Hermes Agent](https://hermes-agent.nousresearch.com/) runtimes.

<img width="1397" height="761" alt="image" src="https://github.com/user-attachments/assets/631c598a-9553-4a21-8ff5-f002568f0bbe" />

## Quickstart

Install the module with

```bash
add-module ghcr.io/stell0/hermes-agent:latest 1
```

From the UI, configure:

* a virtualhost for the agent dashboard like `hermes.example.com`
* select a user domain from the dropdown, which binds the module to that domain and populates the `allowed_user` selectors for each agent
* one or more agents with unique `allowed_user` values from the selected user domain

Configuration will create the agents and publish the dashboard at `https://hermes.example.com/` with per-agent authentication and routing.

From dashboard, you can setup a Telegram and everything else, but Dashboard is still early and setting it up from command line is a lot easier.

**Notes**:

* the module does not support multiple agents with the same `allowed_user` value.
* the Dashboard Web UI is build every time the container starts, so it takes a bit of time to be available after the agent service is started.
* after changing the configuration from dashboard, the agent service needs to be restarted to apply the new configuration. At the moment it can be done with the /restart command, but the first time you configure a messaging platform you need to restart the service from terminal with `systemctl --user restart hermes@<id>.service` or saving changes from NS8 ui
* At the moment, saving changes from NS8 UI restart all the agents, but in the future we will implement a smarter logic to restart only the agent that needs it.


## Command line

Not mandatory for normal operation, but first configuration is a lot easier from the command line.

Configure LLM provider and messaging platform for agent #1:
```bash
runagent -m hermes-agent1 podman exec -it hermes-1 hermes setup
```

**Tip**: *If you have OpenAI ChatGPT Plus subscription, you can select OpenAI Codex, than authenticate with OAuth, and the agent will be able to use GPT-5.4 with a shared token that doesn't require per-agent OpenAI API keys.*


Accessing the agent #1 console:
```bash
runagent -m hermes-agent1 podman exec -it hermes-1 hermes
```

See [Hermes Agent documentation](https://hermes-agent.nousresearch.com/docs) for more details on the available commands and configuration options.

### Other useful commands:

Restart agent #1 from command line
```bash
runagent -m hermes-agent1 systemctl --user restart hermes@1
```

Accessing the agent #3 console:
```bash
runagent -m hermes-agent1 podman exec -it hermes-3 hermes
```

Configure Telegram or other messaging platform for agent #2:
```bash
runagent -m hermes-agent1 podman exec -it hermes-2 hermes gateway setup
```

## Repository guidelines

The current implementation is intentionally small:

- One dedicated Podman pod per configured agent.
- One configured agent maps directly to one metadata file, one generated Hermes env file, one generated Hermes secrets env file, one Podman-managed Hermes home volume, one primary `hermes@<id>.service`, one per-agent pod owner unit, one rootless Podman pod, and one rootless Hermes container that runs the dashboard and gateway together.
- A fresh install is idle until at least one agent is configured with `status: start`.
- `SOUL.md` and the default Hermes home `.env` are seeded exactly once per agent volume during `configure-module` by a one-shot Hermes container that mounts the checked-in templates plus the generated public agent env file.
- The module supports at most 30 agents and reserves one TCP port for the shared auth listener.
- The module is now an NS8 account consumer and can bind one shared `user_domain` plus one per-agent `allowed_user` for published dashboard authentication.

## Current behavior

- `create-module` seeds minimal module state in `environment`, `secrets.env`, and `agents/`, records `TIMEZONE`, and discovers smarthost settings.
- `configure-module` validates the submitted agent list plus the shared dashboard virtualhost, optional shared `user_domain`, and optional `lets_encrypt` switch, binds the selected NS8 user domain when set, stores one metadata file per agent, generates per-agent runtime files plus shared auth runtime files, seeds first-time agent home content, reconciles the shared Traefik route, and enables or disables the corresponding `hermes@<id>.service` instances plus the shared `hermes-auth.service` when publishing is active.
- `get-configuration` returns the shared `base_virtualhost`, the shared `user_domain`, the shared `lets_encrypt` setting, and the configured agents with their persisted desired `status` plus `allowed_user`.
- `get-agent-runtime` returns live per-agent `runtime_status` derived from the current systemd service state.
- `destroy-module` stops agent services, removes agent pods and containers, stops the shared auth service, deletes the managed Traefik route, and deletes generated per-agent files plus per-agent Hermes home volumes.
- `discover-smarthost` merges shared SMTP settings into `environment` and `secrets.env`.

## Generated state

Module-wide files:

- `environment`
- `secrets.env`
- `authproxy.env`
- `authproxy_secrets.env`
- `authproxy_agents.json`
- `dashboard-sockets/`

Per-agent files:

- `agents/<id>/metadata.json`
- `agent_<id>.env`
- `agent_<id>_secrets.env`

Per-agent Podman volume:

- `hermes-agent-<id>-home`, mounted at `/opt/data`
- bootstrap-managed content inside the volume includes the seeded `SOUL.md`, `.env`, and `config.yaml`, plus the runtime directory skeleton used by Hermes

Operator-visible runtime names are `hermes-pod-<id>` for the pod, `hermes-<id>` for the per-agent Hermes container, `hermes-socket-<id>` for the per-agent socket relay container, `hermes-auth` for the shared auth proxy container, `hermes@.service` for the per-agent primary systemd unit, `hermes-socket@.service` for the per-agent socket sidecar unit, and `hermes-auth.service` for the shared auth unit. The active Traefik route instance is `<module_id>-hermes-auth`, and the Hermes home volume name is `hermes-agent-<id>-home`.

## Repository layout

- `imageroot/`: NS8 actions, helper scripts, templates, event handler, state helper module, and the user systemd units.
- `containers/`: the Hermes wrapper image sources, the dashboard auth proxy image, and the dashboard socket relay image.
- `ui/`: embedded Vue 2 admin UI.
- `tests/`: Robot Framework integration checks and focused Python unit tests.

See `STRUCTURE.md` for a file map.

## Build

Build the module image, auth proxy image, Hermes wrapper image, and socket relay image with:

```bash
bash build-images.sh
```

The Hermes wrapper image is built from `docker.io/nousresearch/hermes-agent:v2026.4.23`. The wrapper no longer patches or rebuilds dashboard web sources at startup; it bootstraps the Hermes home and points `HERMES_WEB_DIST` at the bundled upstream `web_dist` when present.

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

`base_virtualhost` is optional. When set, Traefik publishes one shared auth entrypoint on `https://<base_virtualhost>/`, and the shared auth service routes each authenticated session to its assigned running agent dashboard.
Submit an empty value to remove all managed dashboard routes.

`user_domain` is optional while dashboard publishing is disabled. When `base_virtualhost` is set and at least one agent exists, `user_domain` becomes required and must match an NS8 user domain visible through `agent.ldapproxy`.

`lets_encrypt` is optional. When `true`, Traefik requests a Let's Encrypt certificate for the shared dashboard host. The flag applies to the shared host, not to individual agents.
Changing the shared host, clearing it, or turning `lets_encrypt` off makes the module update or remove the managed routes and request any needed certificate cleanup on the Traefik side.

Each agent contains:

- `id`: integer starting from `1` and capped at `30`
- `name`: letters and spaces only
- `role`: one of `default`, `developer`, `marketing`, `sales`, `customer_support`, `social_media_manager`, `business_consultant`, or `researcher`
- `status`: `start` or `stop`
- `allowed_user`: bare username from the selected NS8 `user_domain`; required when `base_virtualhost` is set and at least one agent is published, and must be unique across the published agent set

Example:

```bash
api-cli run module/hermes-agent1/configure-module --data '{"base_virtualhost":"agents.example.org","user_domain":"example.org","lets_encrypt":true,"agents":[{"id":1,"name":"Foo Bar","role":"developer","status":"start","allowed_user":"alice"}]}'
```

That configuration will:

- store `agents/1/metadata.json`
- generate `agent_1.env` and `agent_1_secrets.env`
- bind the module to the selected NS8 user domain and validate `allowed_user` against that domain
- run a one-shot `podman run --entrypoint /bin/sh` seed step that mounts `hermes-agent-1-home:/opt/data`, mounts the checked-in templates at `/templates`, and creates `/opt/data/SOUL.md` plus `/opt/data/.env` only when they do not already exist
- create or update the shared Traefik route for `https://agents.example.org/`
- enable and start `hermes@1.service`
- enable and start `hermes-socket@1.service`
- create one rootless Podman pod, `hermes-pod-1`, containing the Hermes container `hermes-1`, which binds the dashboard to `127.0.0.1:9120` and runs the gateway together, plus the relay container `hermes-socket-1`, which exposes `/sockets/agent-1.sock`
- enable and start the shared auth proxy service `hermes-auth.service` when publishing is active

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

If `base_virtualhost` is configured, `https://<base_virtualhost>/` is the primary shared entrypoint.
The shared auth service authenticates against the shared `user_domain`, maps the authenticated username to exactly one assigned running agent, and proxies the rest of that session's requests to the selected dashboard.
`https://<base_virtualhost>/hermes-N/` remains an auth-owned login or session-status page for agent `N`; it is no longer a Traefik path route to the dashboard itself.
The auth proxy logs `auth_attempt`, `auth_success`, `auth_failed`, and `proxy_failed` events to standard output for troubleshooting published dashboard access. When `DEBUG=1` or `AUTH_PROXY_DEBUG=1`, it also logs `request_received` for inbound requests and `proxy_forward` with the resolved upstream URL before forwarding. If the assigned dashboard upstream is temporarily unavailable, the proxy returns HTTP 502 instead of terminating the app.

## Runtime unit

The shipped user units are `imageroot/systemd/user/hermes@.service`, `imageroot/systemd/user/hermes-socket@.service`, `imageroot/systemd/user/hermes-auth.service`, and `imageroot/systemd/user/hermes-pod@.service`.

Each started agent runs:

- one primary `systemctl --user` service instance: `hermes@<id>.service`
- one per-agent socket relay service instance: `hermes-socket@<id>.service`
- one Podman pod: `hermes-pod-<id>`
- one Hermes container: `hermes-<id>`
- one socket relay container: `hermes-socket-<id>`
- one Podman-managed Hermes home volume mounted at `/opt/data`
- one per-agent dashboard socket at `%S/state/dashboard-sockets/agent-<id>.sock`, mounted into `hermes-auth` as `/sockets/agent-<id>.sock`

Shared publishing also runs:

- one shared Traefik route instance: `<module_id>-hermes-auth`
- one shared auth listener on `127.0.0.1:${TCP_PORT}` forwarded to auth proxy port `9119`
- one shared auth proxy service instance: `hermes-auth.service`
- one shared Hermes dashboard auth container: `hermes-auth`

Restart supervision is owned by the systemd user units with `Restart=on-failure`; the Podman pod and container launches do not set container-level restart policies.
The shipped services create one named volume per agent mounted at `/opt/data`.
Managed `SOUL.md` and home `.env` seeding runs before service start in `configure-module/75seed-agent-home`; later agent edits preserve existing files inside the volume.
The Hermes container reads `agent_<id>.env` and `agent_<id>_secrets.env`, mounts the shared home volume, and runs `hermes dashboard --host 127.0.0.1 --port 9120 --insecure --no-open -- gateway run` inside the pod. The per-agent socket sidecar relays that listener onto `%S/state/dashboard-sockets/agent-<id>.sock`. The shared auth proxy container reads `authproxy.env`, `authproxy_secrets.env`, and `authproxy_agents.json`, mounts `%S/state/dashboard-sockets:/sockets:z`, authenticates the shared route against LDAP, preserves the dashboard upstream `Authorization` header, injects a trusted `X-Hermes-Authenticated-User` header derived from the authenticated session username while ignoring any client-supplied value for that header, logs auth events to stdout, and proxies requests to the assigned per-agent `upstream_socket`.
If `base_virtualhost` is set, Traefik forwards `https://<base_virtualhost>/` directly to the shared auth proxy listener. No per-agent path route, `strip_prefix`, or `X-Forwarded-Prefix` header is required.

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
- one started agent produces one pod, three services, two containers, one auth-proxied route with the configured shared TLS mode, one isolated volume, and one isolated generated file set
- stopping an agent disables the runtime without deleting its generated files or volume
- removing an agent cleans the runtime files and volume
- removing the module cleans the instance state

## Uninstall

Remove the instance with:

```bash
remove-module --no-preserve hermes-agent1
```
