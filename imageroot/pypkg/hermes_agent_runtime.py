import json
import os
import re
import secrets
import socket
import subprocess
import time
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import agent


ENVIRONMENT_FILE = "environment"
SHARED_SECRETS_ENVFILE = "secrets.env"
SYSTEMD_ENVFILE = "systemd.env"
LEGACY_AGENTS_ENVFILE = "agents.env"
LEGACY_SMARTHOST_ENVFILE = "smarthost.env"
SHARED_OPENVIKING_CONFIGFILE = "openviking.conf"
ALLOWED_ROLES = {"default", "developer"}
ALLOWED_STATUSES = {"start", "stop"}
NAME_PATTERN = re.compile(r"^[A-Za-z ]+$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
AGENT_ENVFILE_PATTERN = re.compile(r"^agent-(\d+)\.env$")
AGENT_SECRETS_ENVFILE_PATTERN = re.compile(r"^agent-(\d+)_secrets\.env$")
AGENT_OPENVIKING_CONFIG_PATTERN = re.compile(r"^agent-(\d+)_openviking\.conf$")
SYSTEMD_TARGET_PATTERN = re.compile(r"^hermes-agent@(\d+)\.target$")
OPENVIKING_CONFIG_PATH = "/app/ov.conf"
OPENVIKING_WORKSPACE_PATH = "/app/data"
OPENVIKING_PORT_ENV = "OPENVIKING_PORT"
OPENVIKING_ROOT_API_KEY_ENV = "OPENVIKING_ROOT_API_KEY"
OPENVIKING_TENANT_MODE_ENV = "OPENVIKING_TENANT_MODE"
OPENVIKING_AGENT_ID_ENV = "OPENVIKING_AGENT_ID"
OPENVIKING_TENANT_MODE = "shared"
OPENVIKING_LOCAL_HOST = "127.0.0.1"
OPENVIKING_CONTAINER_HOST = "host.containers.internal"
OPENVIKING_LISTEN_HOST = "0.0.0.0"
OPENVIKING_CONTAINER_PORT = 1933
OPENVIKING_HEALTH_TIMEOUT = 60
SMTP_PUBLIC_KEYS = (
    "SMTP_ENABLED",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_ENCRYPTION",
    "SMTP_TLSVERIFY",
)
SMTP_SECRET_KEYS = ("SMTP_PASSWORD",)
AGENT_SECRET_KEYS = ("OPENVIKING_API_KEY",)
SYSTEMD_ENV_KEYS = {OPENVIKING_PORT_ENV}


def default_openviking_account(agent_id):
    return f"agent-{agent_id}"


def default_openviking_user(agent_id):
    return f"agent-{agent_id}"


def default_openviking_agent_id(agent_id):
    return f"agent-{agent_id}"


def normalize_identifier(value, default_value, label):
    if value is None:
        return default_value

    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")

    normalized_value = value.strip()
    if not normalized_value or not IDENTIFIER_PATTERN.fullmatch(normalized_value):
        raise ValueError(f"{label} must match {IDENTIFIER_PATTERN.pattern}")

    return normalized_value


def validate_agents(raw_agents):
    if raw_agents is None:
        return []

    if not isinstance(raw_agents, list):
        raise ValueError("agents must be a list")

    normalized_agents = []
    seen_ids = set()
    seen_accounts = set()

    for index, raw_agent in enumerate(raw_agents):
        if not isinstance(raw_agent, dict):
            raise ValueError(f"agent at index {index} must be an object")

        agent_id = raw_agent.get("id")
        if not isinstance(agent_id, int) or agent_id < 1:
            raise ValueError(f"agent at index {index} has an invalid id")
        if agent_id in seen_ids:
            raise ValueError(f"agent id {agent_id} is duplicated")

        name = raw_agent.get("name")
        if not isinstance(name, str):
            raise ValueError(f"agent at index {index} has an invalid name")
        name = name.strip()
        if not name or not NAME_PATTERN.fullmatch(name):
            raise ValueError(f"agent at index {index} has an invalid name")

        role = raw_agent.get("role")
        if role not in ALLOWED_ROLES:
            raise ValueError(f"agent at index {index} has an invalid role")

        status = raw_agent.get("status")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"agent at index {index} has an invalid status")

        account = normalize_identifier(
            raw_agent.get("account"),
            default_openviking_account(agent_id),
            f"agent at index {index} has an invalid account",
        )
        if account in seen_accounts:
            raise ValueError(f"agent account {account} is duplicated")

        user = normalize_identifier(
            raw_agent.get("user"),
            default_openviking_user(agent_id),
            f"agent at index {index} has an invalid user",
        )
        openviking_agent_id = normalize_identifier(
            raw_agent.get("agent_id"),
            default_openviking_agent_id(agent_id),
            f"agent at index {index} has an invalid agent_id",
        )

        normalized_agents.append(
            {
                "id": agent_id,
                "name": name,
                "role": role,
                "status": status,
                "account": account,
                "user": user,
                "agent_id": openviking_agent_id,
            }
        )
        seen_ids.add(agent_id)
        seen_accounts.add(account)

    return sorted(normalized_agents, key=lambda item: item["id"])


