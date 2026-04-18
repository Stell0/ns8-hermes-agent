import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path


ENVIRONMENT_FILE = Path("environment")
SHARED_SECRETS_ENVFILE = Path("secrets.env")
AGENTS_DIR = Path("agents")
SOUL_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "SOUL"
HOME_ENV_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "home.env.in"
MAX_AGENTS = 30

ALLOWED_ROLES = (
    "default",
    "developer",
    "marketing",
    "sales",
    "customer_support",
    "social_media_manager",
    "business_consultant",
    "researcher",
)
ALLOWED_STATUSES = ("start", "stop")
NAME_PATTERN = re.compile(r"^[A-Za-z ]+$")
AGENT_DIR_PATTERN = re.compile(r"^\d+$")
AGENT_ENVFILE_PATTERN = re.compile(r"^agent_(\d+)\.env$")
AGENT_SECRETS_ENVFILE_PATTERN = re.compile(r"^agent_(\d+)_secrets\.env$")
AGENT_SECRET_KEY = "HERMES_AGENT_SECRET"
SMTP_PUBLIC_KEYS = (
    "SMTP_ENABLED",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_ENCRYPTION",
    "SMTP_TLSVERIFY",
)
SMTP_SECRET_KEY = "SMTP_PASSWORD"
TIMEZONE_ENV = "TIMEZONE"
TIMEZONE_DEFAULT = "UTC"
TCP_PORT_ENV = "TCP_PORT"
TCP_PORTS_ENV = "TCP_PORTS"
TCP_PORTS_RANGE_ENV = "TCP_PORTS_RANGE"
BASE_VIRTUALHOST_ENV = "BASE_VIRTUALHOST"
AGENT_DASHBOARD_HOST_PORT_ENV = "AGENT_DASHBOARD_HOST_PORT"
DASHBOARD_PORT = 9119
HOME_VOLUME_STATE_FILE = ".hermes-agent-seed-state.json"
BASE_VIRTUALHOST_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:(?!-)[A-Za-z0-9-]{1,63}(?<!-)\.)+(?!-)[A-Za-z0-9-]{1,63}(?<!-)$"
)


def soul_template_for_role(role):
    if role not in ALLOWED_ROLES:
        raise ValueError(f"invalid role: {role}")

    return SOUL_TEMPLATES_DIR / f"{role}.md.in"


def ensure_private_directory(path):
    directory_path = Path(path)

    if directory_path in {Path("."), Path("/")}:
        return directory_path

    current_path = Path(directory_path.anchor) if directory_path.is_absolute() else Path(".")
    path_parts = directory_path.parts[1:] if directory_path.is_absolute() else directory_path.parts

    for part in path_parts:
        current_path = current_path / part
        try:
            directory_stat = current_path.lstat()
        except FileNotFoundError:
            current_path.mkdir(mode=0o700)
            continue

        if stat.S_ISLNK(directory_stat.st_mode) or not stat.S_ISDIR(directory_stat.st_mode):
            raise ValueError(f"unsafe directory path: {current_path}")

    os.chmod(directory_path, 0o700)
    return directory_path


def write_private_textfile(path, content, mode=0o600):
    file_path = Path(path)
    parent_path = file_path.parent
    temp_path = None
    file_descriptor = None

    if parent_path != Path("."):
        ensure_private_directory(parent_path)

    try:
        file_stat = file_path.lstat()
    except FileNotFoundError:
        file_stat = None

    if file_stat is not None and (stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode)):
        raise ValueError(f"unsafe file path: {file_path}")

    try:
        file_descriptor, temp_path = tempfile.mkstemp(prefix=f".{file_path.name}.", dir=parent_path)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temp_file:
            file_descriptor = None
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.chmod(temp_path, mode)
        os.replace(temp_path, file_path)
    except Exception:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temp_path is not None and os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def read_envfile(path):
    env_data = {}
    file_path = Path(path)
    if not file_path.exists():
        return env_data

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in raw_line:
            continue

        key, value = raw_line.split("=", 1)
        env_data[key] = value

    return env_data


def write_envfile(path, env_data):
    file_path = Path(path)

    content = "\n".join(f"{key}={value}" for key, value in env_data.items())
    if content:
        content = f"{content}\n"

    write_private_textfile(file_path, content)


