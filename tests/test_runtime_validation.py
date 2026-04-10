import importlib.util
import io
import json
import os
import re
import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


RUNTIME_PATH = Path(__file__).resolve().parents[1] / "imageroot" / "pypkg" / "hermes_agent_runtime.py"
CREATE_MODULE_PATH = Path(__file__).resolve().parents[1] / "imageroot" / "actions" / "create-module" / "20create"


def load_runtime_module():
    original_agent = sys.modules.get("agent")
    agent_stub = types.ModuleType("agent")
    setattr(agent_stub, "set_env", lambda *args, **kwargs: None)
    sys.modules["agent"] = agent_stub
    try:
        spec = importlib.util.spec_from_file_location("hermes_agent_runtime_under_test", RUNTIME_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("failed to load runtime module spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if original_agent is not None:
            sys.modules["agent"] = original_agent
        else:
            del sys.modules["agent"]


def run_create_module_script(tcp_port):
    original_agent = sys.modules.get("agent")
    agent_stub = types.ModuleType("agent")
    setattr(agent_stub, "set_env", mock.Mock())
    sys.modules["agent"] = agent_stub
    try:
        with mock.patch.dict(os.environ, {"TCP_PORT": tcp_port}, clear=True), mock.patch(
            "sys.stdin", io.StringIO("{}")
        ):
            runpy.run_path(str(CREATE_MODULE_PATH), run_name="__main__")
    finally:
        if original_agent is not None:
            sys.modules["agent"] = original_agent
        else:
            del sys.modules["agent"]

    return agent_stub


class ConfigureModuleValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = load_runtime_module()

    def test_configure_module_rejects_reserved_openviking_identifiers(self):
        reserved_cases = [
            ("account", "system", "agent account system is reserved"),
            ("user", "system", "agent user system is reserved"),
            ("agent_id", "openviking-backend", "agent agent_id openviking-backend is reserved"),
        ]

        for field, value, error_message in reserved_cases:
            with self.subTest(field=field):
                payload = {
                    "agents": [
                        {
                            "id": 1,
                            "name": "Valid Name",
                            "role": "default",
                            "status": "start",
                            field: value,
                        }
                    ]
                }

                with self.assertRaisesRegex(ValueError, re.escape(error_message)):
                    self.runtime.configure_module(payload)

    def test_system_agent_secrets_preserve_existing_api_server_key(self):
        system_agent = self.runtime.system_agent_data()
        secrets_env = self.runtime.build_agent_secrets_env(
            {},
            agent_data=system_agent,
            existing_agent_secrets={self.runtime.HERMES_API_SERVER_KEY_ENV: "preserved-key"},
        )

        self.assertEqual(secrets_env[self.runtime.HERMES_API_SERVER_KEY_ENV], "preserved-key")

    def test_configure_module_validates_openviking_before_persisting_agents(self):
        payload = {
            "agents": [
                {
                    "id": 1,
                    "name": "Valid Name",
                    "role": "default",
                    "status": "start",
                }
            ],
            "openviking": {
                "embedding": {
                    "provider": "openai",
                }
            },
        }

        with mock.patch.object(self.runtime, "read_openviking_settings", return_value={"embedding": {}}), mock.patch.object(
            self.runtime, "validate_openviking_settings", side_effect=ValueError("embedding api_key is required")
        ), mock.patch.object(self.runtime, "persist_agents") as persist_agents:
            with self.assertRaisesRegex(ValueError, re.escape("embedding api_key is required")):
                self.runtime.configure_module(payload)

        persist_agents.assert_not_called()

    def test_create_module_persists_ns8_tcp_port_to_openviking_port(self):
        agent_stub = run_create_module_script("23456")

        agent_stub.set_env.assert_any_call("OPENVIKING_PORT", "23456")
        agent_stub.set_env.assert_any_call("TIMEZONE", "UTC")

    def test_create_module_normalizes_blank_timezone(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock())
        sys.modules["agent"] = agent_stub
        try:
            with mock.patch.dict(os.environ, {"TCP_PORT": "23456", "TIMEZONE": "   "}, clear=True), mock.patch(
                "sys.stdin", io.StringIO("{}")
            ):
                runpy.run_path(str(CREATE_MODULE_PATH), run_name="__main__")
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

        agent_stub.set_env.assert_any_call("TIMEZONE", "UTC")

    def test_create_module_rejects_invalid_tcp_port(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock())
        sys.modules["agent"] = agent_stub
        try:
            with mock.patch.dict(os.environ, {"TCP_PORT": "0"}, clear=True), mock.patch(
                "sys.stdin", io.StringIO("{}")
            ):
                with self.assertRaisesRegex(ValueError, re.escape("invalid TCP_PORT: 0")):
                    runpy.run_path(str(CREATE_MODULE_PATH), run_name="__main__")
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

        agent_stub.set_env.assert_not_called()

    def test_validate_agents_accepts_gateway_flag(self):
        agents = self.runtime.validate_agents(
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

        self.assertTrue(agents[0]["use_default_gateway_for_llm"])

    def test_validate_agents_accepts_supported_roles(self):
        for role in [
            "default",
            "developer",
            "marketing",
            "sales",
            "customer_support",
            "social_media_manager",
            "business_consultant",
            "researcher",
        ]:
            with self.subTest(role=role):
                agents = self.runtime.validate_agents(
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

    def test_validate_agents_rejects_non_boolean_gateway_flag(self):
        with self.assertRaisesRegex(ValueError, re.escape("agent at index 0 has an invalid use_default_gateway_for_llm flag")):
            self.runtime.validate_agents(
                [
                    {
                        "id": 1,
                        "name": "Valid Name",
                        "role": "default",
                        "status": "start",
                        "use_default_gateway_for_llm": "yes",
                    }
                ]
            )

    def test_parse_agents_list_keeps_backward_compatibility(self):
        agents = self.runtime.parse_agents_list("1:Valid Name:default:start:agent-1:agent-1:agent-1")

        self.assertEqual(len(agents), 1)
        self.assertFalse(agents[0]["use_default_gateway_for_llm"])

    def test_serialize_agents_round_trips_gateway_flag(self):
        raw_agents = [
            {
                "id": 1,
                "name": "Valid Name",
                "role": "default",
                "status": "start",
                "account": "agent-1",
                "user": "agent-1",
                "agent_id": "agent-1",
                "use_default_gateway_for_llm": True,
            }
        ]

        serialized = self.runtime.serialize_agents(raw_agents)
        parsed = self.runtime.parse_agents_list(serialized)

        self.assertTrue(parsed[0]["use_default_gateway_for_llm"])

    def test_sync_agent_llm_gateway_config_uses_hermes_config_set(self):
        agent_data = {
            "id": 1,
            "use_default_gateway_for_llm": True,
        }
        shared_environment = {
            self.runtime.HERMES_SYSTEM_API_PORT_ENV: str(self.runtime.HERMES_API_SERVER_PORT),
            self.runtime.HERMES_IMAGE_ENV: "example/hermes:latest",
        }
        system_agent_secrets = {
            self.runtime.HERMES_API_SERVER_KEY_ENV: "test-key",
        }

        with mock.patch.object(self.runtime, "run_command") as run_command:
            self.runtime.sync_agent_llm_gateway_config(agent_data, shared_environment, system_agent_secrets)

        commands = [call.args[0] for call in run_command.call_args_list]
        self.assertEqual(len(commands), 4)
        self.assertEqual(commands[0][-4:], ["config", "set", "model.provider", "custom"])
        self.assertEqual(commands[1][-4:], ["config", "set", "model.default", self.runtime.HERMES_API_MODEL_NAME])
        self.assertEqual(
            commands[2][-4:],
            ["config", "set", "model.base_url", f"http://{self.runtime.OPENVIKING_CONTAINER_HOST}:{self.runtime.HERMES_API_SERVER_PORT}/v1"],
        )
        self.assertEqual(commands[3][-4:], ["config", "set", "OPENAI_API_KEY", "test-key"])

    def test_sync_agent_llm_gateway_config_clears_gateway_settings_when_disabled(self):
        agent_data = {
            "id": 1,
            "use_default_gateway_for_llm": False,
        }
        shared_environment = {
            self.runtime.HERMES_SYSTEM_API_PORT_ENV: str(self.runtime.HERMES_API_SERVER_PORT),
            self.runtime.HERMES_IMAGE_ENV: "example/hermes:latest",
        }

        with mock.patch.object(self.runtime, "run_command") as run_command:
            self.runtime.sync_agent_llm_gateway_config(agent_data, shared_environment, {})

        commands = [call.args[0] for call in run_command.call_args_list]
        self.assertEqual(len(commands), 4)
        self.assertEqual(commands[0][-4:], ["config", "set", "model.provider", "auto"])
        self.assertEqual(commands[1][-4:], ["config", "set", "model.default", ""])
        self.assertEqual(commands[2][-4:], ["config", "set", "model.base_url", ""])
        self.assertEqual(commands[3][-4:], ["config", "set", "OPENAI_API_KEY", ""])

    def test_sync_agent_llm_gateway_config_requires_system_gateway_key_when_enabled(self):
        agent_data = {
            "id": 1,
            "use_default_gateway_for_llm": True,
        }
        shared_environment = {
            self.runtime.HERMES_SYSTEM_API_PORT_ENV: str(self.runtime.HERMES_API_SERVER_PORT),
            self.runtime.HERMES_IMAGE_ENV: "example/hermes:latest",
        }

        with self.assertRaisesRegex(ValueError, re.escape("missing system gateway API key")):
            self.runtime.sync_agent_llm_gateway_config(agent_data, shared_environment, {})

    def test_render_agent_soul_uses_required_seed_line(self):
        soul = self.runtime.render_agent_soul("Research Partner", "researcher")

        self.assertTrue(
            soul.startswith(
                "- Your name is Research Partner, you are an Hermes Agent that runs on NethServer8\n"
            )
        )
        self.assertIn("## Identity", soul)
        self.assertIn("evidence, careful synthesis, and honest uncertainty", soul)

    def test_should_replace_agent_soul_allows_previous_seed(self):
        existing_agent_env = {
            "AGENT_NAME": "Valid Name",
            "AGENT_ROLE": "developer",
        }
        current_content = self.runtime.render_agent_soul("Valid Name", "developer")

        self.assertTrue(self.runtime.should_replace_agent_soul(current_content, existing_agent_env))

    def test_should_replace_agent_soul_preserves_customized_content(self):
        existing_agent_env = {
            "AGENT_NAME": "Valid Name",
            "AGENT_ROLE": "developer",
        }
        current_content = self.runtime.render_agent_soul("Valid Name", "developer") + "\nCustom note\n"

        self.assertFalse(self.runtime.should_replace_agent_soul(current_content, existing_agent_env))

    def test_sync_agent_soul_creates_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hermes_home = Path(temp_dir)
            agent_data = {
                "id": 1,
                "name": "Alice User",
                "role": "customer_support",
            }

            with mock.patch.object(self.runtime, "agent_hermes_home", return_value=hermes_home):
                updated = self.runtime.sync_agent_soul(agent_data, {})

            self.assertTrue(updated)
            self.assertEqual(
                (hermes_home / self.runtime.SOUL_FILENAME).read_text(encoding="utf-8"),
                self.runtime.render_agent_soul("Alice User", "customer_support"),
            )

    def test_sync_agent_soul_rewrites_previous_seed_on_role_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hermes_home = Path(temp_dir)
            soul_path = hermes_home / self.runtime.SOUL_FILENAME
            soul_path.write_text(self.runtime.render_agent_soul("Alice User", "developer"), encoding="utf-8")
            agent_data = {
                "id": 1,
                "name": "Alice User",
                "role": "marketing",
            }
            existing_agent_env = {
                "AGENT_NAME": "Alice User",
                "AGENT_ROLE": "developer",
            }

            with mock.patch.object(self.runtime, "agent_hermes_home", return_value=hermes_home):
                updated = self.runtime.sync_agent_soul(agent_data, existing_agent_env)

            self.assertTrue(updated)
            self.assertEqual(
                soul_path.read_text(encoding="utf-8"),
                self.runtime.render_agent_soul("Alice User", "marketing"),
            )

    def test_sync_agent_soul_rewrites_previous_seed_on_name_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hermes_home = Path(temp_dir)
            soul_path = hermes_home / self.runtime.SOUL_FILENAME
            soul_path.write_text(self.runtime.render_agent_soul("Alice User", "developer"), encoding="utf-8")
            agent_data = {
                "id": 1,
                "name": "Alice Agent",
                "role": "developer",
            }
            existing_agent_env = {
                "AGENT_NAME": "Alice User",
                "AGENT_ROLE": "developer",
            }

            with mock.patch.object(self.runtime, "agent_hermes_home", return_value=hermes_home):
                updated = self.runtime.sync_agent_soul(agent_data, existing_agent_env)

            self.assertTrue(updated)
            self.assertEqual(
                soul_path.read_text(encoding="utf-8"),
                self.runtime.render_agent_soul("Alice Agent", "developer"),
            )

    def test_sync_agent_soul_preserves_customized_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hermes_home = Path(temp_dir)
            soul_path = hermes_home / self.runtime.SOUL_FILENAME
            soul_path.write_text("customized soul\n", encoding="utf-8")
            agent_data = {
                "id": 1,
                "name": "Alice User",
                "role": "marketing",
            }
            existing_agent_env = {
                "AGENT_NAME": "Alice User",
                "AGENT_ROLE": "developer",
            }

            with mock.patch.object(self.runtime, "agent_hermes_home", return_value=hermes_home):
                updated = self.runtime.sync_agent_soul(agent_data, existing_agent_env)

            self.assertFalse(updated)
            self.assertEqual(soul_path.read_text(encoding="utf-8"), "customized soul\n")

    def test_read_private_textfile_ignores_symlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            target_path = temp_path / "target.txt"
            target_path.write_text("target content\n", encoding="utf-8")
            link_path = temp_path / self.runtime.SOUL_FILENAME
            os.symlink(target_path, link_path)

            self.assertIsNone(self.runtime.read_private_textfile(link_path))

    def test_sync_agent_soul_replaces_symlink_without_following_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hermes_home = Path(temp_dir)
            target_path = hermes_home / "outside.txt"
            target_path.write_text("do not overwrite\n", encoding="utf-8")
            soul_path = hermes_home / self.runtime.SOUL_FILENAME
            os.symlink(target_path, soul_path)
            agent_data = {
                "id": 1,
                "name": "Alice User",
                "role": "marketing",
            }

            with mock.patch.object(self.runtime, "agent_hermes_home", return_value=hermes_home):
                updated = self.runtime.sync_agent_soul(agent_data, {})

            self.assertTrue(updated)
            self.assertFalse(soul_path.is_symlink())
            self.assertEqual(
                soul_path.read_text(encoding="utf-8"),
                self.runtime.render_agent_soul("Alice User", "marketing"),
            )
            self.assertEqual(target_path.read_text(encoding="utf-8"), "do not overwrite\n")

    def test_extract_route_hosts_normalizes_and_deduplicates_hosts(self):
        route_data = [
            {"host": "portal.example.org"},
            {"host": "Portal.Example.Org."},
            {"host": "*.example.org"},
            {"host": "127.0.0.1"},
            {"host": "localhost"},
            {"host": "host.containers.internal"},
            {"host": "intranet"},
            {"host": ""},
            {"host": ["wiki.example.org", "wiki.example.org "]},
            {"path": "/no-host"},
        ]

        self.assertEqual(
            self.runtime.extract_route_hosts(route_data),
            ["portal.example.org", "wiki.example.org"],
        )

    def test_fetch_node_traefik_route_hosts_uses_expanded_list_routes(self):
        agent_tasks = types.SimpleNamespace(
            run=mock.Mock(
                return_value={
                    "exit_code": 0,
                    "output": json.dumps([
                        {"host": "portal.example.org"},
                        {"host": "wiki.example.org"},
                    ]),
                }
            )
        )

        with mock.patch.object(self.runtime.agent, "resolve_agent_id", return_value="module/traefik1", create=True), mock.patch(
            "importlib.import_module",
            return_value=agent_tasks,
        ):
            route_hosts = self.runtime.fetch_node_traefik_route_hosts()

        self.assertEqual(route_hosts, ["portal.example.org", "wiki.example.org"])
        agent_tasks.run.assert_called_once_with(
            agent_id="module/traefik1",
            action="list-routes",
            data={"expand_list": True},
        )

    def test_sync_traefik_route_hosts_reuses_cached_hosts_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            route_hosts_path = Path(temp_dir) / self.runtime.TRAEFIK_ROUTE_HOSTS_STATEFILE
            route_hosts_path.write_text(json.dumps(["cached.example.org"]), encoding="utf-8")

            with mock.patch.object(
                self.runtime,
                "fetch_node_traefik_route_hosts",
                side_effect=RuntimeError("traefik unavailable"),
            ):
                route_hosts = self.runtime.sync_traefik_route_hosts(route_hosts_path)

            self.assertEqual(route_hosts, ["cached.example.org"])
            self.assertEqual(
                json.loads(route_hosts_path.read_text(encoding="utf-8")),
                ["cached.example.org"],
            )

    def test_sync_traefik_route_hosts_reuses_cached_hosts_on_unexpected_exception(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            route_hosts_path = Path(temp_dir) / self.runtime.TRAEFIK_ROUTE_HOSTS_STATEFILE
            route_hosts_path.write_text(json.dumps(["cached.example.org"]), encoding="utf-8")

            with mock.patch.object(
                self.runtime,
                "fetch_node_traefik_route_hosts",
                side_effect=ValueError("malformed response"),
            ):
                route_hosts = self.runtime.sync_traefik_route_hosts(route_hosts_path)

            self.assertEqual(route_hosts, ["cached.example.org"])

    def test_sync_traefik_route_hosts_writes_empty_list_without_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            route_hosts_path = Path(temp_dir) / self.runtime.TRAEFIK_ROUTE_HOSTS_STATEFILE

            with mock.patch.object(
                self.runtime,
                "fetch_node_traefik_route_hosts",
                side_effect=RuntimeError("traefik unavailable"),
            ):
                route_hosts = self.runtime.sync_traefik_route_hosts(route_hosts_path)

            self.assertEqual(route_hosts, [])
            self.assertEqual(json.loads(route_hosts_path.read_text(encoding="utf-8")), [])

    def test_sync_traefik_route_hosts_writes_fetched_hosts_on_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            route_hosts_path = Path(temp_dir) / self.runtime.TRAEFIK_ROUTE_HOSTS_STATEFILE

            with mock.patch.object(
                self.runtime,
                "fetch_node_traefik_route_hosts",
                return_value=["portal.example.org", "wiki.example.org"],
            ):
                route_hosts = self.runtime.sync_traefik_route_hosts(route_hosts_path)

            self.assertEqual(route_hosts, ["portal.example.org", "wiki.example.org"])
            self.assertEqual(
                json.loads(route_hosts_path.read_text(encoding="utf-8")),
                ["portal.example.org", "wiki.example.org"],
            )

    def test_build_hermes_container_command_adds_network_and_route_hosts(self):
        shared_environment = {
            self.runtime.TIMEZONE_ENV: "UTC",
            self.runtime.HERMES_IMAGE_ENV: "example/hermes:latest",
        }

        command = self.runtime.build_hermes_container_command(
            3,
            shared_environment,
            publish=["127.0.0.1:8642:8642"],
            route_hosts=["portal.example.org", "wiki.example.org"],
        )

        self.assertIn("--network", command)
        self.assertIn(self.runtime.HERMES_CONTAINER_NETWORK, command)
        self.assertIn("--publish", command)
        self.assertIn("127.0.0.1:8642:8642", command)
        self.assertIn("portal.example.org:host-gateway", command)
        self.assertIn("wiki.example.org:host-gateway", command)
        self.assertEqual(command[-1], "example/hermes:latest")

    def test_run_hermes_container_uses_cached_route_hosts_by_default(self):
        shared_environment = {
            self.runtime.TIMEZONE_ENV: "UTC",
            self.runtime.HERMES_IMAGE_ENV: "example/hermes:latest",
        }

        with mock.patch.object(
            self.runtime,
            "read_optional_envfile",
            return_value=shared_environment,
        ), mock.patch.object(
            self.runtime,
            "read_cached_traefik_route_hosts",
            return_value=["portal.example.org"],
        ), mock.patch.object(
            self.runtime,
            "run_command",
            return_value=types.SimpleNamespace(returncode=0),
        ) as run_command:
            returncode = self.runtime.run_hermes_container(3, publish=["127.0.0.1:8642:8642"])

        self.assertEqual(returncode, 0)
        command = run_command.call_args.args[0]
        self.assertIn("--publish", command)
        self.assertIn("127.0.0.1:8642:8642", command)
        self.assertIn("--add-host", command)
        self.assertIn("portal.example.org:host-gateway", command)
        self.assertEqual(run_command.call_args.kwargs["check"], False)

    def test_sync_agent_runtime_files_seeds_soul_only_for_started_user_agents(self):
        started_agent = {
            "id": 1,
            "name": "Started Agent",
            "role": "developer",
            "status": "start",
            "account": "agent-1",
            "user": "agent-1",
            "agent_id": "agent-1",
            "use_default_gateway_for_llm": False,
        }
        stopped_agent = {
            "id": 2,
            "name": "Stopped Agent",
            "role": "marketing",
            "status": "stop",
            "account": "agent-2",
            "user": "agent-2",
            "agent_id": "agent-2",
            "use_default_gateway_for_llm": False,
        }
        shared_environment = {
            self.runtime.OPENVIKING_PORT_ENV: "23456",
            self.runtime.HERMES_SYSTEM_API_PORT_ENV: str(self.runtime.HERMES_API_SERVER_PORT),
            self.runtime.HERMES_IMAGE_ENV: "example/hermes:latest",
        }
        shared_secrets = {
            self.runtime.OPENVIKING_ROOT_API_KEY_ENV: "root-key",
        }

        def read_optional_envfile_side_effect(path):
            if path == self.runtime.ENVIRONMENT_FILE:
                return shared_environment
            if path == self.runtime.SHARED_SECRETS_ENVFILE:
                return shared_secrets
            return {}

        with mock.patch.object(
            self.runtime,
            "read_managed_agents_from_state",
            return_value=[self.runtime.system_agent_data(), started_agent, stopped_agent],
        ), mock.patch.object(
            self.runtime,
            "read_optional_envfile",
            side_effect=read_optional_envfile_side_effect,
        ), mock.patch.object(
            self.runtime,
            "ensure_shared_openviking_settings",
            return_value=(23456, "root-key", self.runtime.HERMES_API_SERVER_PORT),
        ), mock.patch.object(
            self.runtime,
            "build_agent_secrets_env",
            return_value={},
        ), mock.patch.object(
            self.runtime,
            "build_openviking_config",
            return_value={},
        ), mock.patch.object(
            self.runtime,
            "write_envfile",
        ), mock.patch.object(
            self.runtime,
            "sync_traefik_route_hosts",
            return_value=[],
        ), mock.patch.object(
            self.runtime,
            "write_jsonfile",
        ), mock.patch.object(
            self.runtime,
            "sync_agent_llm_gateway_config",
        ), mock.patch.object(
            self.runtime,
            "sync_agent_soul",
        ) as sync_agent_soul:
            self.runtime.sync_agent_runtime_files()

        sync_agent_soul.assert_called_once_with(started_agent, {})

    def test_sync_agent_runtime_files_skips_route_refresh_for_agent_specific_sync_with_cache(self):
        shared_environment = {
            self.runtime.OPENVIKING_PORT_ENV: "23456",
            self.runtime.TIMEZONE_ENV: "UTC",
            self.runtime.HERMES_SYSTEM_API_PORT_ENV: str(self.runtime.HERMES_API_SERVER_PORT),
            self.runtime.HERMES_IMAGE_ENV: "example/hermes:latest",
        }
        shared_secrets = {
            self.runtime.OPENVIKING_ROOT_API_KEY_ENV: "root-key",
        }
        agent_data = {
            "id": 1,
            "name": "Started Agent",
            "role": "developer",
            "status": "start",
            "account": "agent-1",
            "user": "agent-1",
            "agent_id": "agent-1",
            "use_default_gateway_for_llm": False,
        }

        def read_optional_envfile_side_effect(path):
            if path == self.runtime.ENVIRONMENT_FILE:
                return shared_environment
            if path == self.runtime.SHARED_SECRETS_ENVFILE:
                return shared_secrets
            return {}

        with mock.patch.object(
            self.runtime,
            "read_managed_agents_from_state",
            return_value=[self.runtime.system_agent_data(), agent_data],
        ), mock.patch.object(
            self.runtime,
            "read_optional_envfile",
            side_effect=read_optional_envfile_side_effect,
        ), mock.patch.object(
            self.runtime,
            "ensure_shared_openviking_settings",
            return_value=(23456, "root-key", self.runtime.HERMES_API_SERVER_PORT),
        ), mock.patch.object(
            self.runtime,
            "build_agent_secrets_env",
            return_value={},
        ), mock.patch.object(
            self.runtime,
            "build_openviking_config",
            return_value={},
        ), mock.patch.object(
            self.runtime,
            "write_envfile",
        ), mock.patch.object(
            self.runtime,
            "read_cached_traefik_route_hosts",
            return_value=["portal.example.org"],
        ), mock.patch.object(
            self.runtime,
            "sync_traefik_route_hosts",
        ) as sync_traefik_route_hosts, mock.patch.object(
            self.runtime,
            "write_jsonfile",
        ), mock.patch.object(
            self.runtime,
            "sync_agent_llm_gateway_config",
        ), mock.patch.object(
            self.runtime,
            "sync_agent_soul",
        ):
            self.runtime.sync_agent_runtime_files(agent_id=1)

        sync_traefik_route_hosts.assert_not_called()

    def test_ensure_shared_openviking_settings_requires_preseeded_openviking_port(self):
        shared_environment = {
            self.runtime.HERMES_SYSTEM_API_PORT_ENV: str(self.runtime.HERMES_API_SERVER_PORT),
        }
        shared_secrets = {
            self.runtime.OPENVIKING_ROOT_API_KEY_ENV: "root-key",
        }

        with self.assertRaisesRegex(
            ValueError, re.escape(f"invalid {self.runtime.OPENVIKING_PORT_ENV}: None")
        ):
            self.runtime.ensure_shared_openviking_settings(shared_environment, shared_secrets)

    def test_ensure_shared_openviking_settings_preserves_preseeded_openviking_port(self):
        shared_environment = {
            self.runtime.OPENVIKING_PORT_ENV: "23456",
            self.runtime.HERMES_SYSTEM_API_PORT_ENV: str(self.runtime.HERMES_API_SERVER_PORT),
        }
        shared_secrets = {
            self.runtime.OPENVIKING_ROOT_API_KEY_ENV: "root-key",
        }

        port, root_api_key, system_api_port = self.runtime.ensure_shared_openviking_settings(
            shared_environment, shared_secrets
        )

        self.assertEqual(port, 23456)
        self.assertEqual(root_api_key, "root-key")
        self.assertEqual(system_api_port, self.runtime.HERMES_API_SERVER_PORT)

    def test_ensure_shared_openviking_settings_backfills_from_ns8_tcp_port(self):
        shared_environment = {
            self.runtime.TCP_PORT_ENV: "23456",
            self.runtime.TIMEZONE_ENV: "UTC",
            self.runtime.HERMES_SYSTEM_API_PORT_ENV: str(self.runtime.HERMES_API_SERVER_PORT),
        }
        shared_secrets = {
            self.runtime.OPENVIKING_ROOT_API_KEY_ENV: "root-key",
        }

        with mock.patch.object(self.runtime.agent, "set_env") as set_env:
            port, root_api_key, system_api_port = self.runtime.ensure_shared_openviking_settings(
                shared_environment, shared_secrets
            )

        self.assertEqual(port, 23456)
        self.assertEqual(root_api_key, "root-key")
        self.assertEqual(system_api_port, self.runtime.HERMES_API_SERVER_PORT)
        self.assertEqual(shared_environment[self.runtime.OPENVIKING_PORT_ENV], "23456")
        set_env.assert_called_once_with(self.runtime.OPENVIKING_PORT_ENV, "23456")

    def test_ensure_shared_openviking_settings_still_allocates_system_api_port(self):
        shared_environment = {
            self.runtime.OPENVIKING_PORT_ENV: "23456",
            self.runtime.TIMEZONE_ENV: "UTC",
        }
        shared_secrets = {
            self.runtime.OPENVIKING_ROOT_API_KEY_ENV: "root-key",
        }

        with mock.patch.object(self.runtime, "reserve_tcp_port", return_value=34567), mock.patch.object(
            self.runtime.agent, "set_env"
        ) as set_env:
            port, root_api_key, system_api_port = self.runtime.ensure_shared_openviking_settings(
                shared_environment, shared_secrets
            )

        self.assertEqual(port, 23456)
        self.assertEqual(root_api_key, "root-key")
        self.assertEqual(system_api_port, 34567)
        set_env.assert_called_once_with(self.runtime.HERMES_SYSTEM_API_PORT_ENV, "34567")

    def test_ensure_shared_openviking_settings_backfills_timezone(self):
        shared_environment = {
            self.runtime.OPENVIKING_PORT_ENV: "23456",
            self.runtime.HERMES_SYSTEM_API_PORT_ENV: str(self.runtime.HERMES_API_SERVER_PORT),
        }
        shared_secrets = {
            self.runtime.OPENVIKING_ROOT_API_KEY_ENV: "root-key",
        }

        with mock.patch.dict(os.environ, {self.runtime.TIMEZONE_ENV: "Europe/Rome"}, clear=False), mock.patch.object(
            self.runtime.agent, "set_env"
        ) as set_env:
            self.runtime.ensure_shared_openviking_settings(shared_environment, shared_secrets)

        self.assertEqual(shared_environment[self.runtime.TIMEZONE_ENV], "Europe/Rome")
        set_env.assert_called_once_with(self.runtime.TIMEZONE_ENV, "Europe/Rome")

    def test_ensure_shared_openviking_settings_normalizes_blank_timezone(self):
        shared_environment = {
            self.runtime.OPENVIKING_PORT_ENV: "23456",
            self.runtime.HERMES_SYSTEM_API_PORT_ENV: str(self.runtime.HERMES_API_SERVER_PORT),
        }
        shared_secrets = {
            self.runtime.OPENVIKING_ROOT_API_KEY_ENV: "root-key",
        }

        with mock.patch.dict(os.environ, {self.runtime.TIMEZONE_ENV: "   "}, clear=False), mock.patch.object(
            self.runtime.agent, "set_env"
        ) as set_env:
            self.runtime.ensure_shared_openviking_settings(shared_environment, shared_secrets)

        self.assertEqual(shared_environment[self.runtime.TIMEZONE_ENV], "UTC")
        set_env.assert_called_once_with(self.runtime.TIMEZONE_ENV, "UTC")


if __name__ == "__main__":
    unittest.main()