def serialize_agents(agents):
    return ",".join(
        ":".join(
            [
                str(agent_data["id"]),
                agent_data["name"],
                agent_data["role"],
                agent_data["status"],
                agent_data["account"],
                agent_data["user"],
                agent_data["agent_id"],
            ]
        )
        for agent_data in sorted(agents, key=lambda item: item["id"])
    )


def parse_agents_list(raw_agents_list):
    if not raw_agents_list:
        return []

    agents = []
    seen_ids = set()
    seen_accounts = set()
    for raw_agent in raw_agents_list.split(","):
        serialized_agent = raw_agent.strip()
        if not serialized_agent:
            continue

        parts = serialized_agent.split(":", 6)
        if len(parts) in {3, 4}:
            return []
        if len(parts) != 7:
            raise ValueError(f"invalid AGENTS_LIST entry: {serialized_agent}")

        agent_id, name, role, status, account, user, openviking_agent_id = parts

        normalized_name = name.strip()

        if not agent_id.isdigit() or int(agent_id) < 1:
            raise ValueError(f"invalid AGENTS_LIST id: {agent_id}")

        normalized_id = int(agent_id)
        if normalized_id in seen_ids:
            raise ValueError(f"duplicated AGENTS_LIST id: {agent_id}")
        if not normalized_name or not NAME_PATTERN.fullmatch(normalized_name):
            raise ValueError(f"invalid AGENTS_LIST name: {name}")
        if role not in ALLOWED_ROLES:
            raise ValueError(f"invalid AGENTS_LIST role: {role}")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"invalid AGENTS_LIST status: {status}")
        if not IDENTIFIER_PATTERN.fullmatch(account):
            raise ValueError(f"invalid AGENTS_LIST account: {account}")
        if account in seen_accounts:
            raise ValueError(f"duplicated AGENTS_LIST account: {account}")
        if not IDENTIFIER_PATTERN.fullmatch(user):
            raise ValueError(f"invalid AGENTS_LIST user: {user}")
        if not IDENTIFIER_PATTERN.fullmatch(openviking_agent_id):
            raise ValueError(f"invalid AGENTS_LIST agent_id: {openviking_agent_id}")

        agents.append(
            {
                "id": normalized_id,
                "name": normalized_name,
                "role": role,
                "status": status,
                "account": account,
                "user": user,
                "agent_id": openviking_agent_id,
            }
        )
        seen_ids.add(normalized_id)
        seen_accounts.add(account)

    return sorted(agents, key=lambda item: item["id"])


def read_optional_envfile(path):
    if not os.path.exists(path):
        return {}

    return agent.read_envfile(path)


def read_agents_list():
    agents_list = read_optional_envfile(ENVIRONMENT_FILE).get("AGENTS_LIST")
    if agents_list is not None:
        return agents_list

    legacy_agents_list = read_optional_envfile(LEGACY_AGENTS_ENVFILE).get("AGENTS_LIST")
    if legacy_agents_list is not None:
        return legacy_agents_list

    return ""


def read_agents_from_state():
    return parse_agents_list(read_agents_list())


def persist_agents(agents):
    agent.set_env("AGENTS_LIST", serialize_agents(agents))
    if os.path.exists(LEGACY_AGENTS_ENVFILE):
        os.remove(LEGACY_AGENTS_ENVFILE)


def agent_envfile(agent_id):
    return f"agent-{agent_id}.env"


def agent_secrets_envfile(agent_id):
    return f"agent-{agent_id}_secrets.env"


def agent_openviking_configfile(agent_id):
    return f"agent-{agent_id}_openviking.conf"


def shared_openviking_configfile():
    return SHARED_OPENVIKING_CONFIGFILE


