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
HOME_SEED_MODULE_PATH = ROOT / "imageroot" / "pypkg" / "hermes_agent_home_seed.py"
SYNC_PATH = ROOT / "imageroot" / "bin" / "sync-agent-runtime"
SEED_HOME_PATH = ROOT / "imageroot" / "bin" / "seed-agent-home"
SERVICE_TEMPLATE_PATH = ROOT / "imageroot" / "systemd" / "user" / "hermes-agent@.service"
HERMES_CONTAINERFILE_PATH = ROOT / "containers" / "hermes" / "Containerfile"
CREATE_MODULE_PATH = ROOT / "imageroot" / "actions" / "create-module" / "20create"
CONFIGURE_MODULE_PATH = ROOT / "imageroot" / "actions" / "configure-module" / "20configure"
DESTROY_MODULE_PATH = ROOT / "imageroot" / "actions" / "destroy-module" / "20destroy"
GET_CONFIGURATION_PATH = ROOT / "imageroot" / "actions" / "get-configuration" / "20read"
UPDATE_TCP_PORTS_PATH = ROOT / "imageroot" / "update-module.d" / "10ensure_tcp_ports"


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


def write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


class HermesModuleStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = load_module(STATE_PATH, "hermes_agent_state")
        cls.home_seed = load_module(HOME_SEED_MODULE_PATH, "hermes_agent_home_seed")
        cls.sync = load_module(SYNC_PATH, "sync_agent_runtime_under_test")

    def test_validate_agents_accepts_supported_roles(self):
        for role in self.state.ALLOWED_ROLES:
            with self.subTest(role=role):
                agents = self.state.validate_agents(
                    [
                        {
                            "id": 1,
                            "name": "Valid Name",
                            "role": role,
                            "status": "start",
                        }
                    ]
                )

                self.assertEqual(agents[0]["role"], role)

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

    def test_validate_agents_rejects_unexpected_fields(self):
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            self.state.validate_agents(
                [
                    {
                        "id": 1,
                        "name": "Valid Name",
                        "role": "default",
                        "status": "start",
                        "use_default_gateway_for_llm": True,
                    }
                ]
            )

    def test_validate_agents_rejects_invalid_id(self):
        with self.assertRaisesRegex(ValueError, "invalid id"):
            self.state.validate_agents(
                [
                    {
                        "id": 0,
                        "name": "Valid Name",
                        "role": "default",
                        "status": "start",
                    }
                ]
            )

    def test_validate_agents_rejects_id_above_supported_limit(self):
        with self.assertRaisesRegex(ValueError, "invalid id"):
            self.state.validate_agents(
                [
                    {
                        "id": 31,
                        "name": "Valid Name",
                        "role": "default",
                        "status": "start",
                    }
                ]
            )

    def test_create_module_sets_timezone_and_initializes_state(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock())
        sys.modules["agent"] = agent_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir), mock.patch.dict(
                os.environ,
                {"TIMEZONE": " Europe/Rome "},
                clear=True,
            ), mock.patch("sys.stdin", io.StringIO("{}")), mock.patch("subprocess.run") as run_command:
                runpy.run_path(str(CREATE_MODULE_PATH), run_name="__main__")
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
        setattr(agent_stub, "set_env", mock.Mock())
        sys.modules["agent"] = agent_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir), mock.patch.dict(
                os.environ,
                {"TIMEZONE": "UTC"},
                clear=True,
            ), mock.patch("sys.stdin", io.StringIO("{}")):
                Path("target-dir").mkdir()
                os.symlink("target-dir", "agents")

                with self.assertRaisesRegex(ValueError, "unsafe directory path"):
                    runpy.run_path(str(CREATE_MODULE_PATH), run_name="__main__")
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

    def test_service_template_does_not_load_removed_hosts_envfile(self):
        service_template = SERVICE_TEMPLATE_PATH.read_text(encoding="utf-8")

        self.assertIn("Restart=on-failure", service_template)
        self.assertNotIn("Restart=always", service_template)
        self.assertNotIn("EnvironmentFile=-%S/state/hosts", service_template)
        self.assertNotIn("$PODMAN_ADD_HOST_ARGS", service_template)
        self.assertNotIn("--restart=always", service_template)
        self.assertNotIn("--pod ", service_template)
        self.assertIn("AGENT_DASHBOARD_HOST_PORT", service_template)
        self.assertIn("--name hermes-agent-%i", service_template)
        self.assertIn("--userns=keep-id", service_template)
        self.assertIn("--volume hermes-agent-%i-home:/opt/data", service_template)
        self.assertNotIn("--volume %S/state/agents/%i/home:/opt/data:Z", service_template)
        self.assertIn("--env-file %S/state/agent_%i.env", service_template)
        self.assertIn("--env-file %S/state/agent_%i_secrets.env", service_template)
        self.assertIn("ExecStartPost=/usr/local/bin/runagent seed-agent-home --agent-id %i", service_template)

    def test_hermes_containerfile_uses_expected_base_image(self):
        containerfile = HERMES_CONTAINERFILE_PATH.read_text(encoding="utf-8")

        self.assertIn("FROM docker.io/nousresearch/hermes-agent:v2026.4.16", containerfile)

    def test_write_envfile_rejects_symlink_target(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            Path("outside.env").write_text("SAFE=1\n", encoding="utf-8")
            os.symlink("outside.env", self.state.agent_envfile(5))

            with self.assertRaisesRegex(ValueError, "unsafe file path"):
                self.state.write_envfile(self.state.agent_envfile(5), {"AGENT_NAME": "Blocked"})

            self.assertEqual(Path("outside.env").read_text(encoding="utf-8"), "SAFE=1\n")

    def test_sync_agent_runtime_files_writes_public_env_and_secrets(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(1),
                {"id": 1, "name": "Alice User", "role": "developer", "status": "start"},
            )
            self.state.write_envfile(
                self.state.ENVIRONMENT_FILE,
                {
                    "TIMEZONE": "UTC",
                    "TCP_PORTS_RANGE": "20001-20030",
                    "BASE_VIRTUALHOST": "agents.example.org",
                    "SMTP_ENABLED": "1",
                    "SMTP_HOST": "smtp.example.org",
                },
            )
            self.state.write_envfile(self.state.SHARED_SECRETS_ENVFILE, {"SMTP_PASSWORD": "secret-pass"})

            self.sync.sync_agent_runtime_files()

            public_env = self.state.read_envfile(self.state.agent_envfile(1))
            agent_secrets = self.state.read_envfile(self.state.agent_secrets_envfile(1))

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

    def test_sync_seeded_home_creates_managed_files_and_state(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            home_dir = Path("home")
            agent_data = {"id": 2, "name": "Bob Agent", "role": "marketing", "status": "stop"}

            changed = self.home_seed.sync_seeded_home(
                home_dir,
                agent_data,
            )

            soul_path = home_dir / "SOUL.md"
            home_env_path = home_dir / ".env"
            state_path = self.home_seed.home_seed_state_path(home_dir)
            desired_entries = self.home_seed.build_desired_seed_entries(agent_data)

            self.assertTrue(changed)
            self.assertEqual(
                soul_path.read_text(encoding="utf-8"),
                self.home_seed.render_seed_entry("SOUL.md", desired_entries["SOUL.md"]),
            )
            self.assertEqual(
                home_env_path.read_text(encoding="utf-8"),
                self.home_seed.render_seed_entry(".env", desired_entries[".env"]),
            )
            self.assertEqual(set(self.state.read_jsonfile(state_path)["files"]), {"SOUL.md", ".env"})

    def test_sync_seeded_home_preserves_existing_home_files_without_state(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            home_dir = Path("home")
            home_dir.mkdir()
            soul_path = home_dir / "SOUL.md"
            home_env_path = home_dir / ".env"
            soul_path.write_text("custom soul\n", encoding="utf-8")
            home_env_path.write_text("CUSTOM=true\n", encoding="utf-8")

            changed = self.home_seed.sync_seeded_home(
                home_dir,
                {"id": 2, "name": "Bob Agent", "role": "marketing", "status": "stop"},
            )

            self.assertFalse(changed)
            self.assertEqual(soul_path.read_text(encoding="utf-8"), "custom soul\n")
            self.assertEqual(home_env_path.read_text(encoding="utf-8"), "CUSTOM=true\n")

    def test_sync_seeded_home_updates_managed_files_after_agent_edit(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            home_dir = Path("home")

            self.home_seed.sync_seeded_home(
                home_dir,
                {"id": 2, "name": "Bob Agent", "role": "marketing", "status": "start"},
            )

            changed = self.home_seed.sync_seeded_home(
                home_dir,
                {"id": 2, "name": "Bob Renamed", "role": "business_consultant", "status": "start"},
            )

            soul_path = home_dir / "SOUL.md"
            home_env_path = home_dir / ".env"

            self.assertTrue(changed)
            self.assertIn(
                "Your name is Bob Renamed, you are an Hermes Agent that runs on NethServer8",
                soul_path.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "You are a business consultant who frames problems cleanly and turns ambiguity into decisions, priorities, and tradeoffs.",
                soul_path.read_text(encoding="utf-8"),
            )
            self.assertIn("AGENT_NAME=Bob Renamed", home_env_path.read_text(encoding="utf-8"))
            self.assertIn(
                "AGENT_ROLE=business_consultant",
                home_env_path.read_text(encoding="utf-8"),
            )

    def test_sync_seeded_home_preserves_customized_files_after_agent_edit(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            home_dir = Path("home")

            self.home_seed.sync_seeded_home(
                home_dir,
                {"id": 2, "name": "Bob Agent", "role": "marketing", "status": "start"},
            )

            soul_path = home_dir / "SOUL.md"
            home_env_path = home_dir / ".env"
            soul_path.write_text("customized soul\n", encoding="utf-8")
            home_env_path.write_text("CUSTOM=true\n", encoding="utf-8")

            changed = self.home_seed.sync_seeded_home(
                home_dir,
                {"id": 2, "name": "Bob Renamed", "role": "business_consultant", "status": "start"},
            )

            self.assertFalse(changed)
            self.assertEqual(soul_path.read_text(encoding="utf-8"), "customized soul\n")
            self.assertEqual(home_env_path.read_text(encoding="utf-8"), "CUSTOM=true\n")

    def test_sync_seeded_home_replaces_symlinked_seed_file(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            home_dir = Path("home")
            home_dir.mkdir()

            self.home_seed.sync_seeded_home(
                home_dir,
                {"id": 4, "name": "Dana Agent", "role": "sales", "status": "start"},
            )
            soul_path = home_dir / "SOUL.md"
            soul_path.unlink()
            target_path = home_dir / "outside.txt"
            target_path.write_text("do not overwrite\n", encoding="utf-8")
            os.symlink(target_path, soul_path)

            changed = self.home_seed.sync_seeded_home(
                home_dir,
                {"id": 4, "name": "Dana Agent", "role": "sales", "status": "start"},
            )

            self.assertTrue(changed)
            self.assertFalse(soul_path.is_symlink())
            self.assertIn(
                "Your name is Dana Agent, you are an Hermes Agent that runs on NethServer8",
                soul_path.read_text(encoding="utf-8"),
            )
            self.assertEqual(target_path.read_text(encoding="utf-8"), "do not overwrite\n")

    def test_sync_seeded_home_uses_explicit_state_when_volume_state_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            home_dir = Path("home")
            state_path = Path("agents") / "8" / self.state.HOME_VOLUME_STATE_FILE

            self.home_seed.sync_seeded_home(
                home_dir,
                {"id": 8, "name": "Volume Agent", "role": "developer", "status": "start"},
                state_path=state_path,
            )

            self.home_seed.home_seed_state_path(home_dir).unlink()

            changed = self.home_seed.sync_seeded_home(
                home_dir,
                {"id": 8, "name": "Volume Renamed", "role": "researcher", "status": "start"},
                state_path=state_path,
            )

            self.assertTrue(changed)
            self.assertIn(
                "Your name is Volume Renamed, you are an Hermes Agent that runs on NethServer8",
                (home_dir / "SOUL.md").read_text(encoding="utf-8"),
            )

    def test_sync_seeded_home_replaces_symlinked_state_file(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            home_dir = Path("home")
            home_dir.mkdir()
            state_path = self.home_seed.home_seed_state_path(home_dir)
            outside_state = Path("outside-state.json")
            outside_state.write_text('{"files":{"SOUL.md":{"template_role":"sales"}}}\n', encoding="utf-8")
            os.symlink(outside_state, state_path)

            changed = self.home_seed.sync_seeded_home(
                home_dir,
                {"id": 5, "name": "Erin Agent", "role": "sales", "status": "start"},
            )

            self.assertTrue(changed)
            self.assertFalse(state_path.is_symlink())
            self.assertEqual(
                self.state.read_jsonfile(state_path),
                {"files": self.home_seed.build_desired_seed_entries({"id": 5, "name": "Erin Agent", "role": "sales", "status": "start"})},
            )
            self.assertEqual(
                outside_state.read_text(encoding="utf-8"),
                '{"files":{"SOUL.md":{"template_role":"sales"}}}\n',
            )

    def test_sync_seeded_home_recovers_from_invalid_state_json(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            home_dir = Path("home")
            home_dir.mkdir()
            state_path = self.home_seed.home_seed_state_path(home_dir)
            state_path.write_text("not-json\n", encoding="utf-8")

            changed = self.home_seed.sync_seeded_home(
                home_dir,
                {"id": 6, "name": "Frank Agent", "role": "developer", "status": "start"},
            )

            self.assertTrue(changed)
            self.assertEqual(
                self.state.read_jsonfile(state_path),
                {"files": self.home_seed.build_desired_seed_entries({"id": 6, "name": "Frank Agent", "role": "developer", "status": "start"})},
            )

    def test_seed_agent_home_schedules_restart_only_when_files_change(self):
        original_argv = sys.argv[:]

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                home_dir = Path(temp_dir) / "volume"
                home_dir.mkdir()
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(7),
                    {"id": 7, "name": "Restart Agent", "role": "developer", "status": "start"},
                )

                inspect_response = types.SimpleNamespace(returncode=0, stdout=f"{home_dir}\n")
                ok_response = types.SimpleNamespace(returncode=0, stdout="")

                with mock.patch.object(
                    sys,
                    "argv",
                    [str(SEED_HOME_PATH), "--agent-id", "7"],
                ), mock.patch("subprocess.run", side_effect=[inspect_response, ok_response]) as run_command, mock.patch(
                    "sys.stdout",
                    new_callable=io.StringIO,
                ) as stdout:
                    with self.assertRaises(SystemExit) as exit_error:
                        runpy.run_path(str(SEED_HOME_PATH), run_name="__main__")

                self.assertEqual(exit_error.exception.code, 0)

                self.assertEqual(stdout.getvalue().strip(), "changed")
                self.assertEqual(
                    run_command.call_args_list,
                    [
                        mock.call(
                            ["podman", "volume", "inspect", "--format", "{{.Mountpoint}}", "hermes-agent-7-home"],
                            check=True,
                            capture_output=True,
                            text=True,
                        ),
                        mock.call(
                            [
                                "systemd-run",
                                "--user",
                                "--collect",
                                "--no-block",
                                "--quiet",
                                "/usr/bin/systemctl",
                                "--user",
                                "restart",
                                "hermes-agent@7.service",
                            ],
                            check=True,
                        ),
                    ],
                )

                with mock.patch.object(
                    sys,
                    "argv",
                    [str(SEED_HOME_PATH), "--agent-id", "7"],
                ), mock.patch("subprocess.run", return_value=inspect_response) as run_command, mock.patch(
                    "sys.stdout",
                    new_callable=io.StringIO,
                ) as stdout:
                    with self.assertRaises(SystemExit) as exit_error:
                        runpy.run_path(str(SEED_HOME_PATH), run_name="__main__")

                self.assertEqual(exit_error.exception.code, 0)

                self.assertEqual(stdout.getvalue().strip(), "unchanged")
                run_command.assert_called_once_with(
                    ["podman", "volume", "inspect", "--format", "{{.Mountpoint}}", "hermes-agent-7-home"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
        finally:
            sys.argv[:] = original_argv

    def test_sync_agent_runtime_files_preserves_existing_agent_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(3),
                {"id": 3, "name": "Carol Agent", "role": "researcher", "status": "start"},
            )
            self.state.write_envfile(
                self.state.ENVIRONMENT_FILE,
                {"TIMEZONE": "UTC", "TCP_PORTS_RANGE": "20001-20030"},
            )
            self.state.write_envfile(
                self.state.agent_secrets_envfile(3),
                {
                    "HERMES_AGENT_SECRET": "preserved",
                    "SMTP_PASSWORD": "old-pass",
                },
            )
            self.state.write_envfile(self.state.SHARED_SECRETS_ENVFILE, {"SMTP_PASSWORD": "new-pass"})

            self.sync.sync_agent_runtime_files(agent_id=3)

            agent_secrets = self.state.read_envfile(self.state.agent_secrets_envfile(3))
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
                self.state.write_envfile(self.state.ENVIRONMENT_FILE, {"MODULE_ID": "hermes-agent1"})

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
        setattr(agent_stub, "set_env", mock.Mock())
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    self.state.agent_metadata_path(2),
                    {"id": 2, "name": "Old Agent", "role": "default", "status": "stop"},
                )
                self.state.write_envfile(self.state.agent_envfile(2), {"AGENT_NAME": "Old Agent"})
                self.state.write_envfile(
                    self.state.agent_secrets_envfile(2),
                    {"HERMES_AGENT_SECRET": "old-secret"},
                )

                with mock.patch("sys.stdin", io.StringIO(json.dumps({
                    "agents": [
                        {
                            "id": 1,
                            "name": "New Agent",
                            "role": "developer",
                            "status": "start",
                        }
                    ]
                }))), mock.patch("subprocess.run") as run_command:
                    runpy.run_path(str(CONFIGURE_MODULE_PATH), run_name="__main__")

                self.assertEqual(
                    self.state.read_jsonfile(self.state.agent_metadata_path(1)),
                    {"id": 1, "name": "New Agent", "role": "developer", "status": "start"},
                )
                self.assertFalse(self.state.agent_dir(2).exists())
                self.assertFalse(self.state.agent_envfile(2).exists())
                self.assertFalse(self.state.agent_secrets_envfile(2).exists())
                agent_stub.set_env.assert_called_once_with(self.state.TIMEZONE_ENV, self.state.TIMEZONE_DEFAULT)
                self.assertEqual(
                    run_command.call_args_list,
                    [
                        mock.call(
                            ["systemctl", "--user", "disable", "--now", "hermes-agent@2.service"],
                            check=False,
                        ),
                        mock.call(["podman", "rm", "--force", "hermes-agent-2"], check=False),
                        mock.call(["podman", "volume", "rm", "--force", "hermes-agent-2-home"], check=False),
                        mock.call(["runagent", "discover-smarthost"], check=True),
                        mock.call(["runagent", "sync-agent-runtime"], check=True),
                        mock.call(["systemctl", "--user", "daemon-reload"], check=True),
                        mock.call(["systemctl", "--user", "enable", "hermes-agent@1.service"], check=True),
                        mock.call(["systemctl", "--user", "stop", "hermes-agent@1.service"], check=False),
                        mock.call(["systemctl", "--user", "start", "hermes-agent@1.service"], check=True),
                    ],
                )
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

    def test_configure_module_sets_traefik_routes_for_dashboard(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock())
        setattr(agent_stub, "resolve_agent_id", mock.Mock(return_value="module/traefik1"))
        setattr(agent_stub, "assert_exp", mock.Mock())
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_envfile(
                    self.state.ENVIRONMENT_FILE,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TIMEZONE": "UTC",
                        "TCP_PORTS_RANGE": "20001-20030",
                    },
                )

                with mock.patch.dict(os.environ, {"MODULE_ID": "hermes-agent1"}, clear=False), mock.patch(
                    "sys.stdin",
                    io.StringIO(
                        json.dumps(
                            {
                                "base_virtualhost": "agents.example.org",
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
                    ),
                ), mock.patch("subprocess.run"):
                    runpy.run_path(str(CONFIGURE_MODULE_PATH), run_name="__main__")

                agent_stub.set_env.assert_called_once_with("BASE_VIRTUALHOST", "agents.example.org")
                agent_stub.resolve_agent_id.assert_called_once_with("traefik@node")
                agent_tasks_stub.run.assert_called_once_with(
                    agent_id="module/traefik1",
                    action="set-route",
                    data={
                        "instance": "hermes-agent1-hermes-agent-1",
                        "url": "http://127.0.0.1:20001",
                        "host": "agents.example.org",
                        "path": "/hermes-agent-1",
                        "http2https": True,
                        "lets_encrypt": False,
                        "strip_prefix": True,
                        "headers": {
                            "request": {
                                "X-Forwarded-Prefix": "/hermes-agent-1",
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
                self.state.write_envfile(
                    self.state.agent_envfile(4),
                    {"AGENT_NAME": "Route Agent"},
                )
                self.state.write_envfile(
                    self.state.agent_secrets_envfile(4),
                    {"HERMES_AGENT_SECRET": "persisted-secret"},
                )

                with mock.patch.dict(os.environ, {"MODULE_ID": "hermes-agent1"}, clear=False), mock.patch(
                    "sys.stdin", io.StringIO("{}")
                ), mock.patch("subprocess.run") as run_command:
                    runpy.run_path(str(DESTROY_MODULE_PATH), run_name="__main__")

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
                            ["systemctl", "--user", "disable", "--now", "hermes-agent@4.service"],
                            check=False,
                        ),
                        mock.call(["podman", "rm", "--force", "hermes-agent-4"], check=False),
                        mock.call(["podman", "volume", "rm", "--force", "hermes-agent-4-home"], check=False),
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

    def test_get_configuration_reports_actual_runtime_status_separately(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(1),
                {"id": 1, "name": "Runtime Agent", "role": "developer", "status": "stop"},
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout), mock.patch(
                "subprocess.run",
                return_value=types.SimpleNamespace(returncode=0),
            ):
                runpy.run_path(str(GET_CONFIGURATION_PATH), run_name="__main__")

            self.assertEqual(
                json.loads(stdout.getvalue()),
                {
                    "base_virtualhost": "",
                    "agents": [
                        {
                            "id": 1,
                            "name": "Runtime Agent",
                            "role": "developer",
                            "status": "stop",
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
            self.state.write_envfile(self.state.agent_envfile(2), {"AGENT_NAME": "Two Agent"})
            self.state.write_envfile(self.state.agent_secrets_envfile(3), {"HERMES_AGENT_SECRET": "secret"})

            self.assertEqual(self.state.list_known_agent_ids(), [1, 2, 3])

    def test_actual_agent_status_uses_systemctl_result(self):
        with mock.patch.object(
            self.state.subprocess,
            "run",
            return_value=types.SimpleNamespace(returncode=0),
        ) as run_command:
            status = self.state.actual_agent_status(7)

        self.assertEqual(status, "start")
        run_command.assert_called_once()

    def test_sync_agent_runtime_files_requires_existing_agent(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            with self.assertRaisesRegex(ValueError, "agent 99 not found"):
                self.sync.sync_agent_runtime_files(agent_id=99)
