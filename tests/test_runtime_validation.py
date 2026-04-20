import importlib.util
import io
import json
import os
import runpy
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "imageroot" / "pypkg" / "hermes_agent_state.py"
SYNC_PATH = ROOT / "imageroot" / "bin" / "sync-agent-runtime"
REMOVE_AGENT_STATE_PATH = ROOT / "imageroot" / "bin" / "remove-agent-state"
SERVICE_TEMPLATE_PATH = ROOT / "imageroot" / "systemd" / "user" / "hermes@.service"
DASHBOARD_SERVICE_TEMPLATE_PATH = ROOT / "imageroot" / "systemd" / "user" / "hermes-dashboard@.service"
POD_SERVICE_TEMPLATE_PATH = ROOT / "imageroot" / "systemd" / "user" / "hermes-pod@.service"
HERMES_CONTAINERFILE_PATH = ROOT / "containers" / "hermes" / "Containerfile"
HERMES_ENTRYPOINT_PATH = ROOT / "containers" / "hermes" / "entrypoint.sh"
CREATE_MODULE_ACTION_DIR = ROOT / "imageroot" / "actions" / "create-module"
CONFIGURE_MODULE_ACTION_DIR = ROOT / "imageroot" / "actions" / "configure-module"
DESTROY_MODULE_ACTION_DIR = ROOT / "imageroot" / "actions" / "destroy-module"
PERSIST_SHARED_ENV_PATH = CONFIGURE_MODULE_ACTION_DIR / "20persist-shared-env"
SEED_AGENT_HOME_ACTION_PATH = CONFIGURE_MODULE_ACTION_DIR / "75seed-agent-home"
RECONCILE_DESIRED_ROUTES_PATH = CONFIGURE_MODULE_ACTION_DIR / "90reconcile-desired-routes"
DESTROY_REMOVE_ROUTES_PATH = DESTROY_MODULE_ACTION_DIR / "10remove-routes"
GET_CONFIGURATION_PATH = ROOT / "imageroot" / "actions" / "get-configuration" / "20read"
GET_AGENT_RUNTIME_PATH = ROOT / "imageroot" / "actions" / "get-agent-runtime" / "10read"
UPDATE_TCP_PORTS_PATH = ROOT / "imageroot" / "update-module.d" / "10ensure_tcp_ports"
SMARTHOST_CHANGED_EVENT_PATH = ROOT / "imageroot" / "events" / "smarthost-changed" / "10reload_services"