def pod_name(agent_id):
    return f"hermes-agent-{agent_id}"


def hermes_data_volume(agent_id):
    return f"hermes-agent-hermes-data-{agent_id}"


def legacy_openviking_data_volume(agent_id):
    return f"hermes-agent-openviking-data-{agent_id}"


def shared_openviking_data_volume():
    return "hermes-agent-openviking-data"


def target_unit(agent_id):
    return f"hermes-agent@{agent_id}.target"


def pod_service_unit(agent_id):
    return f"hermes-agent-pod@{agent_id}.service"


def container_service_units(agent_id):
    return [
        f"hermes-agent-hermes@{agent_id}.service",
        f"hermes-agent-gateway@{agent_id}.service",
    ]


def managed_service_units(agent_id):
    return [
        shared_openviking_service_unit(),
        pod_service_unit(agent_id),
        *container_service_units(agent_id),
    ]


def shared_openviking_service_unit():
    return "hermes-agent-openviking.service"


def shared_openviking_container_name():
    return "hermes-agent-openviking"


def run_command(command, check=True, capture_output=False):
    return subprocess.run(
        command,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )


def systemctl_user(*args, check=True, capture_output=False):
    return run_command(
        ["systemctl", "--user", *args],
        check=check,
        capture_output=capture_output,
    )


def unit_is_active(unit_name):
    return systemctl_user("is-active", "--quiet", unit_name, check=False).returncode == 0


def list_systemd_agent_ids():
    ids = set()
    commands = [
        ["list-unit-files", "--type=target", "--all", "hermes-agent@*.target", "--no-legend", "--plain"],
        ["list-units", "--type=target", "--all", "hermes-agent@*.target", "--no-legend", "--plain"],
    ]

    for command in commands:
        result = systemctl_user(*command, check=False, capture_output=True)
        if not result.stdout:
            continue

        for line in result.stdout.splitlines():
            match = SYSTEMD_TARGET_PATTERN.match(line.strip().split()[0])
            if match:
                ids.add(int(match.group(1)))

    return ids


def scan_generated_agent_ids(base_path="."):
    ids = set()
    for path in Path(base_path).glob("agent-*.env"):
        match = AGENT_ENVFILE_PATTERN.fullmatch(path.name)
        if match:
            ids.add(int(match.group(1)))
            continue

        match = AGENT_SECRETS_ENVFILE_PATTERN.fullmatch(path.name)
        if match:
            ids.add(int(match.group(1)))

        match = AGENT_OPENVIKING_CONFIG_PATTERN.fullmatch(path.name)
        if match:
            ids.add(int(match.group(1)))

    for path in Path(base_path).glob("agent-*_secrets.env"):
        match = AGENT_SECRETS_ENVFILE_PATTERN.fullmatch(path.name)
        if match:
            ids.add(int(match.group(1)))

    for path in Path(base_path).glob("agent-*_openviking.conf"):
        match = AGENT_OPENVIKING_CONFIG_PATTERN.fullmatch(path.name)
        if match:
            ids.add(int(match.group(1)))

    return ids


def list_known_agent_ids(base_path="."):
    return sorted(scan_generated_agent_ids(base_path) | list_systemd_agent_ids())


def write_envfile(path, env_data):
    if env_data:
        agent.write_envfile(path, env_data)
        return

    Path(path).write_text("", encoding="utf-8")


def write_jsonfile(path, data):
    Path(path).write_text(f"{json.dumps(data, indent=2)}\n", encoding="utf-8")


def valid_port_value(value):
    return isinstance(value, str) and value.isdigit() and 1 <= int(value) <= 65535


def reserve_tcp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((OPENVIKING_LOCAL_HOST, 0))
        return server_socket.getsockname()[1]


def ensure_shared_openviking_settings(shared_environment, shared_secrets):
    port_value = shared_environment.get(OPENVIKING_PORT_ENV)
    if not valid_port_value(port_value):
        port_value = str(reserve_tcp_port())
        agent.set_env(OPENVIKING_PORT_ENV, port_value)
        shared_environment[OPENVIKING_PORT_ENV] = port_value

    root_api_key = shared_secrets.get(OPENVIKING_ROOT_API_KEY_ENV)
    if not root_api_key:
        root_api_key = generate_agent_secret(OPENVIKING_ROOT_API_KEY_ENV)
        shared_secrets = {**shared_secrets, OPENVIKING_ROOT_API_KEY_ENV: root_api_key}
        write_envfile(SHARED_SECRETS_ENVFILE, shared_secrets)

    return int(port_value), root_api_key