def read_jsonfile(path):
    file_path = Path(path)
    if not file_path.exists():
        return None

    return json.loads(file_path.read_text(encoding="utf-8"))


def write_jsonfile(path, data):
    file_path = Path(path)
    write_private_textfile(file_path, f"{json.dumps(data, indent=2)}\n")


def agent_dir(agent_id):
    return AGENTS_DIR / str(agent_id)


def agent_metadata_path(agent_id):
    return agent_dir(agent_id) / "metadata.json"


def agent_seed_state_path(agent_id):
    return agent_dir(agent_id) / HOME_VOLUME_STATE_FILE


def agent_envfile(agent_id):
    return Path(f"agent_{agent_id}.env")


def agent_secrets_envfile(agent_id):
    return Path(f"agent_{agent_id}_secrets.env")


def service_unit(agent_id):
    return f"hermes-agent@{agent_id}.service"


def container_name(agent_id):
    return f"hermes-agent-{agent_id}"


def volume_name(agent_id):
    return f"hermes-agent-{agent_id}-home"


def route_instance_name(agent_id, module_id=None, shared_environment=None):
    if shared_environment is None:
        shared_environment = read_envfile(ENVIRONMENT_FILE)

    module_value = module_id or shared_environment.get("MODULE_ID") or os.getenv("MODULE_ID")
    if not module_value:
        raise ValueError("MODULE_ID is required to derive route instance names")

    return f"{module_value}-hermes-agent-{agent_id}"


def route_path(agent_id):
    return f"/hermes-agent-{agent_id}"


def timezone_value(shared_environment=None):
    if shared_environment is None:
        shared_environment = read_envfile(ENVIRONMENT_FILE)

    value = (shared_environment.get(TIMEZONE_ENV) or TIMEZONE_DEFAULT).strip()
    return value or TIMEZONE_DEFAULT


def base_virtualhost_value(shared_environment=None):
    if shared_environment is None:
        shared_environment = read_envfile(ENVIRONMENT_FILE)

    return (shared_environment.get(BASE_VIRTUALHOST_ENV) or "").strip().lower()


def validate_base_virtualhost(value):
    normalized_value = (value or "").strip().lower()
    if not normalized_value:
        return ""

    if not BASE_VIRTUALHOST_PATTERN.fullmatch(normalized_value):
        raise ValueError("invalid base_virtualhost")

    return normalized_value


def parse_tcp_ports_range(port_range):
    normalized_range = (port_range or "").strip()
    if not normalized_range:
        raise ValueError(f"missing {TCP_PORTS_RANGE_ENV} in environment")

    start_text, separator, end_text = normalized_range.partition("-")
    if not separator:
        raise ValueError(f"invalid {TCP_PORTS_RANGE_ENV} value: {normalized_range}")

    return int(start_text), int(end_text)


def build_tcp_ports_environment(start_port, end_port, ports_demand):
    if end_port - start_port + 1 < ports_demand:
        raise ValueError(f"{TCP_PORTS_RANGE_ENV} must contain at least {ports_demand} ports")

    environment = {TCP_PORT_ENV: str(start_port)}
    if ports_demand > 1:
        environment[TCP_PORTS_RANGE_ENV] = f"{start_port}-{end_port}"
    if 1 < ports_demand <= 8:
        environment[TCP_PORTS_ENV] = ",".join(
            str(port) for port in range(start_port, end_port + 1)
        )

    return environment


def ensure_tcp_ports_environment(shared_environment=None, ports_demand=MAX_AGENTS, allocate_ports=None):
    if shared_environment is None:
        shared_environment = read_envfile(ENVIRONMENT_FILE)

    try:
        start_port, end_port = parse_tcp_ports_range(shared_environment.get(TCP_PORTS_RANGE_ENV))
    except ValueError:
        start_port = None
        end_port = None

    if start_port is not None and end_port is not None and end_port - start_port + 1 >= ports_demand:
        expected_environment = build_tcp_ports_environment(
            start_port=start_port,
            end_port=end_port,
            ports_demand=ports_demand,
        )
        env_patch = {}
        for env_key, env_value in expected_environment.items():
            if shared_environment.get(env_key) != env_value:
                env_patch[env_key] = env_value
        return env_patch

    if allocate_ports is None:
        raise ValueError("allocate_ports callback is required")

    allocated_range = allocate_ports(ports_demand, "tcp")
    if not isinstance(allocated_range, (list, tuple)) or len(allocated_range) != 2:
        raise ValueError("allocate_ports returned an invalid port range")

    return build_tcp_ports_environment(
        start_port=int(allocated_range[0]),
        end_port=int(allocated_range[1]),
        ports_demand=ports_demand,
    )


