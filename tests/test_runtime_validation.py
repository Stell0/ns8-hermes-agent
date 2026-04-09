import importlib.util
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


RUNTIME_PATH = Path(__file__).resolve().parents[1] / "imageroot" / "pypkg" / "hermes_agent_runtime.py"


def load_runtime_module():
    original_agent = sys.modules.get("agent")
    sys.modules["agent"] = types.SimpleNamespace(set_env=lambda *args, **kwargs: None)
    try:
        spec = importlib.util.spec_from_file_location("hermes_agent_runtime_under_test", RUNTIME_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if original_agent is not None:
            sys.modules["agent"] = original_agent
        else:
            del sys.modules["agent"]


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


if __name__ == "__main__":
    unittest.main()