def openviking_port(shared_environment):
    port_value = shared_environment.get(OPENVIKING_PORT_ENV)
    if not valid_port_value(port_value):
        raise ValueError(f"invalid {OPENVIKING_PORT_ENV}: {port_value}")

    return int(port_value)


def openviking_host_endpoint(shared_environment):
    return f"http://{OPENVIKING_LOCAL_HOST}:{openviking_port(shared_environment)}"


def openviking_container_endpoint(shared_environment):
    return f"http://{OPENVIKING_CONTAINER_HOST}:{openviking_port(shared_environment)}"


def build_agent_public_env(agent_data, shared_environment):
    env_data = {
        "AGENT_ID": agent_data["agent_id"],
        "AGENT_INSTANCE_ID": str(agent_data["id"]),
        "AGENT_NAME": agent_data["name"],
        "AGENT_ROLE": agent_data["role"],
        "AGENT_STATUS": agent_data["status"],
        OPENVIKING_AGENT_ID_ENV: agent_data["agent_id"],
        OPENVIKING_TENANT_MODE_ENV: OPENVIKING_TENANT_MODE,
        "OPENVIKING_ENDPOINT": openviking_container_endpoint(shared_environment),
        "OPENVIKING_ACCOUNT": agent_data["account"],
        "OPENVIKING_USER": agent_data["user"],
    }

    module_id = os.environ.get("MODULE_ID")
    if module_id:
        env_data["MODULE_ID"] = module_id

    for key in SMTP_PUBLIC_KEYS:
        value = shared_environment.get(key)
        if value is not None:
            env_data[key] = value

    return env_data


def openviking_user(agent_data):
    return agent_data["user"]


def can_preserve_agent_api_key(existing_agent_env, agent_data):
    existing_agent_id = existing_agent_env.get(OPENVIKING_AGENT_ID_ENV) or existing_agent_env.get("AGENT_ID")
    return (
        existing_agent_env.get(OPENVIKING_TENANT_MODE_ENV) == OPENVIKING_TENANT_MODE
        and existing_agent_env.get("OPENVIKING_ACCOUNT") == agent_data["account"]
        and existing_agent_env.get("OPENVIKING_USER") == agent_data["user"]
        and existing_agent_id == agent_data["agent_id"]
    )


def generate_agent_secret(_key):
    return secrets.token_hex(32)


def build_agent_secrets_env(
    shared_secrets,
    existing_agent_secrets=None,
    preserve_openviking_api_key=False,
):
    existing_agent_secrets = existing_agent_secrets or {}
    env_data = {}
    if preserve_openviking_api_key and existing_agent_secrets.get("OPENVIKING_API_KEY"):
        env_data["OPENVIKING_API_KEY"] = existing_agent_secrets["OPENVIKING_API_KEY"]

    env_data.update(
        {
            key: value
            for key in SMTP_SECRET_KEYS
            if (value := shared_secrets.get(key)) is not None
        }
    )
    return env_data


def build_systemd_environment(shared_environment):
    return {
        key: value
        for key, value in shared_environment.items()
        if key.endswith("_IMAGE") or key in SYSTEMD_ENV_KEYS
    }


def build_openviking_config(shared_secrets):
    return {
        "server": {
            "host": OPENVIKING_LISTEN_HOST,
            "port": OPENVIKING_CONTAINER_PORT,
            "auth_mode": "api_key",
            "root_api_key": shared_secrets[OPENVIKING_ROOT_API_KEY_ENV],
        },
        "storage": {
            "workspace": OPENVIKING_WORKSPACE_PATH,
            "agfs": {
                "backend": "local",
            },
            "vectordb": {
                "backend": "local",
            },
        },
        "log": {
            "level": "INFO",
            "output": "stdout",
        },
    }


def parse_json_bytes(payload):
    if not payload:
        return {}

    decoded_payload = payload.decode("utf-8")
    if not decoded_payload:
        return {}

    try:
        return json.loads(decoded_payload)
    except json.JSONDecodeError:
        return {"raw": decoded_payload}


def openviking_request(method, path, port, api_key=None, data=None, query=None):
    url = f"http://{OPENVIKING_LOCAL_HOST}:{port}{path}"
    if query:
        url = f"{url}?{urllib_parse.urlencode(query)}"

    headers = {}
    payload = None
    if api_key:
        headers["X-API-Key"] = api_key
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib_request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            return response.status, parse_json_bytes(response.read())
    except urllib_error.HTTPError as error:
        return error.code, parse_json_bytes(error.read())
    except urllib_error.URLError as error:
        raise RuntimeError(f"OpenViking request failed: {error.reason}") from error


