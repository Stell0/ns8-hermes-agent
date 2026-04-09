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


if __name__ == "__main__":
    unittest.main()