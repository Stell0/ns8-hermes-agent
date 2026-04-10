import json
import os
import re
import secrets
import socket
import stat
import subprocess
import tempfile
import time
from typing import Any
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
HERMES_IMAGE_ENV = "HERMES_AGENT_HERMES_IMAGE"
ALLOWED_ROLES = {
    "default",
    "developer",
    "marketing",
    "sales",
    "customer_support",
    "social_media_manager",
    "business_consultant",
    "researcher",
}
ALLOWED_STATUSES = {"start", "stop"}
NAME_PATTERN = re.compile(r"^[A-Za-z ]+$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
AGENT_ENVFILE_PATTERN = re.compile(r"^agent-(-?\d+)\.env$")
AGENT_SECRETS_ENVFILE_PATTERN = re.compile(r"^agent-(-?\d+)_secrets\.env$")
AGENT_OPENVIKING_CONFIG_PATTERN = re.compile(r"^agent-(-?\d+)_openviking\.conf$")
SYSTEMD_TARGET_PATTERN = re.compile(r"^hermes-agent@(\d+)\.target$")
OPENVIKING_CONFIG_PATH = "/app/ov.conf"
OPENVIKING_WORKSPACE_PATH = "/app/data"
TCP_PORT_ENV = "TCP_PORT"
OPENVIKING_PORT_ENV = "OPENVIKING_PORT"
TIMEZONE_ENV = "TIMEZONE"
OPENVIKING_ROOT_API_KEY_ENV = "OPENVIKING_ROOT_API_KEY"
OPENVIKING_TENANT_MODE_ENV = "OPENVIKING_TENANT_MODE"
OPENVIKING_AGENT_ID_ENV = "OPENVIKING_AGENT_ID"
OPENVIKING_EMBEDDING_PROVIDER_ENV = "OPENVIKING_EMBEDDING_PROVIDER"
OPENVIKING_EMBEDDING_API_KEY_ENV = "OPENVIKING_EMBEDDING_API_KEY"
OPENVIKING_TENANT_MODE = "shared"
OPENVIKING_LOCAL_HOST = "127.0.0.1"
OPENVIKING_CONTAINER_HOST = "host.containers.internal"
OPENVIKING_LISTEN_HOST = "0.0.0.0"
OPENVIKING_CONTAINER_PORT = 1933
OPENVIKING_HEALTH_TIMEOUT = 60
SYSTEM_AGENT_ID = 0
SYSTEM_AGENT_NAME = "OpenViking Backend"
SYSTEM_AGENT_ROLE = "default"
SYSTEM_AGENT_STATUS = "start"
SYSTEM_AGENT_ACCOUNT = "system"
SYSTEM_AGENT_USER = "system"
SYSTEM_AGENT_OPENVIKING_AGENT_ID = "openviking-backend"
SYSTEM_AGENT_SERVICE_UNIT = "hermes-agent-hermes-system.service"
HERMES_API_SERVER_ENABLED_ENV = "API_SERVER_ENABLED"
HERMES_API_SERVER_HOST_ENV = "API_SERVER_HOST"
HERMES_API_SERVER_PORT_ENV = "API_SERVER_PORT"
HERMES_API_SERVER_KEY_ENV = "API_SERVER_KEY"
HERMES_GATEWAY_PORT_ENV = "HERMES_GATEWAY_PORT"
HERMES_SYSTEM_API_PORT_ENV = "HERMES_SYSTEM_API_PORT"
HERMES_API_SERVER_HOST = "0.0.0.0"
HERMES_API_SERVER_PORT = 8642
HERMES_API_MODEL_NAME = "hermes-agent"
HERMES_MODEL_PROVIDER_KEY = "model.provider"
HERMES_MODEL_DEFAULT_KEY = "model.default"
HERMES_MODEL_BASE_URL_KEY = "model.base_url"
HERMES_OPENAI_API_KEY = "OPENAI_API_KEY"
SOUL_FILENAME = "SOUL.md"
ROLE_SOUL_PROFILES = {
    "default": {
        "identity": "You are a steady general-purpose assistant with a calm, practical voice.",
        "style": [
            "Be clear and structured.",
            "Prefer direct answers over filler.",
            "Adapt depth to the user's apparent need.",
            "Stay grounded and useful when the request is ambiguous.",
        ],
        "avoid": [
            "Overpromising certainty.",
            "Hype language.",
            "Unnecessary verbosity.",
        ],
        "defaults": [
            "Ask a clarifying question when the goal is underspecified.",
            "When there are tradeoffs, explain them briefly and pick a sensible default.",
            "If something is uncertain, say so plainly.",
        ],
    },
    "developer": {
        "identity": "You are a pragmatic technical partner who values correctness, clarity, and operational reality.",
        "style": [
            "Be direct and technically precise.",
            "Prefer compact answers unless complexity requires depth.",
            "Challenge weak assumptions clearly.",
            "Focus on root causes and defensible tradeoffs.",
        ],
        "avoid": [
            "Politeness theater.",
            "Hand-wavy architecture talk.",
            "Explaining obvious material at length.",
        ],
        "defaults": [
            "Separate facts from guesses.",
            "Point out risks, regressions, and edge cases when they matter.",
            "When several paths are possible, recommend the most practical one.",
        ],
    },
    "marketing": {
        "identity": "You are a sharp marketing strategist focused on positioning, audience fit, and message clarity.",
        "style": [
            "Write with energy, but stay disciplined.",
            "Make the value proposition concrete.",
            "Tailor language to audience, channel, and stage.",
            "Turn vague ideas into crisp messaging angles.",
        ],
        "avoid": [
            "Empty buzzwords.",
            "Claims without support.",
            "Generic brand language that could fit anything.",
        ],
        "defaults": [
            "Ask who the audience is if that changes the message.",
            "Prefer specific outcomes, differentiators, and calls to action.",
            "Keep copy punchy unless long-form strategy is explicitly needed.",
        ],
    },
    "sales": {
        "identity": "You are a consultative sales operator who listens carefully, qualifies needs, and moves conversations toward concrete next steps.",
        "style": [
            "Be confident, clear, and commercially aware.",
            "Surface pain points, constraints, and decision drivers.",
            "Frame recommendations in terms of value and fit.",
            "Handle objections honestly instead of forcing the close.",
        ],
        "avoid": [
            "Pushy pressure tactics.",
            "Overpromising outcomes.",
            "Needless jargon when plain language would work better.",
        ],
        "defaults": [
            "Clarify buyer context before pitching too hard.",
            "When useful, suggest a concrete follow-up, offer, or next action.",
            "Protect credibility over short-term persuasion.",
        ],
    },
    "customer_support": {
        "identity": "You are a calm customer support specialist focused on resolution, empathy, and fast understanding.",
        "style": [
            "Acknowledge the problem without sounding scripted.",
            "Guide troubleshooting step by step.",
            "Reduce confusion and keep momentum.",
            "Use plain language before specialized terminology.",
        ],
        "avoid": [
            "Blaming the user.",
            "Defensive phrasing.",
            "Long digressions that delay the fix.",
        ],
        "defaults": [
            "Ask only the questions needed to unblock resolution.",
            "Summarize the likely issue and the next step clearly.",
            "When something is not possible, explain the constraint plainly and offer the best alternative.",
        ],
    },
    "social_media_manager": {
        "identity": "You are a social media manager with strong instincts for hooks, audience attention, and platform-native messaging.",
        "style": [
            "Be concise, current, and audience-aware.",
            "Shape content for reach, clarity, and brand consistency.",
            "Offer multiple angles, hooks, and caption directions when useful.",
            "Balance creativity with practical execution.",
        ],
        "avoid": [
            "Forced meme language.",
            "Spammy calls to action.",
            "Overlong copy that buries the hook.",
        ],
        "defaults": [
            "Consider platform and audience before choosing tone.",
            "Prefer punchy drafts and reusable content formats.",
            "Flag when a trend-dependent idea may age badly or dilute the brand.",
        ],
    },
    "business_consultant": {
        "identity": "You are a business consultant who frames problems cleanly and turns ambiguity into decisions, priorities, and tradeoffs.",
        "style": [
            "Be structured and commercially grounded.",
            "Diagnose the problem before recommending action.",
            "Present options in terms of cost, risk, and expected payoff.",
            "Prefer clear reasoning over polished vagueness.",
        ],
        "avoid": [
            "Hand-wavy strategic filler.",
            "Pretending uncertainty does not exist.",
            "Frameworks without a practical conclusion.",
        ],
        "defaults": [
            "If priorities are unclear, impose structure and sequencing.",
            "Recommend the most actionable option when the analysis is sufficient.",
            "Call out assumptions that materially affect the recommendation.",
        ],
    },
    "researcher": {
        "identity": "You are a thoughtful research collaborator who values evidence, careful synthesis, and honest uncertainty.",
        "style": [
            "Be curious, rigorous, and explicit about confidence levels.",
            "Separate observation, inference, and speculation.",
            "Look for patterns, contradictions, and missing evidence.",
            "Prefer depth and signal over shallow completeness.",
        ],
        "avoid": [
            "Claiming certainty without support.",
            "Flattening nuanced findings into a false consensus.",
            "Premature conclusions.",
        ],
        "defaults": [
            "Ask clarifying questions when the research target is underspecified.",
            "Name important limitations and open questions.",
            "When a recommendation is needed, tie it back to the strongest available evidence.",
        ],
    },
}
SUPPORTED_EMBEDDING_PROVIDERS = {
    "gemini",
    "jina",
    "minimax",
    "openai",
    "volcengine",
    "voyage",
}
EMBEDDING_PROVIDER_DEFAULTS = {
    "gemini": {
        "model": "text-embedding-004",
        "dimension": 768,
    },
    "jina": {
        "model": "jina-embeddings-v5-text-small",
        "dimension": 1024,
    },
    "minimax": {
        "model": "embo-01",
        "dimension": 1536,
    },
    "openai": {
        "model": "text-embedding-3-large",
        "dimension": 3072,
    },
    "volcengine": {
        "model": "doubao-embedding-vision-250615",
        "dimension": 1024,
        "input": "multimodal",
    },
    "voyage": {
        "model": "voyage-3.5-lite",
        "dimension": 1024,
    },
}
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
SYSTEMD_ENV_KEYS = {OPENVIKING_PORT_ENV, HERMES_SYSTEM_API_PORT_ENV, TIMEZONE_ENV}
RESERVED_OPENVIKING_IDENTIFIERS = {
    "account": {SYSTEM_AGENT_ACCOUNT},
    "user": {SYSTEM_AGENT_USER},
    "agent_id": {SYSTEM_AGENT_OPENVIKING_AGENT_ID},
}


def is_system_agent_id(agent_id):
    return int(agent_id) == SYSTEM_AGENT_ID


def system_agent_data():
    return {
        "id": SYSTEM_AGENT_ID,
        "name": SYSTEM_AGENT_NAME,
        "role": SYSTEM_AGENT_ROLE,
        "status": SYSTEM_AGENT_STATUS,
        "account": SYSTEM_AGENT_ACCOUNT,
        "user": SYSTEM_AGENT_USER,
        "agent_id": SYSTEM_AGENT_OPENVIKING_AGENT_ID,
        "use_default_gateway_for_llm": False,
        "hidden": True,
        "protected": True,
        "system": True,
    }


def attach_agent_metadata(agent_data):
    if is_system_agent_id(agent_data["id"]):
        return {
            **agent_data,
            "hidden": True,
            "protected": True,
            "system": True,
        }

    return {
        **agent_data,
        "hidden": False,
        "protected": False,
        "system": False,
    }


def managed_agents(user_agents):
    return [system_agent_data(), *sorted(user_agents, key=lambda item: item["id"])]


def read_managed_agents_from_state():
    return managed_agents(read_agents_from_state())


def get_agent_definition(agent_id):
    for agent_data in read_managed_agents_from_state():
        if agent_data["id"] == agent_id:
            return agent_data

    return None


def valid_embedding_provider(value):
    return isinstance(value, str) and value in SUPPORTED_EMBEDDING_PROVIDERS


def embedding_defaults(provider):
    return EMBEDDING_PROVIDER_DEFAULTS[provider].copy()


def normalize_optional_string(value):
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("value must be a string")

    normalized_value = value.strip()
    return normalized_value or None


def read_openviking_settings(shared_environment=None, shared_secrets=None):
    shared_environment = shared_environment or read_optional_envfile(ENVIRONMENT_FILE)
    shared_secrets = shared_secrets or read_optional_envfile(SHARED_SECRETS_ENVFILE)

    provider = normalize_optional_string(shared_environment.get(OPENVIKING_EMBEDDING_PROVIDER_ENV))
    if not valid_embedding_provider(provider):
        provider = None

    embedding_settings: dict[str, Any] = {
        "api_key_configured": bool(shared_secrets.get(OPENVIKING_EMBEDDING_API_KEY_ENV)),
    }
    if provider:
        embedding_settings["provider"] = provider

    return {
        "embedding": embedding_settings,
    }


def validate_openviking_settings(raw_openviking, existing_openviking=None):
    if raw_openviking is None:
        return read_openviking_settings()

    if not isinstance(raw_openviking, dict):
        raise ValueError("openviking must be an object")

    raw_embedding = raw_openviking.get("embedding") or {}
    if not isinstance(raw_embedding, dict):
        raise ValueError("openviking embedding must be an object")

    provider = normalize_optional_string(raw_embedding.get("provider"))
    api_key = normalize_optional_string(raw_embedding.get("api_key"))
    existing_openviking = existing_openviking or read_openviking_settings()
    existing_embedding = existing_openviking.get("embedding", {})
    existing_provider = existing_embedding.get("provider")

    if provider is None:
        return {
            "embedding": {
                "api_key": None,
                "api_key_configured": False,
            }
        }

    if not valid_embedding_provider(provider):
        raise ValueError(f"unsupported embedding provider: {provider}")

    if not api_key and (provider != existing_provider or not existing_embedding.get("api_key_configured")):
        raise ValueError("embedding api_key is required")

    return {
        "embedding": {
            "provider": provider,
            "api_key": api_key,
            "api_key_configured": bool(api_key or existing_embedding.get("api_key_configured")),
        }
    }


def persist_openviking_settings(openviking_settings):
    embedding_settings = openviking_settings.get("embedding", {})
    provider = embedding_settings.get("provider") or ""
    agent.set_env(OPENVIKING_EMBEDDING_PROVIDER_ENV, provider)

    shared_secrets = read_optional_envfile(SHARED_SECRETS_ENVFILE)
    updated_shared_secrets = {
        key: value
        for key, value in shared_secrets.items()
        if key != OPENVIKING_EMBEDDING_API_KEY_ENV
    }
    api_key = embedding_settings.get("api_key")
    if api_key:
        updated_shared_secrets[OPENVIKING_EMBEDDING_API_KEY_ENV] = api_key

    write_envfile(SHARED_SECRETS_ENVFILE, updated_shared_secrets)


def configure_module(request_payload):
    user_agents = validate_agents(request_payload.get("agents", []))
    openviking_settings = None
    if "openviking" in request_payload:
        existing_openviking = read_openviking_settings()
        openviking_settings = validate_openviking_settings(request_payload.get("openviking"), existing_openviking)

    persist_agents(user_agents)
    if openviking_settings is not None:
        persist_openviking_settings(openviking_settings)


def get_configuration():
    return {
        "agents": [
            {
                **attach_agent_metadata(agent_data),
                "status": actual_agent_status(agent_data["id"]),
            }
            for agent_data in read_managed_agents_from_state()
        ],
        "openviking": read_openviking_settings(),
    }


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
    seen_users = set()
    seen_agent_ids = set()

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

        use_default_gateway_for_llm = raw_agent.get("use_default_gateway_for_llm", False)
        if not isinstance(use_default_gateway_for_llm, bool):
            raise ValueError(f"agent at index {index} has an invalid use_default_gateway_for_llm flag")

        account = normalize_identifier(
            raw_agent.get("account"),
            default_openviking_account(agent_id),
            f"agent at index {index} has an invalid account",
        )
        if account in seen_accounts:
            raise ValueError(f"agent account {account} is duplicated")
        if account in RESERVED_OPENVIKING_IDENTIFIERS["account"]:
            raise ValueError(f"agent account {account} is reserved")

        user = normalize_identifier(
            raw_agent.get("user"),
            default_openviking_user(agent_id),
            f"agent at index {index} has an invalid user",
        )
        if user in seen_users:
            raise ValueError(f"agent user {user} is duplicated")
        if user in RESERVED_OPENVIKING_IDENTIFIERS["user"]:
            raise ValueError(f"agent user {user} is reserved")

        openviking_agent_id = normalize_identifier(
            raw_agent.get("agent_id"),
            default_openviking_agent_id(agent_id),
            f"agent at index {index} has an invalid agent_id",
        )
        if openviking_agent_id in seen_agent_ids:
            raise ValueError(f"agent agent_id {openviking_agent_id} is duplicated")
        if openviking_agent_id in RESERVED_OPENVIKING_IDENTIFIERS["agent_id"]:
            raise ValueError(f"agent agent_id {openviking_agent_id} is reserved")

        normalized_agents.append(
            {
                "id": agent_id,
                "name": name,
                "role": role,
                "status": status,
                "account": account,
                "user": user,
                "agent_id": openviking_agent_id,
                "use_default_gateway_for_llm": use_default_gateway_for_llm,
            }
        )
        seen_ids.add(agent_id)
        seen_accounts.add(account)
        seen_users.add(user)
        seen_agent_ids.add(openviking_agent_id)

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
                "true" if agent_data.get("use_default_gateway_for_llm") else "false",
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

        parts = serialized_agent.split(":")
        if len(parts) in {3, 4}:
            return []
        if len(parts) not in {7, 8}:
            raise ValueError(f"invalid AGENTS_LIST entry: {serialized_agent}")

        use_default_gateway_for_llm = False
        if len(parts) == 7:
            agent_id, name, role, status, account, user, openviking_agent_id = parts
        else:
            agent_id, name, role, status, account, user, openviking_agent_id, raw_gateway_flag = parts
            if raw_gateway_flag not in {"true", "false"}:
                raise ValueError(f"invalid AGENTS_LIST use_default_gateway_for_llm: {raw_gateway_flag}")
            use_default_gateway_for_llm = raw_gateway_flag == "true"

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
                "use_default_gateway_for_llm": use_default_gateway_for_llm,
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


def hermes_container_name(agent_id):
    return f"hermes-agent-hermes-{agent_id}"


def hermes_data_volume(agent_id):
    return f"hermes-agent-hermes-data-{agent_id}"


def legacy_openviking_data_volume(agent_id):
    return f"hermes-agent-openviking-data-{agent_id}"


def shared_openviking_data_volume():
    return "hermes-agent-openviking-data"


def target_unit(agent_id):
    return f"hermes-agent@{agent_id}.target"


def container_service_units(agent_id):
    return [
        f"hermes-agent-hermes@{agent_id}.service",
    ]


def managed_service_units(agent_id):
    return [
        shared_openviking_service_unit(),
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
    file_path = Path(path)
    file_path.write_text(f"{json.dumps(data, indent=2)}\n", encoding="utf-8")
    os.chmod(file_path, 0o600)


def ensure_private_directory(path):
    directory_path = Path(path)

    try:
        directory_stat = directory_path.lstat()
    except FileNotFoundError:
        directory_path.mkdir(parents=True, exist_ok=True)
        directory_stat = directory_path.lstat()

    if stat.S_ISLNK(directory_stat.st_mode) or not stat.S_ISDIR(directory_stat.st_mode):
        raise ValueError(f"unsafe directory path: {directory_path}")

    return directory_path


def read_private_textfile(path):
    file_path = Path(path)

    try:
        file_stat = file_path.lstat()
    except FileNotFoundError:
        return None

    if not stat.S_ISREG(file_stat.st_mode):
        return None

    return file_path.read_text(encoding="utf-8")


def write_private_textfile(path, content):
    file_path = Path(path)
    parent_path = ensure_private_directory(file_path.parent)
    temp_path = None
    file_descriptor = None

    try:
        file_descriptor, temp_path = tempfile.mkstemp(prefix=f".{file_path.name}.", dir=parent_path)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temp_file:
            file_descriptor = None
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.chmod(temp_path, 0o600)
        os.replace(temp_path, file_path)
    except Exception:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temp_path is not None and os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def render_agent_soul(agent_name, role):
    if role not in ROLE_SOUL_PROFILES:
        raise ValueError(f"unsupported soul role: {role}")

    profile = ROLE_SOUL_PROFILES[role]
    lines = [
        f"- Your name is {agent_name}, you are an Hermes Agent that runs on NethServer8",
        "",
        "## Identity",
        profile["identity"],
        "",
        "## Style",
        *(f"- {item}" for item in profile["style"]),
        "",
        "## Avoid",
        *(f"- {item}" for item in profile["avoid"]),
        "",
        "## Defaults",
        *(f"- {item}" for item in profile["defaults"]),
        "",
    ]
    return "\n".join(lines)


def previous_seeded_agent_soul(existing_agent_env):
    previous_name = normalize_optional_string(existing_agent_env.get("AGENT_NAME"))
    previous_role = existing_agent_env.get("AGENT_ROLE")
    if not previous_name or previous_role not in ROLE_SOUL_PROFILES:
        return None

    return render_agent_soul(previous_name, previous_role)


def should_replace_agent_soul(current_content, existing_agent_env):
    if current_content is None or not current_content.strip():
        return True

    previous_seed = previous_seeded_agent_soul(existing_agent_env)
    if not previous_seed:
        return False

    return current_content == previous_seed


def ensure_podman_volume(volume_name):
    run_command(["podman", "volume", "create", volume_name], capture_output=True)


def podman_volume_mountpoint(volume_name):
    result = run_command(
        ["podman", "volume", "inspect", volume_name, "--format", "{{.Mountpoint}}"],
        capture_output=True,
    )
    mountpoint = (result.stdout or "").strip()
    if not mountpoint:
        raise ValueError(f"missing mountpoint for volume {volume_name}")

    return Path(mountpoint)


def agent_hermes_home(agent_id):
    ensure_podman_volume(hermes_data_volume(agent_id))
    return ensure_private_directory(podman_volume_mountpoint(hermes_data_volume(agent_id)))


def sync_agent_soul(agent_data, existing_agent_env):
    soul_path = agent_hermes_home(agent_data["id"]) / SOUL_FILENAME
    current_content = read_private_textfile(soul_path)

    if not should_replace_agent_soul(current_content, existing_agent_env):
        return False

    write_private_textfile(soul_path, render_agent_soul(agent_data["name"], agent_data["role"]))
    return True


def valid_port_value(value):
    return isinstance(value, str) and value.isdigit() and 1 <= int(value) <= 65535


def reserve_tcp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((OPENVIKING_LOCAL_HOST, 0))
        return server_socket.getsockname()[1]


def ensure_shared_openviking_settings(shared_environment, shared_secrets):
    port_value = shared_environment.get(OPENVIKING_PORT_ENV)
    if not valid_port_value(port_value):
        port_value = shared_environment.get(TCP_PORT_ENV)
        if valid_port_value(port_value):
            agent.set_env(OPENVIKING_PORT_ENV, port_value)
            shared_environment[OPENVIKING_PORT_ENV] = port_value
        else:
            raise ValueError(f"invalid {OPENVIKING_PORT_ENV}: {shared_environment.get(OPENVIKING_PORT_ENV)}")

    timezone = normalize_optional_string(shared_environment.get(TIMEZONE_ENV))
    if timezone is None:
        timezone = normalize_optional_string(os.getenv(TIMEZONE_ENV)) or "UTC"
        agent.set_env(TIMEZONE_ENV, timezone)
        shared_environment[TIMEZONE_ENV] = timezone

    system_api_port = shared_environment.get(HERMES_SYSTEM_API_PORT_ENV)
    if not valid_port_value(system_api_port):
        system_api_port = str(reserve_tcp_port())
        agent.set_env(HERMES_SYSTEM_API_PORT_ENV, system_api_port)
        shared_environment[HERMES_SYSTEM_API_PORT_ENV] = system_api_port

    root_api_key = shared_secrets.get(OPENVIKING_ROOT_API_KEY_ENV)
    if not root_api_key:
        root_api_key = generate_agent_secret(OPENVIKING_ROOT_API_KEY_ENV)
        shared_secrets = {**shared_secrets, OPENVIKING_ROOT_API_KEY_ENV: root_api_key}
        write_envfile(SHARED_SECRETS_ENVFILE, shared_secrets)

    return int(port_value), root_api_key, int(system_api_port)


def openviking_port(shared_environment):
    port_value = shared_environment.get(OPENVIKING_PORT_ENV)
    if not valid_port_value(port_value):
        raise ValueError(f"invalid {OPENVIKING_PORT_ENV}: {port_value}")

    return int(port_value)


def openviking_host_endpoint(shared_environment):
    return f"http://{OPENVIKING_LOCAL_HOST}:{openviking_port(shared_environment)}"


def openviking_container_endpoint(shared_environment):
    return f"http://{OPENVIKING_CONTAINER_HOST}:{openviking_port(shared_environment)}"


def hermes_system_api_port(shared_environment):
    port_value = shared_environment.get(HERMES_SYSTEM_API_PORT_ENV)
    if not valid_port_value(port_value):
        raise ValueError(f"invalid {HERMES_SYSTEM_API_PORT_ENV}: {port_value}")

    return int(port_value)


def hermes_system_api_base(shared_environment):
    return f"http://{OPENVIKING_CONTAINER_HOST}:{hermes_system_api_port(shared_environment)}/v1"


def hermes_runtime_image(shared_environment):
    image = shared_environment.get(HERMES_IMAGE_ENV)
    if not image:
        raise ValueError(f"missing {HERMES_IMAGE_ENV}")

    return image


def podman_run_hermes_config(agent_id, shared_environment, key, value):
    run_command(
        [
            "podman",
            "run",
            "--rm",
            "--volume",
            f"{hermes_data_volume(agent_id)}:/opt/data:z",
            "--env",
            "HERMES_HOME=/opt/data",
            hermes_runtime_image(shared_environment),
            "config",
            "set",
            key,
            value,
        ]
    )


def sync_agent_llm_gateway_config(agent_data, shared_environment, system_agent_secrets):
    gateway_enabled = agent_data.get("use_default_gateway_for_llm", False)
    config_values = [
        (HERMES_MODEL_PROVIDER_KEY, "custom" if gateway_enabled else "auto"),
        (HERMES_MODEL_DEFAULT_KEY, HERMES_API_MODEL_NAME if gateway_enabled else ""),
        (HERMES_MODEL_BASE_URL_KEY, hermes_system_api_base(shared_environment) if gateway_enabled else ""),
        (
            HERMES_OPENAI_API_KEY,
            system_agent_secrets.get(HERMES_API_SERVER_KEY_ENV, "") if gateway_enabled else "",
        ),
    ]

    if gateway_enabled and not config_values[-1][1]:
        raise ValueError("missing system gateway API key")

    for key, value in config_values:
        podman_run_hermes_config(agent_data["id"], shared_environment, key, value)


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

    if is_system_agent_id(agent_data["id"]):
        env_data.update(
            {
                HERMES_GATEWAY_PORT_ENV: str(HERMES_API_SERVER_PORT),
                HERMES_API_SERVER_ENABLED_ENV: "true",
                HERMES_API_SERVER_HOST_ENV: HERMES_API_SERVER_HOST,
                HERMES_API_SERVER_PORT_ENV: str(HERMES_API_SERVER_PORT),
            }
        )

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
    agent_data=None,
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
    if agent_data and is_system_agent_id(agent_data["id"]):
        env_data[HERMES_API_SERVER_KEY_ENV] = existing_agent_secrets.get(HERMES_API_SERVER_KEY_ENV) or generate_agent_secret(
            HERMES_API_SERVER_KEY_ENV
        )
    return env_data


def build_systemd_environment(shared_environment):
    return {
        key: value
        for key, value in shared_environment.items()
        if key.endswith("_IMAGE") or key in SYSTEMD_ENV_KEYS
    }


def build_openviking_embedding_config(shared_environment, shared_secrets):
    provider = normalize_optional_string(shared_environment.get(OPENVIKING_EMBEDDING_PROVIDER_ENV))
    if not valid_embedding_provider(provider):
        return None

    api_key = shared_secrets.get(OPENVIKING_EMBEDDING_API_KEY_ENV)
    if not api_key:
        return None

    dense_config = {
        "provider": provider,
        "api_key": api_key,
        **embedding_defaults(provider),
    }
    return {
        "max_concurrent": 10,
        "max_retries": 3,
        "dense": dense_config,
    }


def build_openviking_config(shared_environment, shared_secrets, system_agent_secrets):
    config = {
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
        "vlm": {
            "provider": "openai",
            "api_base": hermes_system_api_base(shared_environment),
            "api_key": system_agent_secrets[HERMES_API_SERVER_KEY_ENV],
            "model": HERMES_API_MODEL_NAME,
            "max_retries": 2,
        },
    }

    embedding_config = build_openviking_embedding_config(shared_environment, shared_secrets)
    if embedding_config:
        config["embedding"] = embedding_config
        config["storage"]["vectordb"]["dimension"] = embedding_config["dense"]["dimension"]

    return config


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
    agent_data = get_agent_definition(agent_id)
    if agent_data is None:
        raise ValueError(f"agent {agent_id} not found")

    shared_environment = read_optional_envfile(ENVIRONMENT_FILE)
    shared_secrets = read_optional_envfile(SHARED_SECRETS_ENVFILE)
    port, root_api_key, _ = ensure_shared_openviking_settings(shared_environment, shared_secrets)
    wait_for_openviking(port)

    shared_secrets = read_optional_envfile(SHARED_SECRETS_ENVFILE)
    agent_secrets = read_optional_envfile(agent_secrets_envfile(agent_id))
    existing_user_key = agent_secrets.get("OPENVIKING_API_KEY")
    if existing_user_key and openviking_user_key_is_valid(port, existing_user_key):
        write_envfile(
            agent_secrets_envfile(agent_id),
            build_agent_secrets_env(
                shared_secrets,
                agent_data=agent_data,
                existing_agent_secrets=agent_secrets,
                preserve_openviking_api_key=True,
            ),
        )
        return existing_user_key

    user_key = provision_openviking_tenant(port, root_api_key, agent_data)
    updated_agent_secrets = build_agent_secrets_env(shared_secrets, agent_data=agent_data, existing_agent_secrets=agent_secrets)
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

    assert port_value is not None
    port = int(port_value)
    wait_for_openviking(port)
    status_code, _ = openviking_request(
        "DELETE",
        f"/api/v1/admin/accounts/{urllib_parse.quote(account_id)}",
        port,
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
    agents = read_managed_agents_from_state()
    shared_environment = read_optional_envfile(ENVIRONMENT_FILE)
    shared_secrets = read_optional_envfile(SHARED_SECRETS_ENVFILE)

    ensure_shared_openviking_settings(shared_environment, shared_secrets)
    shared_environment = read_optional_envfile(ENVIRONMENT_FILE)
    shared_secrets = read_optional_envfile(SHARED_SECRETS_ENVFILE)

    write_envfile(SYSTEMD_ENVFILE, build_systemd_environment(shared_environment))

    if agent_id is not None:
        filtered_agents = [item for item in agents if item["id"] == agent_id]
        if not filtered_agents:
            raise ValueError(f"agent {agent_id} not found")
        agents = filtered_agents

    current_ids = {item["id"] for item in read_managed_agents_from_state()}
    generated_agent_secrets = {}

    for agent_data in agents:
        existing_agent_env = read_optional_envfile(agent_envfile(agent_data["id"]))
        existing_agent_secrets = read_optional_envfile(agent_secrets_envfile(agent_data["id"]))
        agent_secrets = build_agent_secrets_env(
            shared_secrets,
            agent_data=agent_data,
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
        if not is_system_agent_id(agent_data["id"]) and agent_data["status"] == "start":
            sync_agent_soul(agent_data, existing_agent_env)
        generated_agent_secrets[agent_data["id"]] = agent_secrets
        legacy_configfile = agent_openviking_configfile(agent_data["id"])
        if os.path.exists(legacy_configfile):
            os.remove(legacy_configfile)

    system_agent_secrets = generated_agent_secrets.get(SYSTEM_AGENT_ID) or read_optional_envfile(
        agent_secrets_envfile(SYSTEM_AGENT_ID)
    )

    for agent_data in agents:
        if is_system_agent_id(agent_data["id"]):
            continue

        sync_agent_llm_gateway_config(agent_data, shared_environment, system_agent_secrets)

    write_jsonfile(
        shared_openviking_configfile(),
        build_openviking_config(shared_environment, shared_secrets, system_agent_secrets),
    )

    return agents


def stop_disable_agent(agent_id):
    systemctl_user("disable", "--now", target_unit(agent_id), check=False)
    run_command(["podman", "rm", "--force", hermes_container_name(agent_id)], check=False)


def cleanup_agent_runtime(agent_id):
    if is_system_agent_id(agent_id):
        systemctl_user("disable", "--now", SYSTEM_AGENT_SERVICE_UNIT, check=False)
        run_command(["podman", "rm", "--force", hermes_container_name(agent_id)], check=False)
        remove_agent_openviking_account(agent_id)
        remove_agent_volumes(agent_id)
        remove_agent_runtime_files(agent_id)
        return

    stop_disable_agent(agent_id)
    remove_agent_openviking_account(agent_id)
    remove_agent_volumes(agent_id)
    remove_agent_runtime_files(agent_id)


def actual_agent_status(agent_id):
    if is_system_agent_id(agent_id):
        if all(
            unit_is_active(unit_name)
            for unit_name in (shared_openviking_service_unit(), SYSTEM_AGENT_SERVICE_UNIT)
        ):
            return "start"
        return "stop"

    services = managed_service_units(agent_id)
    if all(unit_is_active(unit_name) for unit_name in services):
        return "start"
    return "stop"