def response_is_success(status_code):
    return 200 <= status_code < 300


def wait_for_openviking(port, timeout=OPENVIKING_HEALTH_TIMEOUT):
    deadline = time.time() + timeout
    last_error = None

    while time.time() < deadline:
        try:
            status_code, _ = openviking_request("GET", "/health", port)
            if response_is_success(status_code):
                return
            last_error = f"health endpoint returned HTTP {status_code}"
        except RuntimeError as error:
            last_error = str(error)

        time.sleep(1)

    raise RuntimeError(f"OpenViking did not become ready: {last_error or 'timeout'}")


def extract_user_key(response_payload, context):
    user_key = response_payload.get("result", {}).get("user_key")
    if user_key:
        return user_key

    raise RuntimeError(f"OpenViking {context} response did not include a user_key")


def openviking_user_key_is_valid(port, user_key):
    status_code, _ = openviking_request(
        "GET",
        "/api/v1/fs/ls",
        port,
        api_key=user_key,
        query={"uri": "viking://"},
    )
    return response_is_success(status_code)


def provision_openviking_tenant(port, root_api_key, agent_data):
    account_id = agent_data["account"]
    user_id = agent_data["user"]
    account_path = "/api/v1/admin/accounts"

    status_code, response_payload = openviking_request(
        "POST",
        account_path,
        port,
        api_key=root_api_key,
        data={
            "account_id": account_id,
            "admin_user_id": user_id,
        },
    )
    if response_is_success(status_code):
        return extract_user_key(response_payload, "create-account")

    user_path = f"{account_path}/{urllib_parse.quote(account_id)}/users"
    status_code, response_payload = openviking_request(
        "POST",
        user_path,
        port,
        api_key=root_api_key,
        data={"user_id": user_id, "role": "admin"},
    )
    if response_is_success(status_code):
        return extract_user_key(response_payload, "register-user")

    openviking_request(
        "PUT",
        f"{user_path}/{urllib_parse.quote(user_id)}/role",
        port,
        api_key=root_api_key,
        data={"role": "admin"},
    )
    status_code, response_payload = openviking_request(
        "POST",
        f"{user_path}/{urllib_parse.quote(user_id)}/key",
        port,
        api_key=root_api_key,
    )
    if response_is_success(status_code):
        return extract_user_key(response_payload, "regenerate-key")

    raise RuntimeError(
        "Unable to provision OpenViking tenant "
        f"{account_id}/{user_id}: create-account, register-user, and regenerate-key failed"
    )


def ensure_agent_openviking_tenant(agent_id):
    agent_data = next(
        (item for item in read_agents_from_state() if item["id"] == agent_id),
        None,
    )
    if agent_data is None:
        raise ValueError(f"agent {agent_id} not found")

    shared_environment = read_optional_envfile(ENVIRONMENT_FILE)
    shared_secrets = read_optional_envfile(SHARED_SECRETS_ENVFILE)
    port, root_api_key = ensure_shared_openviking_settings(shared_environment, shared_secrets)
    wait_for_openviking(port)

    shared_secrets = read_optional_envfile(SHARED_SECRETS_ENVFILE)
    agent_secrets = read_optional_envfile(agent_secrets_envfile(agent_id))
    existing_user_key = agent_secrets.get("OPENVIKING_API_KEY")
    if existing_user_key and openviking_user_key_is_valid(port, existing_user_key):
        write_envfile(
            agent_secrets_envfile(agent_id),
            build_agent_secrets_env(
                shared_secrets,
                existing_agent_secrets=agent_secrets,
                preserve_openviking_api_key=True,
            ),
        )
        return existing_user_key

    user_key = provision_openviking_tenant(port, root_api_key, agent_data)
    updated_agent_secrets = build_agent_secrets_env(shared_secrets)
    updated_agent_secrets["OPENVIKING_API_KEY"] = user_key
    write_envfile(agent_secrets_envfile(agent_id), updated_agent_secrets)
    return user_key


