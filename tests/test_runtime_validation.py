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
CREATE_MODULE_PATH = ROOT / "imageroot" / "actions" / "create-module" / "20create"
CONFIGURE_MODULE_PATH = ROOT / "imageroot" / "actions" / "configure-module" / "20configure"
CONFIGURE_HOSTS_PATH = ROOT / "imageroot" / "actions" / "configure-module" / "40hosts"
GET_CONFIGURATION_PATH = ROOT / "imageroot" / "actions" / "get-configuration" / "20read"


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
        cls.state = load_module(STATE_PATH, "hermes_agent_state_under_test")
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

    def test_write_envfile_rejects_symlink_target(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            Path("outside.env").write_text("SAFE=1\n", encoding="utf-8")
            os.symlink("outside.env", self.state.agent_envfile(5))

            with self.assertRaisesRegex(ValueError, "unsafe file path"):
                self.state.write_envfile(self.state.agent_envfile(5), {"AGENT_NAME": "Blocked"})

            self.assertEqual(Path("outside.env").read_text(encoding="utf-8"), "SAFE=1\n")

    def test_sync_agent_runtime_files_seeds_home_and_env_files(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(1),
                {"id": 1, "name": "Alice User", "role": "developer", "status": "start"},
            )
            self.state.write_envfile(
                self.state.ENVIRONMENT_FILE,
                {
                    "TIMEZONE": "UTC",
                    "SMTP_ENABLED": "1",
                    "SMTP_HOST": "smtp.example.org",
                },
            )
            self.state.write_envfile(self.state.SHARED_SECRETS_ENVFILE, {"SMTP_PASSWORD": "secret-pass"})

            self.sync.sync_agent_runtime_files()

            public_env = self.state.read_envfile(self.state.agent_envfile(1))
            agent_secrets = self.state.read_envfile(self.state.agent_secrets_envfile(1))
            soul_path = self.state.agent_home_dir(1) / "SOUL.md"
            home_env_path = self.state.agent_home_dir(1) / ".env"

            self.assertEqual(public_env["AGENT_NAME"], "Alice User")
            self.assertEqual(public_env["AGENT_ROLE"], "developer")
            self.assertEqual(public_env["SMTP_HOST"], "smtp.example.org")
            self.assertEqual(agent_secrets["SMTP_PASSWORD"], "secret-pass")
            self.assertTrue(agent_secrets["HERMES_AGENT_SECRET"])
            self.assertIn("Your name is Alice User.", soul_path.read_text(encoding="utf-8"))
            self.assertIn("AGENT_NAME=Alice User", home_env_path.read_text(encoding="utf-8"))
            self.assertIn("AGENT_ROLE=developer", home_env_path.read_text(encoding="utf-8"))

    def test_sync_agent_runtime_files_preserves_existing_home_files(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(2),
                {"id": 2, "name": "Bob Agent", "role": "marketing", "status": "stop"},
            )
            home_dir = self.state.agent_home_dir(2)
            self.state.ensure_private_directory(home_dir)
            soul_path = home_dir / "SOUL.md"
            home_env_path = home_dir / ".env"
            soul_path.write_text("custom soul\n", encoding="utf-8")
            home_env_path.write_text("CUSTOM=true\n", encoding="utf-8")

            self.sync.sync_agent_runtime_files(agent_id=2)

            self.assertEqual(soul_path.read_text(encoding="utf-8"), "custom soul\n")
            self.assertEqual(home_env_path.read_text(encoding="utf-8"), "CUSTOM=true\n")

    def test_sync_agent_runtime_files_updates_seeded_home_files_after_agent_edit(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(2),
                {"id": 2, "name": "Bob Agent", "role": "marketing", "status": "start"},
            )

            self.sync.sync_agent_runtime_files(agent_id=2)

            self.state.write_jsonfile(
                self.state.agent_metadata_path(2),
                {"id": 2, "name": "Bob Renamed", "role": "business_consultant", "status": "start"},
            )

            self.sync.sync_agent_runtime_files(agent_id=2)

            soul_path = self.state.agent_home_dir(2) / "SOUL.md"
            home_env_path = self.state.agent_home_dir(2) / ".env"

            self.assertIn("Your name is Bob Renamed.", soul_path.read_text(encoding="utf-8"))
            self.assertIn(
                "Your configured role is business consultant.",
                soul_path.read_text(encoding="utf-8"),
            )
            self.assertIn("AGENT_NAME=Bob Renamed", home_env_path.read_text(encoding="utf-8"))
            self.assertIn(
                "AGENT_ROLE=business_consultant",
                home_env_path.read_text(encoding="utf-8"),
            )

    def test_sync_agent_runtime_files_preserves_customized_seeded_home_files_after_agent_edit(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(2),
                {"id": 2, "name": "Bob Agent", "role": "marketing", "status": "start"},
            )

            self.sync.sync_agent_runtime_files(agent_id=2)

            soul_path = self.state.agent_home_dir(2) / "SOUL.md"
            home_env_path = self.state.agent_home_dir(2) / ".env"
            soul_path.write_text("customized soul\n", encoding="utf-8")
            home_env_path.write_text("CUSTOM=true\n", encoding="utf-8")

            self.state.write_jsonfile(
                self.state.agent_metadata_path(2),
                {"id": 2, "name": "Bob Renamed", "role": "business_consultant", "status": "start"},
            )

            self.sync.sync_agent_runtime_files(agent_id=2)

            self.assertEqual(soul_path.read_text(encoding="utf-8"), "customized soul\n")
            self.assertEqual(home_env_path.read_text(encoding="utf-8"), "CUSTOM=true\n")

    def test_sync_agent_runtime_files_replaces_symlinked_seed_file(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(4),
                {"id": 4, "name": "Dana Agent", "role": "sales", "status": "start"},
            )
            home_dir = self.state.agent_home_dir(4)
            self.state.ensure_private_directory(home_dir)
            soul_path = home_dir / "SOUL.md"
            target_path = home_dir / "outside.txt"
            target_path.write_text("do not overwrite\n", encoding="utf-8")
            os.symlink(target_path, soul_path)

            self.sync.sync_agent_runtime_files(agent_id=4)

            self.assertFalse(soul_path.is_symlink())
            self.assertIn("Your name is Dana Agent.", soul_path.read_text(encoding="utf-8"))
            self.assertEqual(target_path.read_text(encoding="utf-8"), "do not overwrite\n")

    def test_sync_agent_runtime_files_preserves_existing_agent_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                self.state.agent_metadata_path(3),
                {"id": 3, "name": "Carol Agent", "role": "researcher", "status": "start"},
            )
            self.state.write_envfile(
                self.state.agent_secrets_envfile(3),
                {"HERMES_AGENT_SECRET": "preserved", "SMTP_PASSWORD": "old-pass"},
            )
            self.state.write_envfile(self.state.SHARED_SECRETS_ENVFILE, {"SMTP_PASSWORD": "new-pass"})

            self.sync.sync_agent_runtime_files(agent_id=3)

            agent_secrets = self.state.read_envfile(self.state.agent_secrets_envfile(3))
            self.assertEqual(agent_secrets["HERMES_AGENT_SECRET"], "preserved")
            self.assertEqual(agent_secrets["SMTP_PASSWORD"], "new-pass")

    def test_configure_module_reconciles_removed_and_started_agents(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock())
        sys.modules["agent"] = agent_stub

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

    def test_configure_hosts_writes_unique_loopback_overrides(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bin_dir = temp_path / "bin"
            bin_dir.mkdir()

            write_executable(
                bin_dir / "api-cli",
                "#!/bin/sh\n"
                "cat <<'JSON'\n"
                "[\n"
                "  {\"host\": \"mail.example.com\"},\n"
                "  {\"host\": \"mail.example.com\", \"path\": \"/api\"},\n"
                "  {\"path\": \"/health\"},\n"
                "  {\"host\": \"chat.example.com\"},\n"
                "  {\"host\": \"bad host\"},\n"
                "  {\"host\": \"-bad.example.com\"},\n"
                "  {\"host\": \"bad-.example.com\"},\n"
                "  {\"host\": \"bad.example.com.\"}\n"
                "]\n"
                "JSON\n",
            )
            write_executable(
                bin_dir / "jq",
                "#!/usr/bin/env python3\n"
                "import json\n"
                "import sys\n"
                "for item in json.load(sys.stdin):\n"
                "    host = item.get('host')\n"
                "    if host:\n"
                "        print(host)\n",
            )

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

            subprocess.run(["bash", str(CONFIGURE_HOSTS_PATH)], cwd=temp_dir, env=env, check=True)

            self.assertEqual(
                (temp_path / "hosts").read_text(encoding="utf-8"),
                'PODMAN_ADD_HOST_ARGS="--add-host=chat.example.com:10.0.2.2 --add-host=mail.example.com:10.0.2.2"\n',
            )

    def test_configure_hosts_rejects_symlinked_hosts_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bin_dir = temp_path / "bin"
            bin_dir.mkdir()

            write_executable(
                bin_dir / "api-cli",
                "#!/bin/sh\n"
                "cat <<'JSON'\n"
                "[{\"host\": \"mail.example.com\"}]\n"
                "JSON\n",
            )
            write_executable(
                bin_dir / "jq",
                "#!/usr/bin/env python3\n"
                "import json\n"
                "import sys\n"
                "for item in json.load(sys.stdin):\n"
                "    host = item.get('host')\n"
                "    if host:\n"
                "        print(host)\n",
            )

            outside_path = temp_path / "outside.env"
            outside_path.write_text("SAFE=1\n", encoding="utf-8")
            os.symlink(outside_path, temp_path / "hosts")

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

            result = subprocess.run(
                ["bash", str(CONFIGURE_HOSTS_PATH)],
                cwd=temp_dir,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe file path: hosts", result.stderr)
            self.assertEqual(outside_path.read_text(encoding="utf-8"), "SAFE=1\n")

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