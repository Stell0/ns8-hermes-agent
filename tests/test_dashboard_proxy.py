import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROXY_PATH = ROOT / "containers" / "hermes" / "hermes-dashboard-proxy.py"


def load_proxy_module():
    spec = importlib.util.spec_from_file_location("hermes_dashboard_proxy", PROXY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HermesDashboardProxyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proxy = load_proxy_module()

    def test_normalize_prefix_accepts_safe_path_prefix(self):
        self.assertEqual(self.proxy.normalize_prefix(" /hermes-agent-1/ "), "/hermes-agent-1")

    def test_normalize_prefix_rejects_unsafe_characters(self):
        self.assertEqual(self.proxy.normalize_prefix('"/><script>alert(1)</script>'), "")

    def test_rewrite_text_uses_json_escaped_prefix_script(self):
        html = "<html><head></head><body><a href=\"/api\">api</a></body></html>"

        rewritten = self.proxy.rewrite_text(html, "/hermes-agent-1")

        self.assertIn('window.__HERMES_DASHBOARD_PREFIX__ = "/hermes-agent-1"', rewritten)
        self.assertIn('href="/hermes-agent-1/api"', rewritten)


if __name__ == "__main__":
    unittest.main()