def remove_agent_openviking_account(agent_id):
    agent_environment = read_optional_envfile(agent_envfile(agent_id))
    if agent_environment.get(OPENVIKING_TENANT_MODE_ENV) != OPENVIKING_TENANT_MODE:
        return

    account_id = agent_environment.get("OPENVIKING_ACCOUNT")
    if not account_id or not unit_is_active(shared_openviking_service_unit()):
        return

    shared_environment = read_optional_envfile(ENVIRONMENT_FILE)
    shared_secrets = read_optional_envfile(SHARED_SECRETS_ENVFILE)
    root_api_key = shared_secrets.get(OPENVIKING_ROOT_API_KEY_ENV)
    port_value = shared_environment.get(OPENVIKING_PORT_ENV)
    if not root_api_key or not valid_port_value(port_value):
        return

    wait_for_openviking(int(port_value))
    status_code, _ = openviking_request(
        "DELETE",
        f"/api/v1/admin/accounts/{urllib_parse.quote(account_id)}",
        int(port_value),
        api_key=root_api_key,
    )
    if response_is_success(status_code) or status_code == 404:
        return

    raise RuntimeError(f"Unable to delete OpenViking account {account_id}: HTTP {status_code}")


def remove_agent_runtime_files(agent_id):
    for path in (
        agent_envfile(agent_id),
        agent_secrets_envfile(agent_id),
        agent_openviking_configfile(agent_id),
    ):
        if os.path.exists(path):
            os.remove(path)


def remove_agent_volumes(agent_id):
    for volume_name in (hermes_data_volume(agent_id), legacy_openviking_data_volume(agent_id)):
        run_command(["podman", "volume", "rm", "--force", volume_name], check=False)


def cleanup_shared_openviking_runtime():
    systemctl_user("stop", shared_openviking_service_unit(), check=False)
    run_command(
        ["podman", "volume", "rm", "--force", shared_openviking_data_volume()],
        check=False,
    )
    shared_configfile = shared_openviking_configfile()
    if os.path.exists(shared_configfile):
        os.remove(shared_configfile)


def sync_agent_runtime_files(agent_id=None):
    agents = read_agents_from_state()
    shared_environment = read_optional_envfile(ENVIRONMENT_FILE)
    shared_secrets = read_optional_envfile(SHARED_SECRETS_ENVFILE)

    ensure_shared_openviking_settings(shared_environment, shared_secrets)
    shared_environment = read_optional_envfile(ENVIRONMENT_FILE)
    shared_secrets = read_optional_envfile(SHARED_SECRETS_ENVFILE)

    write_envfile(SYSTEMD_ENVFILE, build_systemd_environment(shared_environment))
    write_jsonfile(shared_openviking_configfile(), build_openviking_config(shared_secrets))

    if agent_id is not None:
        filtered_agents = [item for item in agents if item["id"] == agent_id]
        if not filtered_agents:
            raise ValueError(f"agent {agent_id} not found")
        agents = filtered_agents

    current_ids = {item["id"] for item in read_agents_from_state()}

    for agent_data in agents:
        existing_agent_env = read_optional_envfile(agent_envfile(agent_data["id"]))
        existing_agent_secrets = read_optional_envfile(agent_secrets_envfile(agent_data["id"]))
        agent_secrets = build_agent_secrets_env(
            shared_secrets,
            existing_agent_secrets=existing_agent_secrets,
            preserve_openviking_api_key=can_preserve_agent_api_key(existing_agent_env, agent_data),
        )
        write_envfile(
            agent_envfile(agent_data["id"]),
            build_agent_public_env(agent_data, shared_environment),
        )
        write_envfile(
            agent_secrets_envfile(agent_data["id"]),
            agent_secrets,
        )
        legacy_configfile = agent_openviking_configfile(agent_data["id"])
        if os.path.exists(legacy_configfile):
            os.remove(legacy_configfile)

    if agent_id is None:
        for stale_id in scan_generated_agent_ids():
            if stale_id not in current_ids:
                remove_agent_runtime_files(stale_id)

    return agents


def stop_disable_agent(agent_id):
    systemctl_user("disable", "--now", target_unit(agent_id), check=False)
    run_command(["podman", "pod", "rm", "--force", pod_name(agent_id)], check=False)


def cleanup_agent_runtime(agent_id):
    stop_disable_agent(agent_id)
    remove_agent_openviking_account(agent_id)
    remove_agent_volumes(agent_id)
    remove_agent_runtime_files(agent_id)


def actual_agent_status(agent_id):
    services = managed_service_units(agent_id)
    if all(unit_is_active(unit_name) for unit_name in services):
        return "start"
    return "stop"