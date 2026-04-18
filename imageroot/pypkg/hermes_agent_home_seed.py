import json
import stat
from pathlib import Path

from hermes_agent_state import (
    ALLOWED_ROLES,
    HOME_ENV_TEMPLATE,
    HOME_VOLUME_STATE_FILE,
    read_jsonfile,
    soul_template_for_role,
    write_jsonfile,
    write_private_textfile,
)


ROLE_TITLES = {role: role.replace("_", " ") for role in ALLOWED_ROLES}
MANAGED_HOME_FILES = ("SOUL.md", ".env")


def build_template_replacements(agent_id, agent_name, agent_role):
    return {
        "__AGENT_ID__": str(agent_id),
        "__AGENT_NAME__": agent_name,
        "__AGENT_ROLE__": agent_role,
    }


def render_template_content(template_path, replacements):
    content = Path(template_path).read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    return content


def home_seed_state_path(home_dir):
    return Path(home_dir) / HOME_VOLUME_STATE_FILE


def read_home_seed_state(state_path):
    state_file = Path(state_path)

    try:
        state_stat = state_file.lstat()
    except FileNotFoundError:
        return {}

    if stat.S_ISLNK(state_stat.st_mode):
        state_file.unlink()
        return {}

    if not stat.S_ISREG(state_stat.st_mode):
        raise ValueError(f"unsafe seed state path: {state_file}")

    try:
        state_data = read_jsonfile(state_file)
    except json.JSONDecodeError:
        return {}

    return state_data if isinstance(state_data, dict) else {}


def build_desired_seed_entries(agent_data):
    role = agent_data["role"]
    return {
        "SOUL.md": {
            "template_role": role,
            "replacements": build_template_replacements(
                agent_data["id"],
                agent_data["name"],
                ROLE_TITLES.get(role, role),
            ),
        },
        ".env": {
            "replacements": build_template_replacements(
                agent_data["id"],
                agent_data["name"],
                role,
            ),
        },
    }


def render_seed_entry(file_name, entry):
    if not isinstance(entry, dict):
        return None

    replacements = entry.get("replacements")
    if not isinstance(replacements, dict):
        return None

    if file_name == "SOUL.md":
        template_role = entry.get("template_role")
        if template_role not in ALLOWED_ROLES:
            return None
        template_path = soul_template_for_role(template_role)
    elif file_name == ".env":
        template_path = HOME_ENV_TEMPLATE
    else:
        raise ValueError(f"unsupported managed file: {file_name}")

    return render_template_content(template_path, replacements)


def sync_seeded_file(target_path, file_name, desired_entry, previous_entry):
    desired_content = render_seed_entry(file_name, desired_entry)
    if desired_content is None:
        raise ValueError(f"failed to render desired managed file: {file_name}")

    if target_path.is_symlink():
        target_path.unlink()
        write_private_textfile(target_path, desired_content)
        return True, desired_entry

    if not target_path.exists():
        write_private_textfile(target_path, desired_content)
        return True, desired_entry

    current_content = target_path.read_text(encoding="utf-8")

    previous_content = render_seed_entry(file_name, previous_entry)
    if previous_content is None:
        if current_content == desired_content:
            return False, desired_entry
        return False, previous_entry

    if current_content != previous_content:
        return False, previous_entry

    if current_content != desired_content:
        write_private_textfile(target_path, desired_content)
        return True, desired_entry

    return False, desired_entry


def sync_seeded_home(home_dir, agent_data, state_path=None):
    home_path = Path(home_dir)
    home_path.mkdir(parents=True, exist_ok=True)
    volume_state_path = home_seed_state_path(home_path)
    managed_state_path = Path(state_path) if state_path is not None else volume_state_path
    previous_state = read_home_seed_state(managed_state_path)
    if not previous_state and managed_state_path != volume_state_path:
        previous_state = read_home_seed_state(volume_state_path)
    previous_files = previous_state.get("files") if isinstance(previous_state, dict) else {}
    if not isinstance(previous_files, dict):
        previous_files = {}

    desired_files = build_desired_seed_entries(agent_data)
    applied_files = {}
    changed = False

    for file_name in MANAGED_HOME_FILES:
        file_changed, applied_entry = sync_seeded_file(
            home_path / file_name,
            file_name,
            desired_files[file_name],
            previous_files.get(file_name),
        )
        if applied_entry is not None:
            applied_files[file_name] = applied_entry
        changed = changed or file_changed

    next_state = {"files": applied_files}
    state_targets = {managed_state_path, volume_state_path}
    for target_path in state_targets:
        if read_home_seed_state(target_path) != next_state:
            write_jsonfile(target_path, next_state)

    return changed