def load_module(path, module_name):
    loader = SourceFileLoader(module_name, str(path))
    spec = importlib.util.spec_from_loader(module_name, loader)
    if spec is None:
        raise RuntimeError(f"failed to load module from {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader.exec_module(module)
    return module


@contextmanager
def working_directory(path):
    current_directory = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(current_directory)


def write_envfile(path, env_data):
    file_path = Path(path)
    content = "\n".join(f"{key}={value}" for key, value in env_data.items())
    if content:
        content = f"{content}\n"
    file_path.write_text(content, encoding="utf-8")


def write_executable(path, content):
    file_path = Path(path)
    file_path.write_text(content, encoding="utf-8")
    file_path.chmod(0o755)


def read_envfile(path):
    file_path = Path(path)
    if not file_path.exists():
        return {}

    env_data = {}
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        env_data[key] = value
    return env_data


def strict_read_envfile(path):
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8"):
        pass

    return read_envfile(file_path)


def action_steps(action_dir):
    return sorted(
        path
        for path in Path(action_dir).iterdir()
        if path.is_file() and len(path.name) >= 2 and path.name[:2].isdigit()
    )


def run_action(action_dir, stdin_payload="{}"):
    for step_path in action_steps(action_dir):
        with mock.patch("sys.stdin", io.StringIO(stdin_payload)):
            try:
                runpy.run_path(str(step_path), run_name="__main__")
            except SystemExit as exit_error:
                if exit_error.code not in (0, None):
                    raise


def set_env_side_effect(name, value):
    os.environ[name] = value
    env_data = read_envfile("environment")
    env_data[name] = value
    write_envfile("environment", env_data)


def unset_env_side_effect(name):
    os.environ.pop(name, None)
    env_path = Path("environment")
    env_data = read_envfile(env_path)
    if name not in env_data:
        return

    env_data.pop(name, None)
    if env_data:
        write_envfile(env_path, env_data)
    elif env_path.exists():
        env_path.unlink()


def emulate_remove_agent_state(command):
    original_argv = sys.argv[:]
    sys.argv[:] = [str(REMOVE_AGENT_STATE_PATH), *command[2:]]
    try:
        try:
            runpy.run_path(str(REMOVE_AGENT_STATE_PATH), run_name="__main__")
        except SystemExit as exit_error:
            if exit_error.code not in (0, None):
                raise
    finally:
        sys.argv[:] = original_argv

    return types.SimpleNamespace(returncode=0)


def persist_process_environment(path="environment"):
    env_data = read_envfile(path)
    for key in (
        "MODULE_ID",
        "TIMEZONE",
        "TCP_PORT",
        "TCP_PORTS_RANGE",
        "BASE_VIRTUALHOST",
        "LETS_ENCRYPT",
    ):
        value = os.environ.get(key)
        if value is not None:
            env_data[key] = value

    if env_data:
        write_envfile(path, env_data)


def emulate_sync_agent_runtime(sync_module, command):
    agent_id = None
    if "--agent-id" in command:
        agent_id = int(command[command.index("--agent-id") + 1])

    persist_process_environment()

    with mock.patch.object(sync_module.agent, "read_envfile", side_effect=read_envfile, create=True), mock.patch.object(
        sync_module.agent,
        "write_envfile",
        side_effect=write_envfile,
        create=True,
    ):
        sync_module.sync_agent_runtime_files(agent_id=agent_id)

    return types.SimpleNamespace(returncode=0)


def run_seed_script(script, data_dir, agent_id, agent_name, agent_role):
    subprocess.run(
        [
            "/bin/sh",
            "-eu",
            "-c",
            script,
        ],
        check=True,
        env={
            **os.environ,
            "AGENT_ID": str(agent_id),
            "AGENT_NAME": agent_name,
            "AGENT_ROLE": agent_role,
        },
    )


class HermesModuleStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = load_module(STATE_PATH, "hermes_agent_state")
        original_agent = sys.modules.get("agent")
        if original_agent is None:
            agent_stub = types.ModuleType("agent")
            setattr(agent_stub, "read_envfile", read_envfile)
            setattr(agent_stub, "write_envfile", write_envfile)
            sys.modules["agent"] = agent_stub

        try:
            cls.sync = load_module(SYNC_PATH, "sync_agent_runtime_under_test")
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

    def test_read_agents_from_state_accepts_supported_roles(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            for index, role in enumerate(self.state.ALLOWED_ROLES, start=1):
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(index),
                    {
                        "id": index,
                        "name": "Valid Name",
                        "role": role,
                        "status": "start",
                    },
                )

            agents = self.state.read_agents_from_state()

        self.assertEqual([agent_data["role"] for agent_data in agents], list(self.state.ALLOWED_ROLES))

    def test_soul_template_lookup_accepts_supported_roles_and_rejects_invalid_role(self):
        for role in self.state.ALLOWED_ROLES:
            with self.subTest(role=role):
                template_path = self.state.soul_template_for_role(role)

                self.assertEqual(template_path.name, f"{role}.md.in")
                self.assertTrue(template_path.is_file())

        with self.assertRaisesRegex(ValueError, "invalid role"):
            self.state.soul_template_for_role("invalid_role")

    def test_read_agents_from_state_rejects_tampered_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.ensure_private_directory(self.state.AGENTS_DIR / "1")
            (self.state.AGENTS_DIR / "1" / "metadata.json").write_text(
                json.dumps(
                    {
                        "id": "../../outside",
                        "name": "Alice User",
                        "role": "developer",
                        "status": "start",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "invalid id"):
                self.state.read_agents_from_state()

    def test_read_agents_from_state_rejects_unexpected_fields(self):
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(1),
                    {
                        "id": 1,
                        "name": "Valid Name",
                        "role": "default",
                        "status": "start",
                        "use_default_gateway_for_llm": True,
                    },
                )
                self.state.read_agents_from_state()

    def test_read_agents_from_state_rejects_invalid_id(self):
        with self.assertRaisesRegex(ValueError, "invalid id"):
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(1),
                    {
                        "id": 0,
                        "name": "Valid Name",
                        "role": "default",
                        "status": "start",
                    },
                )
                self.state.read_agents_from_state()

    def test_read_agents_from_state_rejects_id_above_supported_limit(self):
        with self.assertRaisesRegex(ValueError, "invalid id"):
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(1),
                    {
                        "id": 31,
                        "name": "Valid Name",
                        "role": "default",
                        "status": "start",
                    },
                )
                self.state.read_agents_from_state()

    def test_create_module_sets_timezone_and_initializes_state(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock(side_effect=set_env_side_effect))
        sys.modules["agent"] = agent_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir), mock.patch.dict(
                os.environ,
                {"TIMEZONE": " Europe/Rome "},
                clear=True,
            ), mock.patch("subprocess.run") as run_command:
                run_action(CREATE_MODULE_ACTION_DIR)
                self.assertTrue(Path(temp_dir, "agents").is_dir())
                self.assertTrue(Path(temp_dir, "secrets.env").is_file())
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

        agent_stub.set_env.assert_called_once_with("TIMEZONE", "Europe/Rome")
        run_command.assert_called_once_with(["runagent", "discover-smarthost"], check=True)

    def test_create_module_rejects_symlinked_state_paths(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock(side_effect=set_env_side_effect))
        sys.modules["agent"] = agent_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir), mock.patch.dict(
                os.environ,
                {"TIMEZONE": "UTC"},
                clear=True,
            ):
                Path("target-dir").mkdir()
                os.symlink("target-dir", "agents")

                with self.assertRaisesRegex(ValueError, "unsafe directory path"):
                    run_action(CREATE_MODULE_ACTION_DIR)
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

    def test_runtime_name_helpers_preserve_split_contract(self):
        self.assertEqual(self.state.service_unit(1), "hermes@1.service")
        self.assertEqual(self.state.dashboard_service_unit(1), "hermes-dashboard@1.service")
        self.assertEqual(self.state.pod_service_unit(1), "hermes-pod@1.service")
        self.assertEqual(self.state.legacy_service_unit(1), "hermes-agent@1.service")
        self.assertEqual(self.state.container_name(1), "hermes-1")
        self.assertEqual(self.state.dashboard_container_name(1), "hermes-dashboard-1")
        self.assertEqual(self.state.pod_name(1), "hermes-pod-1")
        self.assertEqual(self.state.legacy_container_name(1), "hermes-agent-1")
        self.assertEqual(self.state.volume_name(1), "hermes-agent-1-home")
        self.assertEqual(
            self.state.route_instance_name(1, module_id="hermes-agent1"),
            "hermes-agent1-hermes-agent-1",
        )
        self.assertEqual(self.state.route_path(1), "/hermes-1")

    def test_service_templates_keep_runtime_contract(self):
        service_template = SERVICE_TEMPLATE_PATH.read_text(encoding="utf-8")
        dashboard_template = DASHBOARD_SERVICE_TEMPLATE_PATH.read_text(encoding="utf-8")
        pod_template = POD_SERVICE_TEMPLATE_PATH.read_text(encoding="utf-8")

        self.assertIn("Restart=on-failure", service_template)
        self.assertNotIn("Restart=always", service_template)
        self.assertNotIn("EnvironmentFile=-%S/state/hosts", service_template)
        self.assertNotIn("$PODMAN_ADD_HOST_ARGS", service_template)
        self.assertNotIn("--restart=always", service_template)
        self.assertIn("--pod hermes-pod-%i", service_template)
        self.assertIn("--name hermes-%i", service_template)
        self.assertIn("--userns=keep-id", service_template)
        self.assertIn("--volume hermes-agent-%i-home:/opt/data", service_template)
        self.assertNotIn("--volume %S/state/agents/%i/home:/opt/data:Z", service_template)
        self.assertIn("--env-file %S/state/agent_%i.env", service_template)
        self.assertIn("--env-file %S/state/agent_%i_secrets.env", service_template)
        self.assertIn("API_SERVER_ENABLED=true", service_template)
        self.assertIn("gateway run", service_template)
        self.assertNotIn("seed-agent-home", service_template)

        self.assertIn("--name hermes-dashboard-%i", dashboard_template)
        self.assertIn("--pod hermes-pod-%i", dashboard_template)
        self.assertIn("--userns=keep-id", dashboard_template)
        self.assertIn("GATEWAY_HEALTH_URL=http://127.0.0.1:8642", dashboard_template)
        self.assertIn("--volume hermes-agent-%i-home:/opt/data:Z,ro", dashboard_template)
        self.assertIn("dashboard --host 0.0.0.0", dashboard_template)
        self.assertNotIn("--publish ", dashboard_template)

        self.assertIn("Type=oneshot", pod_template)
        self.assertIn("RemainAfterExit=yes", pod_template)
        self.assertIn("AGENT_DASHBOARD_HOST_PORT", pod_template)
        self.assertIn("--name hermes-pod-%i", pod_template)
        self.assertIn("--publish 127.0.0.1:${AGENT_DASHBOARD_HOST_PORT}:9119", pod_template)

    def test_hermes_containerfile_uses_expected_base_image(self):
        containerfile = HERMES_CONTAINERFILE_PATH.read_text(encoding="utf-8")

        self.assertIn("FROM docker.io/nousresearch/hermes-agent:v2026.4.16", containerfile)

    def test_hermes_entrypoint_keeps_absolute_virtualenv_activation(self):
        entrypoint = HERMES_ENTRYPOINT_PATH.read_text(encoding="utf-8")

        self.assertIn('source "${INSTALL_DIR}/.venv/bin/activate"', entrypoint)
        self.assertNotIn("source .venv/bin/activate", entrypoint)

    def test_smarthost_changed_event_restarts_active_primary_units(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            Path("agents/1").mkdir(parents=True)
            Path("agents/2").mkdir(parents=True)

            bin_dir = Path(temp_dir) / "bin"
            bin_dir.mkdir()
            command_log_path = Path(temp_dir) / "commands.log"

            write_executable(
                bin_dir / "runagent",
                "#!/bin/sh\nprintf 'runagent %s\\n' \"$*\" >> \"$TEST_LOG\"\nexit 0\n",
            )
            write_executable(
                bin_dir / "systemctl",
                "#!/bin/sh\nprintf 'systemctl %s\\n' \"$*\" >> \"$TEST_LOG\"\ncase \"$*\" in\n  \"--user is-active --quiet hermes@1.service\")\n    exit 0\n    ;;\n  \"--user is-active --quiet hermes@2.service\")\n    exit 3\n    ;;\n  \"--user restart hermes@1.service\")\n    exit 0\n    ;;\nesac\nexit 1\n",
            )

            subprocess.run(
                [str(SMARTHOST_CHANGED_EVENT_PATH)],
                check=True,
                env={
                    **os.environ,
                    "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
                    "TEST_LOG": str(command_log_path),
                },
            )

            logged_commands = command_log_path.read_text(encoding="utf-8").splitlines()

            self.assertEqual(
                logged_commands,
                [
                    "runagent discover-smarthost",
                    "systemctl --user is-active --quiet hermes@1.service",
                    "systemctl --user restart hermes@1.service",
                    "systemctl --user is-active --quiet hermes@2.service",
                ],
            )
            self.assertNotIn("hermes-agent@", command_log_path.read_text(encoding="utf-8"))

    def test_write_private_textfile_rejects_symlink_target(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            Path("outside.env").write_text("SAFE=1\n", encoding="utf-8")
            os.symlink("outside.env", self.state.agent_envfile(5))

            with self.assertRaisesRegex(ValueError, "unsafe file path"):
                self.state.write_private_textfile(self.state.agent_envfile(5), "AGENT_NAME=Blocked\n")

            self.assertEqual(Path("outside.env").read_text(encoding="utf-8"), "SAFE=1\n")

    def test_sync_agent_runtime_files_writes_public_env_and_secrets(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(1),
                {"id": 1, "name": "Alice User", "role": "developer", "status": "start"},
            )
            write_envfile(
                self.state.ENVIRONMENT_FILE,
                {
                    "TIMEZONE": "UTC",
                    "TCP_PORTS_RANGE": "20001-20030",
                    "BASE_VIRTUALHOST": "agents.example.org",
                    "SMTP_ENABLED": "1",
                    "SMTP_HOST": "smtp.example.org",
                },
            )
            write_envfile(self.state.SHARED_SECRETS_ENVFILE, {"SMTP_PASSWORD": "secret-pass"})

            with mock.patch.object(self.sync.agent, "read_envfile", side_effect=read_envfile, create=True), mock.patch.object(
                self.sync.agent,
                "write_envfile",
                side_effect=write_envfile,
                create=True,
            ):
                self.sync.sync_agent_runtime_files()

            public_env = read_envfile(self.state.agent_envfile(1))
            agent_secrets = read_envfile(self.state.agent_secrets_envfile(1))

            self.assertEqual(public_env["AGENT_NAME"], "Alice User")
            self.assertEqual(public_env["AGENT_ROLE"], "developer")
            self.assertEqual(public_env["SMTP_HOST"], "smtp.example.org")
            self.assertEqual(public_env["AGENT_DASHBOARD_HOST_PORT"], "20001")
            self.assertEqual(
                set(public_env),
                {
                    "AGENT_DASHBOARD_HOST_PORT",
                    "AGENT_ID",
                    "AGENT_NAME",
                    "AGENT_ROLE",
                    "BASE_VIRTUALHOST",
                    "SMTP_ENABLED",
                    "SMTP_HOST",
                    "TIMEZONE",
                    "TZ",
                },
            )
            self.assertEqual(agent_secrets["SMTP_PASSWORD"], "secret-pass")
            self.assertTrue(agent_secrets["HERMES_AGENT_SECRET"])
            self.assertEqual(set(agent_secrets), {"HERMES_AGENT_SECRET", "SMTP_PASSWORD"})
            self.assertEqual(
                sorted(path.name for path in Path(".").glob("agent_1*.env")),
                ["agent_1.env", "agent_1_secrets.env"],
            )
            self.assertFalse((self.state.agent_dir(1) / "home").exists())

    def test_sync_agent_runtime_files_creates_missing_agent_secrets_envfile(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(1),
                {"id": 1, "name": "Alice User", "role": "developer", "status": "start"},
            )
            write_envfile(
                self.state.ENVIRONMENT_FILE,
                {
                    "TIMEZONE": "UTC",
                    "TCP_PORTS_RANGE": "20001-20030",
                    "SMTP_HOST": "smtp.example.org",
                },
            )
            write_envfile(self.state.SHARED_SECRETS_ENVFILE, {"SMTP_PASSWORD": "secret-pass"})

            with mock.patch.object(
                self.sync.agent,
                "read_envfile",
                side_effect=strict_read_envfile,
                create=True,
            ), mock.patch.object(
                self.sync.agent,
                "write_envfile",
                side_effect=write_envfile,
                create=True,
            ):
                self.sync.sync_agent_runtime_files(agent_id=1)

            public_env = read_envfile(self.state.agent_envfile(1))
            agent_secrets = read_envfile(self.state.agent_secrets_envfile(1))

            self.assertEqual(public_env["AGENT_NAME"], "Alice User")
            self.assertEqual(public_env["AGENT_DASHBOARD_HOST_PORT"], "20001")
            self.assertEqual(agent_secrets["SMTP_PASSWORD"], "secret-pass")
            self.assertTrue(agent_secrets["HERMES_AGENT_SECRET"])

    def test_sync_agent_runtime_files_preserves_generated_agent_secret_on_rerun(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(3),
                {"id": 3, "name": "Carol Agent", "role": "researcher", "status": "start"},
            )
            write_envfile(
                self.state.ENVIRONMENT_FILE,
                {"TIMEZONE": "UTC", "TCP_PORTS_RANGE": "20001-20030"},
            )
            write_envfile(self.state.SHARED_SECRETS_ENVFILE, {"SMTP_PASSWORD": "old-pass"})

            with mock.patch.object(
                self.sync.agent,
                "read_envfile",
                side_effect=strict_read_envfile,
                create=True,
            ), mock.patch.object(
                self.sync.agent,
                "write_envfile",
                side_effect=write_envfile,
                create=True,
            ):
                self.sync.sync_agent_runtime_files(agent_id=3)
                first_sync_secrets = read_envfile(self.state.agent_secrets_envfile(3))

                write_envfile(self.state.SHARED_SECRETS_ENVFILE, {"SMTP_PASSWORD": "new-pass"})
                self.sync.sync_agent_runtime_files(agent_id=3)

            agent_secrets = read_envfile(self.state.agent_secrets_envfile(3))
            self.assertEqual(agent_secrets["HERMES_AGENT_SECRET"], first_sync_secrets["HERMES_AGENT_SECRET"])
            self.assertEqual(agent_secrets["SMTP_PASSWORD"], "new-pass")
            self.assertEqual(set(agent_secrets), {"HERMES_AGENT_SECRET", "SMTP_PASSWORD"})

    def test_seed_agent_home_action_uses_public_envfile_and_templates_mount(self):
        with mock.patch("sys.stdin", io.StringIO("{}")):
            seed_action = runpy.run_path(
                str(SEED_AGENT_HOME_ACTION_PATH),
                run_name="seed_agent_home_fixture",
            )

        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            write_envfile(
                self.state.agent_envfile(1),
                {
                    "AGENT_ID": "1",
                    "AGENT_NAME": "Seed Agent",
                    "AGENT_ROLE": "developer",
                },
            )

            request = json.dumps(
                {
                    "agents": [
                        {
                            "id": 1,
                            "name": "Seed Agent",
                            "role": "developer",
                            "status": "start",
                        }
                    ]
                }
            )

            with mock.patch.dict(
                os.environ,
                {"HERMES_AGENT_HERMES_IMAGE": "quay.io/example/hermes:test"},
                clear=False,
            ), mock.patch("sys.stdin", io.StringIO(request)), mock.patch("subprocess.run") as run_command:
                runpy.run_path(str(SEED_AGENT_HOME_ACTION_PATH), run_name="__main__")

            command = run_command.call_args.args[0]
            self.assertEqual(command[:2], ["podman", "run"])
            self.assertIn("--name", command)
            self.assertIn("hermes-agent-seed-1", command)
            self.assertIn("--network=none", command)
            self.assertIn("--user", command)
            self.assertEqual(command[command.index("--user") + 1], "hermes")
            self.assertIn("--entrypoint", command)
            self.assertIn("/bin/sh", command)
            self.assertIn("--env-file", command)
            self.assertIn(str((Path(temp_dir) / "agent_1.env").resolve()), command)
            self.assertNotIn(str((Path(temp_dir) / "agent_1_secrets.env").resolve()), command)
            self.assertIn("hermes-agent-1-home:/opt/data", command)
            self.assertIn(f"{(ROOT / 'imageroot' / 'templates').resolve()}:/templates:ro,Z", command)
            self.assertEqual(command[-2], "-c")
            self.assertEqual(command[-1], seed_action["SEED_SCRIPT"])
            self.assertEqual(run_command.call_args.kwargs, {"check": True})

    def test_seed_agent_home_script_only_creates_missing_files(self):
        with mock.patch("sys.stdin", io.StringIO("{}")):
            seed_action = runpy.run_path(
                str(SEED_AGENT_HOME_ACTION_PATH),
                run_name="seed_agent_home_script_check",
            )

        seed_script = seed_action["SEED_SCRIPT"]

        self.assertIn("ensure_safe_target /opt/data/SOUL.md", seed_script)
        self.assertIn("if [ ! -e /opt/data/SOUL.md ]; then", seed_script)
        self.assertIn("ensure_safe_target /opt/data/.env", seed_script)
        self.assertIn("if [ ! -e /opt/data/.env ]; then", seed_script)

    def test_seed_agent_home_script_preserves_existing_files_on_rerun(self):
        with mock.patch("sys.stdin", io.StringIO("{}")):
            seed_action = runpy.run_path(
                str(SEED_AGENT_HOME_ACTION_PATH),
                run_name="seed_agent_home_script_execution",
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "opt-data"
            data_dir.mkdir()
            seed_script = seed_action["SEED_SCRIPT"].replace("/opt/data", str(data_dir)).replace(
                "/templates",
                str((ROOT / "imageroot" / "templates").resolve()),
            )

            run_seed_script(
                seed_script,
                data_dir,
                agent_id=1,
                agent_name="Seed Agent",
                agent_role="developer",
            )

            self.assertIn("AGENT_NAME=Seed Agent", (data_dir / ".env").read_text(encoding="utf-8"))
            self.assertIn(
                "Your name is Seed Agent, you are an Hermes Agent that runs on NethServer8",
                (data_dir / "SOUL.md").read_text(encoding="utf-8"),
            )

            (data_dir / "SOUL.md").write_text("customized soul\n", encoding="utf-8")
            (data_dir / ".env").write_text("CUSTOM=true\n", encoding="utf-8")

            run_seed_script(
                seed_script,
                data_dir,
                agent_id=1,
                agent_name="Renamed Agent",
                agent_role="marketing",
            )

            self.assertEqual((data_dir / "SOUL.md").read_text(encoding="utf-8"), "customized soul\n")
            self.assertEqual((data_dir / ".env").read_text(encoding="utf-8"), "CUSTOM=true\n")

    def test_seed_agent_home_action_requires_generated_public_envfile(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            request = json.dumps({"agents": [{"id": 1}]})

            with mock.patch.dict(
                os.environ,
                {"HERMES_AGENT_HERMES_IMAGE": "quay.io/example/hermes:test"},
                clear=False,
            ), mock.patch("sys.stdin", io.StringIO(request)), self.assertRaisesRegex(
                ValueError,
                "agent env file not found",
            ):
                runpy.run_path(str(SEED_AGENT_HOME_ACTION_PATH), run_name="__main__")

    def test_persist_shared_env_tracks_previous_lets_encrypt_on_host_change(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock(side_effect=set_env_side_effect))
        setattr(agent_stub, "unset_env", mock.Mock(side_effect=unset_env_side_effect))
        sys.modules["agent"] = agent_stub

        try:
            request = json.dumps(
                {
                    "base_virtualhost": "new.example.org",
                    "lets_encrypt": True,
                    "agents": [],
                }
            )

            with mock.patch.dict(
                os.environ,
                {
                    "TIMEZONE": "UTC",
                    self.state.BASE_VIRTUALHOST_ENV: "old.example.org",
                    self.state.LETS_ENCRYPT_ENV: "true",
                },
                clear=False,
            ), mock.patch("sys.stdin", io.StringIO(request)):
                runpy.run_path(str(PERSIST_SHARED_ENV_PATH), run_name="__main__")

            self.assertIn(
                mock.call(self.state.BASE_VIRTUALHOST_PREVIOUS_ENV, "old.example.org"),
                agent_stub.set_env.call_args_list,
            )
            self.assertIn(
                mock.call(self.state.BASE_VIRTUALHOST_ENV, "new.example.org"),
                agent_stub.set_env.call_args_list,
            )
            self.assertIn(
                mock.call(self.state.LETS_ENCRYPT_PREVIOUS_ENV, "true"),
                agent_stub.set_env.call_args_list,
            )
            self.assertIn(
                mock.call(self.state.LETS_ENCRYPT_ENV, "true"),
                agent_stub.set_env.call_args_list,
            )
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

    def test_reconcile_desired_routes_cleans_up_previous_certificate_on_host_change(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "resolve_agent_id", mock.Mock(return_value="module/traefik1"))
        setattr(agent_stub, "assert_exp", mock.Mock())
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(1),
                    {"id": 1, "name": "Route Agent", "role": "developer", "status": "start"},
                )

                request = json.dumps(
                    {
                        "base_virtualhost": "new.example.org",
                        "agents": [
                            {
                                "id": 1,
                                "name": "Route Agent",
                                "role": "developer",
                                "status": "start",
                            }
                        ],
                    }
                )

                with mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TCP_PORTS_RANGE": "20001-20030",
                        self.state.BASE_VIRTUALHOST_ENV: "new.example.org",
                        self.state.BASE_VIRTUALHOST_PREVIOUS_ENV: "old.example.org",
                        self.state.LETS_ENCRYPT_ENV: "true",
                        self.state.LETS_ENCRYPT_PREVIOUS_ENV: "true",
                    },
                    clear=False,
                ), mock.patch("sys.stdin", io.StringIO(request)):
                    runpy.run_path(str(RECONCILE_DESIRED_ROUTES_PATH), run_name="__main__")

                self.assertEqual(
                    agent_tasks_stub.run.call_args_list,
                    [
                        mock.call(
                            agent_id="module/traefik1",
                            action="delete-route",
                            data={
                                "instance": "hermes-agent1-hermes-agent-1",
                                "lets_encrypt_cleanup": True,
                            },
                        ),
                        mock.call(
                            agent_id="module/traefik1",
                            action="set-route",
                            data={
                                "instance": "hermes-agent1-hermes-agent-1",
                                "url": "http://127.0.0.1:20001",
                                "host": "new.example.org",
                                "path": "/hermes-1",
                                "http2https": True,
                                "lets_encrypt": True,
                                "strip_prefix": True,
                                "headers": {
                                    "request": {
                                        "X-Forwarded-Prefix": "/hermes-1",
                                    }
                                },
                            },
                        ),
                    ],
                )
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

            if original_agent_tasks is not None:
                sys.modules["agent.tasks"] = original_agent_tasks
            elif "agent.tasks" in sys.modules:
                del sys.modules["agent.tasks"]

    def test_reconcile_desired_routes_cleans_up_when_disabling_lets_encrypt(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "resolve_agent_id", mock.Mock(return_value="module/traefik1"))
        setattr(agent_stub, "assert_exp", mock.Mock())
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(1),
                    {"id": 1, "name": "Route Agent", "role": "developer", "status": "start"},
                )

                request = json.dumps(
                    {
                        "base_virtualhost": "agents.example.org",
                        "lets_encrypt": False,
                        "agents": [
                            {
                                "id": 1,
                                "name": "Route Agent",
                                "role": "developer",
                                "status": "start",
                            }
                        ],
                    }
                )

                with mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TCP_PORTS_RANGE": "20001-20030",
                        self.state.BASE_VIRTUALHOST_ENV: "agents.example.org",
                        self.state.LETS_ENCRYPT_ENV: "false",
                        self.state.LETS_ENCRYPT_PREVIOUS_ENV: "true",
                    },
                    clear=False,
                ), mock.patch("sys.stdin", io.StringIO(request)):
                    runpy.run_path(str(RECONCILE_DESIRED_ROUTES_PATH), run_name="__main__")

                agent_tasks_stub.run.assert_called_once_with(
                    agent_id="module/traefik1",
                    action="set-route",
                    data={
                        "instance": "hermes-agent1-hermes-agent-1",
                        "url": "http://127.0.0.1:20001",
                        "host": "agents.example.org",
                        "path": "/hermes-1",
                        "http2https": True,
                        "lets_encrypt": False,
                        "lets_encrypt_cleanup": True,
                        "strip_prefix": True,
                        "headers": {
                            "request": {
                                "X-Forwarded-Prefix": "/hermes-1",
                            }
                        },
                    },
                )
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

            if original_agent_tasks is not None:
                sys.modules["agent.tasks"] = original_agent_tasks
            elif "agent.tasks" in sys.modules:
                del sys.modules["agent.tasks"]

    def test_remove_deleted_routes_cleans_certificate_once_for_last_removed_agent(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "resolve_agent_id", mock.Mock(return_value="module/traefik1"))
        setattr(agent_stub, "assert_exp", mock.Mock())
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(1),
                    {"id": 1, "name": "Old Agent", "role": "developer", "status": "start"},
                )

                with mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        self.state.BASE_VIRTUALHOST_ENV: "agents.example.org",
                        self.state.LETS_ENCRYPT_ENV: "true",
                    },
                    clear=False,
                ), mock.patch("sys.stdin", io.StringIO(json.dumps({"agents": []}))):
                    runpy.run_path(
                        str(CONFIGURE_MODULE_ACTION_DIR / "30remove-deleted-routes"),
                        run_name="__main__",
                    )

                agent_tasks_stub.run.assert_called_once_with(
                    agent_id="module/traefik1",
                    action="delete-route",
                    data={
                        "instance": "hermes-agent1-hermes-agent-1",
                        "lets_encrypt_cleanup": True,
                    },
                )
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

            if original_agent_tasks is not None:
                sys.modules["agent.tasks"] = original_agent_tasks
            elif "agent.tasks" in sys.modules:
                del sys.modules["agent.tasks"]

    def test_sync_agent_runtime_files_preserves_existing_agent_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(3),
                {"id": 3, "name": "Carol Agent", "role": "researcher", "status": "start"},
            )
            write_envfile(
                self.state.ENVIRONMENT_FILE,
                {"TIMEZONE": "UTC", "TCP_PORTS_RANGE": "20001-20030"},
            )
            write_envfile(
                self.state.agent_secrets_envfile(3),
                {
                    "HERMES_AGENT_SECRET": "preserved",
                    "SMTP_PASSWORD": "old-pass",
                },
            )
            write_envfile(self.state.SHARED_SECRETS_ENVFILE, {"SMTP_PASSWORD": "new-pass"})

            with mock.patch.object(self.sync.agent, "read_envfile", side_effect=read_envfile, create=True), mock.patch.object(
                self.sync.agent,
                "write_envfile",
                side_effect=write_envfile,
                create=True,
            ):
                self.sync.sync_agent_runtime_files(agent_id=3)

            agent_secrets = read_envfile(self.state.agent_secrets_envfile(3))
            self.assertEqual(agent_secrets["HERMES_AGENT_SECRET"], "preserved")
            self.assertEqual(agent_secrets["SMTP_PASSWORD"], "new-pass")
            self.assertEqual(set(agent_secrets), {"HERMES_AGENT_SECRET", "SMTP_PASSWORD"})

    def test_ensure_tcp_ports_environment_keeps_existing_valid_range(self):
        allocator = mock.Mock()

        env_patch = self.state.ensure_tcp_ports_environment(
            {
                "TCP_PORT": "20001",
                "TCP_PORTS_RANGE": "20001-20030",
            },
            allocate_ports=allocator,
        )

        self.assertEqual(env_patch, {})
        allocator.assert_not_called()

    def test_ensure_tcp_ports_environment_repairs_missing_tcp_port(self):
        allocator = mock.Mock()

        env_patch = self.state.ensure_tcp_ports_environment(
            {
                "TCP_PORTS_RANGE": "20001-20030",
            },
            allocate_ports=allocator,
        )

        self.assertEqual(env_patch, {"TCP_PORT": "20001"})
        allocator.assert_not_called()

    def test_ensure_tcp_ports_environment_reallocates_missing_range(self):
        allocator = mock.Mock(return_value=(21000, 21029))

        env_patch = self.state.ensure_tcp_ports_environment({}, allocate_ports=allocator)

        self.assertEqual(
            env_patch,
            {
                "TCP_PORT": "21000",
                "TCP_PORTS_RANGE": "21000-21029",
            },
        )
        allocator.assert_called_once_with(self.state.MAX_AGENTS, "tcp")

    def test_update_module_repairs_missing_tcp_ports_range(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "allocate_ports", mock.Mock(return_value=(22000, 22029)))
        setattr(agent_stub, "mset_env", mock.Mock())
        sys.modules["agent"] = agent_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                write_envfile(self.state.ENVIRONMENT_FILE, {"MODULE_ID": "hermes-agent1"})

                runpy.run_path(str(UPDATE_TCP_PORTS_PATH), run_name="__main__")
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

        agent_stub.allocate_ports.assert_called_once_with(self.state.MAX_AGENTS, "tcp")
        agent_stub.mset_env.assert_called_once_with(
            {
                "TCP_PORT": "22000",
                "TCP_PORTS_RANGE": "22000-22029",
            }
        )

    def test_configure_module_reconciles_removed_and_started_agents(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock(side_effect=set_env_side_effect))
        setattr(agent_stub, "unset_env", mock.Mock(side_effect=unset_env_side_effect))
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(2),
                    {"id": 2, "name": "Old Agent", "role": "default", "status": "stop"},
                )
                write_envfile(self.state.agent_envfile(2), {"AGENT_NAME": "Old Agent"})
                write_envfile(
                    self.state.agent_secrets_envfile(2),
                    {"HERMES_AGENT_SECRET": "old-secret"},
                )

                def run_side_effect(command, **kwargs):
                    if command[:2] == ["runagent", "remove-agent-state"]:
                        return emulate_remove_agent_state(command)
                    if command[:2] == ["runagent", "sync-agent-runtime"]:
                        return emulate_sync_agent_runtime(self.sync, command)
                    return types.SimpleNamespace(returncode=0)

                request = json.dumps(
                    {
                        "agents": [
                            {
                                "id": 1,
                                "name": "New Agent",
                                "role": "developer",
                                "status": "start",
                            }
                        ]
                    }
                )

                with mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TIMEZONE": "UTC",
                        "TCP_PORTS_RANGE": "20001-20030",
                        "HERMES_AGENT_HERMES_IMAGE": "quay.io/example/hermes:test",
                    },
                    clear=False,
                ), mock.patch("subprocess.run", side_effect=run_side_effect) as run_command:
                    run_action(CONFIGURE_MODULE_ACTION_DIR, request)

                self.assertEqual(
                    self.state.read_jsonfile(self.state.agent_metadata_path(1)),
                    {"id": 1, "name": "New Agent", "role": "developer", "status": "start"},
                )
                self.assertFalse(self.state.agent_dir(2).exists())
                self.assertFalse(self.state.agent_envfile(2).exists())
                self.assertFalse(self.state.agent_secrets_envfile(2).exists())
                agent_stub.set_env.assert_not_called()
                command_list = [call.args[0] for call in run_command.call_args_list]
                self.assertEqual(
                    command_list[:10],
                    [
                        ["systemctl", "--user", "disable", "--now", "hermes@2.service"],
                        ["systemctl", "--user", "stop", "hermes-pod@2.service"],
                        ["systemctl", "--user", "disable", "--now", "hermes-agent@2.service"],
                        ["podman", "pod", "rm", "--force", "hermes-pod-2"],
                        ["podman", "rm", "--force", "hermes-2"],
                        ["podman", "rm", "--force", "hermes-dashboard-2"],
                        ["podman", "rm", "--force", "hermes-agent-2"],
                        ["runagent", "remove-agent-state", "--agent-id", "2"],
                        ["podman", "volume", "exists", "hermes-agent-2-home"],
                        ["podman", "volume", "rm", "--force", "hermes-agent-2-home"],
                    ],
                )
                self.assertIn(["runagent", "discover-smarthost"], command_list)
                self.assertIn(["runagent", "sync-agent-runtime"], command_list)
                self.assertIn(["systemctl", "--user", "daemon-reload"], command_list)
                self.assertEqual(command_list[-2:], [["systemctl", "--user", "stop", "hermes-pod@1.service"], ["systemctl", "--user", "start", "hermes@1.service"]])
                self.assertIn(["systemctl", "--user", "enable", "hermes@1.service"], command_list)
                self.assertIn(["systemctl", "--user", "stop", "hermes@1.service"], command_list)
                seed_commands = [command for command in command_list if command[:2] == ["podman", "run"]]
                self.assertEqual(len(seed_commands), 1)
                self.assertIn("hermes-agent-seed-1", seed_commands[0])
                self.assertIn(str((Path(temp_dir) / "agent_1.env").resolve()), seed_commands[0])
                self.assertNotIn(str((Path(temp_dir) / "agent_1_secrets.env").resolve()), seed_commands[0])
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

            if original_agent_tasks is not None:
                sys.modules["agent.tasks"] = original_agent_tasks
            elif "agent.tasks" in sys.modules:
                del sys.modules["agent.tasks"]

    def test_configure_module_sets_traefik_routes_for_dashboard(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock(side_effect=set_env_side_effect))
        setattr(agent_stub, "unset_env", mock.Mock(side_effect=unset_env_side_effect))
        setattr(agent_stub, "resolve_agent_id", mock.Mock(return_value="module/traefik1"))
        setattr(agent_stub, "assert_exp", mock.Mock())
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                write_envfile(
                    self.state.ENVIRONMENT_FILE,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TIMEZONE": "UTC",
                        "TCP_PORTS_RANGE": "20001-20030",
                    },
                )

                request = json.dumps(
                    {
                        "base_virtualhost": "agents.example.org",
                        "lets_encrypt": True,
                        "agents": [
                            {
                                "id": 1,
                                "name": "Route Agent",
                                "role": "developer",
                                "status": "start",
                            }
                        ],
                    }
                )

                with mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TIMEZONE": "UTC",
                        "TCP_PORTS_RANGE": "20001-20030",
                        "HERMES_AGENT_HERMES_IMAGE": "quay.io/example/hermes:test",
                    },
                    clear=False,
                ), mock.patch(
                    "subprocess.run",
                    side_effect=lambda command, **kwargs: emulate_sync_agent_runtime(self.sync, command)
                    if command[:2] == ["runagent", "sync-agent-runtime"]
                    else types.SimpleNamespace(returncode=0),
                ):
                    run_action(CONFIGURE_MODULE_ACTION_DIR, request)

                self.assertIn(mock.call("BASE_VIRTUALHOST", "agents.example.org"), agent_stub.set_env.call_args_list)
                self.assertIn(mock.call("LETS_ENCRYPT", "true"), agent_stub.set_env.call_args_list)
                agent_stub.resolve_agent_id.assert_called_once_with("traefik@node")
                agent_tasks_stub.run.assert_called_once_with(
                    agent_id="module/traefik1",
                    action="set-route",
                    data={
                        "instance": "hermes-agent1-hermes-agent-1",
                        "url": "http://127.0.0.1:20001",
                        "host": "agents.example.org",
                        "path": "/hermes-1",
                        "http2https": True,
                        "lets_encrypt": True,
                        "strip_prefix": True,
                        "headers": {
                            "request": {
                                "X-Forwarded-Prefix": "/hermes-1",
                            }
                        },
                    },
                )
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

            if original_agent_tasks is not None:
                sys.modules["agent.tasks"] = original_agent_tasks
            elif "agent.tasks" in sys.modules:
                del sys.modules["agent.tasks"]

    def test_configure_module_with_empty_virtualhost_does_not_require_traefik(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock(side_effect=set_env_side_effect))
        setattr(agent_stub, "unset_env", mock.Mock(side_effect=unset_env_side_effect))
        setattr(agent_stub, "resolve_agent_id", mock.Mock(return_value=None))
        setattr(agent_stub, "assert_exp", mock.Mock())
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                request = json.dumps(
                    {
                        "base_virtualhost": "",
                        "agents": [
                            {
                                "id": 1,
                                "name": "Route Agent",
                                "role": "developer",
                                "status": "start",
                            }
                        ],
                    }
                )

                with mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TIMEZONE": "UTC",
                        "TCP_PORTS_RANGE": "20001-20030",
                        "HERMES_AGENT_HERMES_IMAGE": "quay.io/example/hermes:test",
                    },
                    clear=False,
                ), mock.patch(
                    "subprocess.run",
                    side_effect=lambda command, **kwargs: emulate_sync_agent_runtime(self.sync, command)
                    if command[:2] == ["runagent", "sync-agent-runtime"]
                    else types.SimpleNamespace(returncode=0),
                ):
                    run_action(CONFIGURE_MODULE_ACTION_DIR, request)

                agent_stub.resolve_agent_id.assert_called_once_with("traefik@node")
                agent_tasks_stub.run.assert_not_called()
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

            if original_agent_tasks is not None:
                sys.modules["agent.tasks"] = original_agent_tasks
            elif "agent.tasks" in sys.modules:
                del sys.modules["agent.tasks"]

    def test_configure_module_clearing_host_removes_routes_for_deleted_and_retained_agents(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock(side_effect=set_env_side_effect))
        setattr(agent_stub, "unset_env", mock.Mock(side_effect=unset_env_side_effect))
        setattr(agent_stub, "resolve_agent_id", mock.Mock(return_value="module/traefik1"))
        setattr(agent_stub, "assert_exp", mock.Mock())
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(2),
                    {"id": 2, "name": "Old Agent", "role": "default", "status": "stop"},
                )
                write_envfile(self.state.agent_envfile(2), {"AGENT_NAME": "Old Agent"})
                write_envfile(
                    self.state.agent_secrets_envfile(2),
                    {"HERMES_AGENT_SECRET": "old-secret"},
                )

                def run_side_effect(command, **kwargs):
                    if command[:2] == ["runagent", "remove-agent-state"]:
                        return emulate_remove_agent_state(command)
                    if command[:2] == ["runagent", "sync-agent-runtime"]:
                        return emulate_sync_agent_runtime(self.sync, command)
                    return types.SimpleNamespace(returncode=0)

                request = json.dumps(
                    {
                        "base_virtualhost": "",
                        "agents": [
                            {
                                "id": 1,
                                "name": "New Agent",
                                "role": "developer",
                                "status": "start",
                            }
                        ],
                    }
                )

                with mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TIMEZONE": "UTC",
                        "TCP_PORTS_RANGE": "20001-20030",
                        "BASE_VIRTUALHOST": "agents.example.org",
                        "HERMES_AGENT_HERMES_IMAGE": "quay.io/example/hermes:test",
                    },
                    clear=False,
                ), mock.patch("subprocess.run", side_effect=run_side_effect):
                    run_action(CONFIGURE_MODULE_ACTION_DIR, request)

                self.assertEqual(
                    agent_tasks_stub.run.call_args_list,
                    [
                        mock.call(
                            agent_id="module/traefik1",
                            action="delete-route",
                            data={"instance": "hermes-agent1-hermes-agent-2"},
                        ),
                        mock.call(
                            agent_id="module/traefik1",
                            action="delete-route",
                            data={"instance": "hermes-agent1-hermes-agent-1"},
                        ),
                    ],
                )
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

            if original_agent_tasks is not None:
                sys.modules["agent.tasks"] = original_agent_tasks
            elif "agent.tasks" in sys.modules:
                del sys.modules["agent.tasks"]

    def test_destroy_module_removes_routes_and_runtime_for_known_agent_state(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "resolve_agent_id", mock.Mock(return_value="module/traefik1"))
        setattr(agent_stub, "assert_exp", mock.Mock())
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                write_envfile(
                    self.state.agent_envfile(4),
                    {"AGENT_NAME": "Route Agent"},
                )
                write_envfile(
                    self.state.agent_secrets_envfile(4),
                    {"HERMES_AGENT_SECRET": "persisted-secret"},
                )

                def run_side_effect(command, **kwargs):
                    if command[:2] == ["runagent", "remove-agent-state"]:
                        return emulate_remove_agent_state(command)
                    return types.SimpleNamespace(returncode=0)

                with mock.patch.dict(os.environ, {"MODULE_ID": "hermes-agent1"}, clear=False), mock.patch(
                    "subprocess.run",
                    side_effect=run_side_effect,
                ) as run_command:
                    run_action(DESTROY_MODULE_ACTION_DIR)

                agent_stub.resolve_agent_id.assert_called_once_with("traefik@node")
                agent_tasks_stub.run.assert_called_once_with(
                    agent_id="module/traefik1",
                    action="delete-route",
                    data={"instance": "hermes-agent1-hermes-agent-4"},
                )
                self.assertEqual(
                    run_command.call_args_list,
                    [
                        mock.call(
                            ["systemctl", "--user", "disable", "--now", "hermes@4.service"],
                            check=False,
                        ),
                        mock.call(
                            ["systemctl", "--user", "stop", "hermes-pod@4.service"],
                            check=False,
                        ),
                        mock.call(
                            ["systemctl", "--user", "disable", "--now", "hermes-agent@4.service"],
                            check=False,
                        ),
                        mock.call(["podman", "pod", "rm", "--force", "hermes-pod-4"], check=False),
                        mock.call(["podman", "rm", "--force", "hermes-4"], check=False),
                        mock.call(["podman", "rm", "--force", "hermes-dashboard-4"], check=False),
                        mock.call(["podman", "rm", "--force", "hermes-agent-4"], check=False),
                        mock.call(["runagent", "remove-agent-state", "--agent-id", "4"], check=True),
                        mock.call(["podman", "volume", "exists", "hermes-agent-4-home"], check=False),
                        mock.call(["podman", "volume", "rm", "--force", "hermes-agent-4-home"], check=True),
                    ],
                )
                self.assertFalse(self.state.agent_envfile(4).exists())
                self.assertFalse(self.state.agent_secrets_envfile(4).exists())
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

            if original_agent_tasks is not None:
                sys.modules["agent.tasks"] = original_agent_tasks
            elif "agent.tasks" in sys.modules:
                del sys.modules["agent.tasks"]

    def test_destroy_remove_routes_cleans_certificate_once_when_lets_encrypt_enabled(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "resolve_agent_id", mock.Mock(return_value="module/traefik1"))
        setattr(agent_stub, "assert_exp", mock.Mock())
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(1),
                    {"id": 1, "name": "One Agent", "role": "default", "status": "start"},
                )
                write_envfile(self.state.agent_envfile(2), {"AGENT_NAME": "Two Agent"})

                with mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        self.state.LETS_ENCRYPT_ENV: "true",
                    },
                    clear=False,
                ), mock.patch("sys.stdin", io.StringIO("{}")):
                    runpy.run_path(str(DESTROY_REMOVE_ROUTES_PATH), run_name="__main__")

                self.assertEqual(
                    agent_tasks_stub.run.call_args_list,
                    [
                        mock.call(
                            agent_id="module/traefik1",
                            action="delete-route",
                            data={
                                "instance": "hermes-agent1-hermes-agent-1",
                                "lets_encrypt_cleanup": True,
                            },
                        ),
                        mock.call(
                            agent_id="module/traefik1",
                            action="delete-route",
                            data={"instance": "hermes-agent1-hermes-agent-2"},
                        ),
                    ],
                )
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

            if original_agent_tasks is not None:
                sys.modules["agent.tasks"] = original_agent_tasks
            elif "agent.tasks" in sys.modules:
                del sys.modules["agent.tasks"]

    def test_get_configuration_returns_desired_state_only(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(1),
                {"id": 1, "name": "Runtime Agent", "role": "developer", "status": "stop"},
            )
            stdout = io.StringIO()

            with mock.patch.dict(
                os.environ,
                {
                    self.state.BASE_VIRTUALHOST_ENV: "agents.example.org",
                    self.state.LETS_ENCRYPT_ENV: "true",
                },
                clear=False,
            ), mock.patch("sys.stdout", stdout):
                runpy.run_path(str(GET_CONFIGURATION_PATH), run_name="__main__")

            self.assertEqual(
                json.loads(stdout.getvalue()),
                {
                    "base_virtualhost": "agents.example.org",
                    "lets_encrypt": True,
                    "agents": [
                        {
                            "id": 1,
                            "name": "Runtime Agent",
                            "role": "developer",
                            "status": "stop",
                        }
                    ]
                },
            )

    def test_get_agent_runtime_reports_actual_runtime_status(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(1),
                {"id": 1, "name": "Runtime Agent", "role": "developer", "status": "stop"},
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdin", io.StringIO("{}")), mock.patch("sys.stdout", stdout), mock.patch(
                "subprocess.run",
                return_value=types.SimpleNamespace(returncode=0),
            ):
                runpy.run_path(str(GET_AGENT_RUNTIME_PATH), run_name="__main__")

            self.assertEqual(
                json.loads(stdout.getvalue()),
                {
                    "agents": [
                        {
                            "id": 1,
                            "runtime_status": "start",
                        }
                    ]
                },
            )

    def test_list_known_agent_ids_scans_metadata_and_generated_files(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(1),
                {"id": 1, "name": "One Agent", "role": "default", "status": "start"},
            )
            write_envfile(self.state.agent_envfile(2), {"AGENT_NAME": "Two Agent"})
            write_envfile(self.state.agent_secrets_envfile(3), {"HERMES_AGENT_SECRET": "secret"})

            self.assertEqual(self.state.list_known_agent_ids(), [1, 2, 3])

    def test_list_known_agent_ids_ignores_out_of_range_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.ensure_private_directory(self.state.agent_dir(31))
            write_envfile(self.state.agent_envfile(32), {"AGENT_NAME": "Ignored Agent"})
            write_envfile(self.state.agent_secrets_envfile(0), {"HERMES_AGENT_SECRET": "ignored"})

            self.assertEqual(self.state.list_known_agent_ids(), [])

    def test_remove_agent_state_rejects_out_of_range_agent_id(self):
        original_argv = sys.argv[:]
        try:
            sys.argv[:] = [str(REMOVE_AGENT_STATE_PATH), "--agent-id", "31"]
            with self.assertRaises(SystemExit) as exit_error, mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
                runpy.run_path(str(REMOVE_AGENT_STATE_PATH), run_name="__main__")

            self.assertEqual(exit_error.exception.code, 2)
            self.assertIn("agent id must be between 1 and 30", stderr.getvalue())
        finally:
            sys.argv[:] = original_argv

    def test_remove_agent_state_keeps_state_when_volume_cleanup_fails(self):
        original_argv = sys.argv[:]
        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.ensure_private_directory(self.state.agent_dir(4))
                write_envfile(self.state.agent_envfile(4), {"AGENT_NAME": "Four Agent"})
                write_envfile(self.state.agent_secrets_envfile(4), {"HERMES_AGENT_SECRET": "secret"})

                def run_side_effect(command, check=False, **kwargs):
                    if command == ["podman", "volume", "exists", "hermes-agent-4-home"]:
                        return types.SimpleNamespace(returncode=0)
                    if command == ["podman", "volume", "rm", "--force", "hermes-agent-4-home"]:
                        raise subprocess.CalledProcessError(returncode=125, cmd=command)
                    return types.SimpleNamespace(returncode=0)

                sys.argv[:] = [str(REMOVE_AGENT_STATE_PATH), "--agent-id", "4"]
                with self.assertRaises(subprocess.CalledProcessError), mock.patch(
                    "subprocess.run",
                    side_effect=run_side_effect,
                ):
                    runpy.run_path(str(REMOVE_AGENT_STATE_PATH), run_name="__main__")

                self.assertTrue(self.state.agent_envfile(4).exists())
                self.assertTrue(self.state.agent_secrets_envfile(4).exists())
                self.assertTrue(self.state.agent_dir(4).exists())
        finally:
            sys.argv[:] = original_argv

    def test_configure_module_validation_rejects_non_ascii_names(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_status", mock.Mock())
        sys.modules["agent"] = agent_stub

        try:
            stdout = io.StringIO()
            with mock.patch(
                "sys.stdin",
                io.StringIO(
                    json.dumps(
                        {
                            "agents": [
                                {
                                    "id": 1,
                                    "name": "Jörg",
                                    "role": "developer",
                                    "status": "start",
                                }
                            ]
                        }
                    )
                ),
            ), mock.patch("sys.stdout", stdout), self.assertRaises(SystemExit) as exit_error:
                runpy.run_path(
                    str(CONFIGURE_MODULE_ACTION_DIR / "10validate-input"),
                    run_name="__main__",
                )

            self.assertEqual(exit_error.exception.code, 2)
            self.assertEqual(
                json.loads(stdout.getvalue()),
                [
                    {
                        "field": "agents[0].name",
                        "parameter": "agents",
                        "value": "J\u00f6rg",
                        "error": "agent_name_invalid",
                    }
                ],
            )
            agent_stub.set_status.assert_called_once_with("validation-failed")
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

    def test_configure_module_validation_rejects_non_boolean_lets_encrypt(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_status", mock.Mock())
        sys.modules["agent"] = agent_stub

        try:
            stdout = io.StringIO()
            with mock.patch(
                "sys.stdin",
                io.StringIO(json.dumps({"lets_encrypt": "yes", "agents": []})),
            ), mock.patch("sys.stdout", stdout), self.assertRaises(SystemExit) as exit_error:
                runpy.run_path(
                    str(CONFIGURE_MODULE_ACTION_DIR / "10validate-input"),
                    run_name="__main__",
                )

            self.assertEqual(exit_error.exception.code, 2)
            self.assertEqual(
                json.loads(stdout.getvalue()),
                [
                    {
                        "field": "lets_encrypt",
                        "parameter": "lets_encrypt",
                        "value": "yes",
                        "error": "lets_encrypt_invalid",
                    }
                ],
            )
            agent_stub.set_status.assert_called_once_with("validation-failed")
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

    def test_sync_agent_runtime_files_requires_existing_agent(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            with mock.patch.object(self.sync.agent, "read_envfile", side_effect=read_envfile, create=True), mock.patch.object(
                self.sync.agent,
                "write_envfile",
                side_effect=write_envfile,
                create=True,
            ), self.assertRaisesRegex(ValueError, "agent 99 not found"):
                self.sync.sync_agent_runtime_files(agent_id=99)