def agent_dashboard_host_port(agent_id, shared_environment=None):
    if not isinstance(agent_id, int) or agent_id < 1 or agent_id > MAX_AGENTS:
        raise ValueError(f"agent id must be between 1 and {MAX_AGENTS}")

    if shared_environment is None:
        shared_environment = read_envfile(ENVIRONMENT_FILE)

    start_port, end_port = parse_tcp_ports_range(shared_environment.get(TCP_PORTS_RANGE_ENV))
    if end_port - start_port + 1 < MAX_AGENTS:
        raise ValueError(f"{TCP_PORTS_RANGE_ENV} must contain at least {MAX_AGENTS} ports")

    return start_port + agent_id - 1


def validate_agents(raw_agents):
    if raw_agents is None:
        return []

    if not isinstance(raw_agents, list):
        raise ValueError("agents must be a list")

    normalized_agents = []
    seen_ids = set()
    allowed_fields = {"id", "name", "role", "status"}

    for index, raw_agent in enumerate(raw_agents):
        if not isinstance(raw_agent, dict):
            raise ValueError(f"agent at index {index} must be an object")

        extra_fields = sorted(set(raw_agent) - allowed_fields)
        if extra_fields:
            raise ValueError(
                f"agent at index {index} has unexpected fields: {', '.join(extra_fields)}"
            )

        agent_id = raw_agent.get("id")
        if not isinstance(agent_id, int) or agent_id < 1 or agent_id > MAX_AGENTS:
            raise ValueError(f"agent at index {index} has an invalid id")
        if agent_id in seen_ids:
            raise ValueError(f"agent id {agent_id} is duplicated")

        raw_name = raw_agent.get("name")
        if not isinstance(raw_name, str):
            raise ValueError(f"agent at index {index} has an invalid name")
        name = raw_name.strip()
        if not name or not NAME_PATTERN.fullmatch(name):
            raise ValueError(f"agent at index {index} has an invalid name")

        role = raw_agent.get("role")
        if role not in ALLOWED_ROLES:
            raise ValueError(f"agent at index {index} has an invalid role")

        status = raw_agent.get("status")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"agent at index {index} has an invalid status")

        normalized_agents.append(
            {
                "id": agent_id,
                "name": name,
                "role": role,
                "status": status,
            }
        )
        seen_ids.add(agent_id)

    return sorted(normalized_agents, key=lambda agent_data: agent_data["id"])


def read_agents_from_state():
    agents = []
    if not AGENTS_DIR.exists():
        return agents

    for path in sorted(
        AGENTS_DIR.iterdir(),
        key=lambda item: (0, int(item.name)) if AGENT_DIR_PATTERN.fullmatch(item.name) else (1, item.name),
    ):
        if not path.is_dir() or not AGENT_DIR_PATTERN.fullmatch(path.name):
            continue

        metadata = read_jsonfile(path / "metadata.json")
        if metadata is None:
            continue

        agents.append(metadata)

    return validate_agents(agents)


def list_known_agent_ids():
    ids = set()

    if AGENTS_DIR.exists():
        for path in AGENTS_DIR.iterdir():
            if path.is_dir() and AGENT_DIR_PATTERN.fullmatch(path.name):
                ids.add(int(path.name))

    for path in Path(".").iterdir():
        for pattern in (AGENT_ENVFILE_PATTERN, AGENT_SECRETS_ENVFILE_PATTERN):
            match = pattern.fullmatch(path.name)
            if match:
                ids.add(int(match.group(1)))

    return sorted(ids)


def actual_agent_status(agent_id):
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", service_unit(agent_id)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return "start" if result.returncode == 0 else "stop"


def remove_agent_state(agent_id):
    for path in (agent_envfile(agent_id), agent_secrets_envfile(agent_id)):
        if path.exists():
            path.unlink()

    subprocess.run(["podman", "volume", "rm", "--force", volume_name(agent_id)], check=False)

    if agent_dir(agent_id).exists():
        shutil.rmtree(agent_dir(agent_id), ignore_errors=True)


def generate_secret():
    return secrets.token_hex(16)