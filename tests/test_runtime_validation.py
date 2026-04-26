import asyncio
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
ENSURE_AGENT_HOME_OWNERSHIP_PATH = ROOT / "imageroot" / "bin" / "ensure-agent-home-ownership"
SERVICE_TEMPLATE_PATH = ROOT / "imageroot" / "systemd" / "user" / "hermes@.service"
AUTH_SERVICE_TEMPLATE_PATH = ROOT / "imageroot" / "systemd" / "user" / "hermes-auth.service"
POD_SERVICE_TEMPLATE_PATH = ROOT / "imageroot" / "systemd" / "user" / "hermes-pod@.service"
SOCKET_SERVICE_TEMPLATE_PATH = ROOT / "imageroot" / "systemd" / "user" / "hermes-socket@.service"
AUTH_CONTAINERFILE_PATH = ROOT / "containers" / "auth" / "Containerfile"
HERMES_CONTAINERFILE_PATH = ROOT / "containers" / "hermes" / "Containerfile"
SOCKET_CONTAINERFILE_PATH = ROOT / "containers" / "socket" / "Containerfile"
HERMES_ENTRYPOINT_PATH = ROOT / "containers" / "hermes" / "entrypoint.sh"
HERMES_DASHBOARD_PATCH_PATH = ROOT / "containers" / "hermes" / "patch_dashboard_source.py"
BUILD_IMAGES_PATH = ROOT / "build-images.sh"
CREATE_MODULE_ACTION_DIR = ROOT / "imageroot" / "actions" / "create-module"
CONFIGURE_MODULE_ACTION_DIR = ROOT / "imageroot" / "actions" / "configure-module"
DESTROY_MODULE_ACTION_DIR = ROOT / "imageroot" / "actions" / "destroy-module"
UPDATE_MODULE_SCRIPT_DIR = ROOT / "imageroot" / "update-module.d"
PERSIST_SHARED_ENV_PATH = CONFIGURE_MODULE_ACTION_DIR / "20persist-shared-env"
SEED_AGENT_HOME_ACTION_PATH = CONFIGURE_MODULE_ACTION_DIR / "75seed-agent-home"
UPDATE_OWNERSHIP_SCRIPT_PATH = UPDATE_MODULE_SCRIPT_DIR / "30ensure-agent-home-ownership"
RECONCILE_DESIRED_ROUTES_PATH = CONFIGURE_MODULE_ACTION_DIR / "90reconcile-desired-routes"
DESTROY_REMOVE_ROUTES_PATH = DESTROY_MODULE_ACTION_DIR / "10remove-routes"
GET_CONFIGURATION_PATH = ROOT / "imageroot" / "actions" / "get-configuration" / "20read"
GET_AGENT_RUNTIME_PATH = ROOT / "imageroot" / "actions" / "get-agent-runtime" / "10read"
SMARTHOST_CHANGED_EVENT_PATH = ROOT / "imageroot" / "events" / "smarthost-changed" / "10reload_services"
LIST_USER_DOMAINS_PATH = ROOT / "imageroot" / "actions" / "list-user-domains" / "10read"
LIST_DOMAIN_USERS_PATH = ROOT / "imageroot" / "actions" / "list-domain-users" / "10read"
AUTHPROXY_PATH = ROOT / "containers" / "auth" / "authproxy.py"


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


@contextmanager
def mocked_ldap_modules(domains=None, users_by_domain=None):
    original_ldapproxy = sys.modules.get("agent.ldapproxy")
    original_ldapclient = sys.modules.get("agent.ldapclient")

    domains = domains or {}
    users_by_domain = users_by_domain or {}

    ldapproxy_module = types.ModuleType("agent.ldapproxy")
    ldapclient_module = types.ModuleType("agent.ldapclient")

    class FakeLdapproxy:
        def get_domains_list(self):
            return list(domains)

        def get_domain(self, domain):
            return domains.get(domain)

    class FakeLdapClientInstance:
        def __init__(self, records):
            self.records = records

        def list_users(self, extra_info=False):
            if extra_info:
                return [dict(record) for record in self.records]

            return [{"user": record["user"]} for record in self.records]

    class FakeLdapclient:
        @staticmethod
        def factory(**kwargs):
            user_domain = kwargs.get("domain_name")
            if user_domain is None:
                for domain_name, domain_data in domains.items():
                    if domain_data == kwargs:
                        user_domain = domain_name
                        break

            return FakeLdapClientInstance(users_by_domain.get(user_domain, []))

    setattr(ldapproxy_module, "Ldapproxy", FakeLdapproxy)
    setattr(ldapclient_module, "Ldapclient", FakeLdapclient)

    sys.modules["agent.ldapproxy"] = ldapproxy_module
    sys.modules["agent.ldapclient"] = ldapclient_module

    try:
        yield
    finally:
        if original_ldapproxy is not None:
            sys.modules["agent.ldapproxy"] = original_ldapproxy
        else:
            del sys.modules["agent.ldapproxy"]

        if original_ldapclient is not None:
            sys.modules["agent.ldapclient"] = original_ldapclient
        else:
            del sys.modules["agent.ldapclient"]


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


@contextmanager
def mocked_authproxy_dependencies():
    module_names = [
        "fastapi",
        "fastapi.responses",
        "httpx",
        "itsdangerous",
        "ldap3",
        "ldap3.utils",
        "ldap3.utils.conv",
        "uvicorn",
    ]
    original_modules = {name: sys.modules.get(name) for name in module_names}

    fastapi_module = types.ModuleType("fastapi")
    fastapi_responses_module = types.ModuleType("fastapi.responses")
    httpx_module = types.ModuleType("httpx")
    itsdangerous_module = types.ModuleType("itsdangerous")
    ldap3_module = types.ModuleType("ldap3")
    ldap3_utils_module = types.ModuleType("ldap3.utils")
    ldap3_utils_conv_module = types.ModuleType("ldap3.utils.conv")
    uvicorn_module = types.ModuleType("uvicorn")

    class FakeFastAPI:
        def __init__(self, *args, **kwargs):
            self.state = types.SimpleNamespace()
            self.lifespan = kwargs.get("lifespan")

        def get(self, *_args, **_kwargs):
            def decorator(function):
                return function

            return decorator

        def post(self, *_args, **_kwargs):
            def decorator(function):
                return function

            return decorator

        def api_route(self, *_args, **_kwargs):
            def decorator(function):
                return function

            return decorator

        def on_event(self, *_args, **_kwargs):
            raise AssertionError("authproxy should use FastAPI lifespan instead of on_event")

    class FakeResponse:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def set_cookie(self, *args, **kwargs):
            self.cookie_args = args
            self.cookie_kwargs = kwargs

        def delete_cookie(self, *args, **kwargs):
            self.delete_cookie_args = args
            self.delete_cookie_kwargs = kwargs

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def request(self, *args, **kwargs):
            raise NotImplementedError

        async def aclose(self):
            return None

    class FakeSerializer:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def dumps(self, payload):
            return json.dumps(payload)

        def loads(self, payload, max_age=None):
            del max_age
            return json.loads(payload)

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

    class FakeRequestError(Exception):
        pass

    class FakeReadError(FakeRequestError):
        pass

    class FakeAsyncHTTPTransport:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    def escape_filter_chars(value):
        return value.replace("\\", r"\5c").replace("*", r"\2a").replace("(", r"\28").replace(")", r"\29")

    setattr(fastapi_module, "FastAPI", FakeFastAPI)
    setattr(fastapi_module, "Request", object)
    setattr(fastapi_responses_module, "HTMLResponse", FakeResponse)
    setattr(fastapi_responses_module, "JSONResponse", FakeResponse)
    setattr(fastapi_responses_module, "PlainTextResponse", FakeResponse)
    setattr(fastapi_responses_module, "RedirectResponse", FakeResponse)
    setattr(fastapi_responses_module, "Response", FakeResponse)
    setattr(httpx_module, "AsyncClient", FakeAsyncClient)
    setattr(httpx_module, "AsyncHTTPTransport", FakeAsyncHTTPTransport)
    setattr(httpx_module, "RequestError", FakeRequestError)
    setattr(httpx_module, "ReadError", FakeReadError)
    setattr(itsdangerous_module, "BadSignature", ValueError)
    setattr(itsdangerous_module, "BadTimeSignature", ValueError)
    setattr(itsdangerous_module, "URLSafeTimedSerializer", FakeSerializer)
    setattr(ldap3_module, "ALL", object())
    setattr(ldap3_module, "Connection", FakeConnection)
    setattr(ldap3_module, "Server", object)
    setattr(ldap3_utils_conv_module, "escape_filter_chars", escape_filter_chars)
    setattr(uvicorn_module, "run", lambda *args, **kwargs: None)

    sys.modules["fastapi"] = fastapi_module
    sys.modules["fastapi.responses"] = fastapi_responses_module
    sys.modules["httpx"] = httpx_module
    sys.modules["itsdangerous"] = itsdangerous_module
    sys.modules["ldap3"] = ldap3_module
    sys.modules["ldap3.utils"] = ldap3_utils_module
    sys.modules["ldap3.utils.conv"] = ldap3_utils_conv_module
    sys.modules["uvicorn"] = uvicorn_module

    try:
        yield
    finally:
        for name, original_module in original_modules.items():
            if original_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original_module


class HermesAuthProxyTest(unittest.TestCase):
    def load_authproxy(self):
        module_name = "authproxy_under_test"
        sys.modules.pop(module_name, None)
        with mocked_authproxy_dependencies():
            return load_module(AUTHPROXY_PATH, module_name)

    def runtime_config(self, authproxy, **overrides):
        agent_record = authproxy.AgentRecord(
            agent_id=1,
            agent_name="Agent One",
            allowed_user="alice",
            status="start",
            upstream_url="http://10.0.2.2:20002",
        )
        values = {
            "user_domain": "example.org",
            "ldap_host": "ldap.example.org",
            "ldap_port": 389,
            "ldap_base_dn": "dc=example,dc=org",
            "ldap_schema": "rfc2307",
            "ldap_bind_dn": "",
            "ldap_bind_password": "",
            "session_secret": "test-secret",
            "agents_by_id": {1: agent_record},
            "agents_by_user": {"alice": agent_record},
        }
        values.update(overrides)
        return authproxy.RuntimeConfig(**values)

    def socket_runtime_config(self, authproxy, **overrides):
        agent_record = authproxy.AgentRecord(
            agent_id=1,
            agent_name="Agent One",
            allowed_user="alice",
            status="start",
            upstream_socket="/sockets/agent-1.sock",
        )
        values = {
            "user_domain": "example.org",
            "ldap_host": "ldap.example.org",
            "ldap_port": 389,
            "ldap_base_dn": "dc=example,dc=org",
            "ldap_schema": "rfc2307",
            "ldap_bind_dn": "",
            "ldap_bind_password": "",
            "session_secret": "test-secret",
            "agents_by_id": {1: agent_record},
            "agents_by_user": {"alice": agent_record},
        }
        values.update(overrides)
        return authproxy.RuntimeConfig(**values)

    def make_request(self, client, headers=None, cookies=None, path="/", query="", method="GET", body=b""):
        class FakeRequest:
            def __init__(self):
                self.method = method
                self.headers = headers or {}
                self.cookies = cookies or {}
                self.url = types.SimpleNamespace(path=path, query=query)
                self.app = types.SimpleNamespace(state=types.SimpleNamespace(client=client))
                self.client = types.SimpleNamespace(host="198.51.100.42")
                self._body = body

            async def body(self):
                return self._body

        return FakeRequest()

    def test_authproxy_uses_fastapi_lifespan(self):
        authproxy = self.load_authproxy()

        self.assertIsNotNone(authproxy.app.lifespan)

    def test_user_search_filter_uses_schema_safe_attributes(self):
        authproxy = self.load_authproxy()

        self.assertEqual(
            authproxy.user_search_filter("alice", "rfc2307"),
            "(|(uid=alice)(cn=alice)(mail=alice))",
        )
        self.assertEqual(
            authproxy.user_search_filter("alice", "ad"),
            "(|(sAMAccountName=alice)(userPrincipalName=alice)(uid=alice))",
        )

    def test_user_search_filter_escapes_special_characters(self):
        authproxy = self.load_authproxy()

        self.assertEqual(
            authproxy.user_search_filter("ali*(ce)", "rfc2307"),
            "(|(uid=ali\\2a\\28ce\\29)(cn=ali\\2a\\28ce\\29)(mail=ali\\2a\\28ce\\29))",
        )

    def test_proxy_logs_successful_form_authentication(self):
        authproxy = self.load_authproxy()
        config = self.runtime_config(authproxy)

        class FakeUpstreamClient:
            async def request(self, *args, **kwargs):
                raise AssertionError("login should not proxy to upstream")

        request = self.make_request(
            FakeUpstreamClient(),
            headers={"content-type": "application/x-www-form-urlencoded", "x-forwarded-proto": "https"},
            path="/login",
            method="POST",
            body=b"username=alice&password=secret&next=%2Ffoo",
        )

        with mock.patch.object(authproxy, "load_config", return_value=config), mock.patch.object(
            authproxy,
            "authenticate_credentials",
            return_value=True,
        ), mock.patch.object(authproxy.LOGGER, "info") as log_info:
            response = asyncio.run(authproxy.proxy("", request))

        self.assertEqual(response.kwargs["status_code"], 303)
        self.assertEqual(response.args[0], "/foo")
        self.assertEqual(response.cookie_kwargs["path"], "/")
        self.assertTrue(response.cookie_kwargs["secure"])
        logged_messages = [call.args[0] for call in log_info.call_args_list]
        self.assertEqual(len(logged_messages), 2)
        self.assertIn("event=auth_attempt", logged_messages[0])
        self.assertIn("auth_method=form", logged_messages[0])
        self.assertIn("user=alice", logged_messages[0])
        self.assertIn("event=auth_success", logged_messages[1])
        self.assertIn("auth_method=form", logged_messages[1])
        self.assertIn("user=alice", logged_messages[1])

    def test_proxy_logs_failed_authentication(self):
        authproxy = self.load_authproxy()
        config = self.runtime_config(authproxy)

        class FakeUpstreamClient:
            async def request(self, *args, **kwargs):
                raise AssertionError("upstream should not be called when auth fails")

        request = self.make_request(
            FakeUpstreamClient(),
            headers={"content-type": "application/x-www-form-urlencoded"},
            path="/hermes-1",
            method="POST",
            body=b"username=alice&password=wrong&next=%2F",
        )

        with mock.patch.object(authproxy, "load_config", return_value=config), mock.patch.object(
            authproxy,
            "authenticate_credentials",
            return_value=False,
        ), mock.patch.object(authproxy.LOGGER, "info") as log_info:
            response = asyncio.run(authproxy.proxy("", request))

        self.assertEqual(response.kwargs["status_code"], 401)
        logged_messages = [call.args[0] for call in log_info.call_args_list]
        self.assertEqual(len(logged_messages), 2)
        self.assertIn("event=auth_attempt", logged_messages[0])
        self.assertIn("event=auth_failed", logged_messages[1])
        self.assertIn("detail=invalid_credentials_or_assignment", logged_messages[1])

    def test_proxy_returns_502_when_upstream_read_fails(self):
        authproxy = self.load_authproxy()
        config = self.runtime_config(authproxy)

        class FakeUpstreamClient:
            async def request(self, *args, **kwargs):
                del args, kwargs
                raise authproxy.httpx.ReadError("connection reset by peer")

        request = self.make_request(
            FakeUpstreamClient(),
            headers={"x-forwarded-proto": "https"},
            cookies={
                authproxy.SESSION_COOKIE: json.dumps(
                    {
                        "allowed_user": "alice",
                        "user_domain": config.user_domain,
                        "agent_id": 1,
                    }
                )
            },
            path="/",
            method="GET",
        )

        with mock.patch.object(authproxy, "load_config", return_value=config), mock.patch.object(
            authproxy.LOGGER, "info"
        ) as log_info:
            response = asyncio.run(authproxy.proxy("", request))

        self.assertEqual(response.kwargs["status_code"], 502)
        self.assertEqual(response.args[0], "Assigned dashboard is temporarily unavailable.")
        logged_messages = [call.args[0] for call in log_info.call_args_list]
        self.assertEqual(len(logged_messages), 2)
        self.assertIn("event=auth_success", logged_messages[0])
        self.assertIn("event=proxy_failed", logged_messages[1])
        self.assertIn("agent_id=1", logged_messages[1])
        self.assertIn("detail=FakeReadError:connection reset by peer", logged_messages[1])

    def test_proxy_logs_received_and_forwarded_requests_when_debug_enabled(self):
        authproxy = self.load_authproxy()
        config = self.runtime_config(authproxy)

        class FakeUpstreamResponse:
            def __init__(self):
                self.content = b"ok"
                self.status_code = 200
                self.headers = {}

        class FakeUpstreamClient:
            async def request(self, *args, **kwargs):
                del args, kwargs
                return FakeUpstreamResponse()

        request = self.make_request(
            FakeUpstreamClient(),
            headers={"x-forwarded-proto": "https"},
            cookies={
                authproxy.SESSION_COOKIE: json.dumps(
                    {
                        "allowed_user": "alice",
                        "user_domain": config.user_domain,
                        "agent_id": 1,
                    }
                )
            },
            path="/api/status",
            query="verbose=1",
            method="GET",
        )

        with mock.patch.dict(os.environ, {"DEBUG": "1"}, clear=False), mock.patch.object(
            authproxy, "load_config", return_value=config
        ), mock.patch.object(authproxy.LOGGER, "info") as log_info:
            response = asyncio.run(authproxy.proxy("api/status", request))

        self.assertEqual(response.kwargs["status_code"], 200)
        logged_messages = [call.args[0] for call in log_info.call_args_list]
        self.assertEqual(len(logged_messages), 3)
        self.assertIn("event=request_received", logged_messages[0])
        self.assertIn("path=/api/status", logged_messages[0])
        self.assertIn("event=auth_success", logged_messages[1])
        self.assertIn("event=proxy_forward", logged_messages[2])
        self.assertIn("agent_id=1", logged_messages[2])
        self.assertIn("detail=upstream_url=http://10.0.2.2:20002/api/status?verbose=1", logged_messages[2])

    def test_load_agent_registry_accepts_unix_socket_upstreams(self):
        authproxy = self.load_authproxy()

        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "authproxy_agents.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "agents": [
                            {
                                "id": 1,
                                "name": "Agent One",
                                "allowed_user": "alice",
                                "status": "start",
                                "upstream_socket": "/sockets/agent-1.sock",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            agents_by_id, agents_by_user = authproxy.load_agent_registry(str(registry_path))

        self.assertEqual(agents_by_id[1].upstream_socket, "/sockets/agent-1.sock")
        self.assertEqual(agents_by_id[1].upstream_origin, "http://agent-1")
        self.assertEqual(agents_by_user["alice"].agent_id, 1)

    def test_proxy_uses_unix_socket_upstream_when_configured(self):
        authproxy = self.load_authproxy()
        config = self.socket_runtime_config(authproxy)

        class FakeUpstreamResponse:
            def __init__(self):
                self.content = b"ok"
                self.status_code = 200
                self.headers = {"location": "http://agent-1/settings"}

        class FakeUdsClient:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs
                self.calls = []

            async def request(self, *args, **kwargs):
                self.calls.append({"args": args, "kwargs": kwargs})
                return FakeUpstreamResponse()

            async def aclose(self):
                return None

        uds_clients = []

        def build_fake_client(*args, **kwargs):
            client = FakeUdsClient(*args, **kwargs)
            uds_clients.append(client)
            return client

        request = self.make_request(
            types.SimpleNamespace(),
            headers={"x-forwarded-proto": "https"},
            cookies={
                authproxy.SESSION_COOKIE: json.dumps(
                    {
                        "allowed_user": "alice",
                        "user_domain": config.user_domain,
                        "agent_id": 1,
                    }
                )
            },
            path="/api/status",
            query="verbose=1",
            method="GET",
        )

        with mock.patch.object(authproxy, "load_config", return_value=config), mock.patch.object(
            authproxy.httpx,
            "AsyncClient",
            side_effect=build_fake_client,
        ), mock.patch.object(
            authproxy.httpx,
            "AsyncHTTPTransport",
            side_effect=lambda **kwargs: types.SimpleNamespace(**kwargs),
        ):
            response = asyncio.run(authproxy.proxy("api/status", request))

        self.assertEqual(response.kwargs["status_code"], 200)
        self.assertEqual(len(uds_clients), 1)
        self.assertEqual(uds_clients[0].kwargs["transport"].uds, "/sockets/agent-1.sock")
        self.assertEqual(uds_clients[0].calls[0]["kwargs"]["url"], "http://agent-1/api/status?verbose=1")
        self.assertEqual(response.kwargs["headers"]["location"], "/settings")

    def test_proxy_preserves_dashboard_authorization_and_sets_custom_user_header(self):
        authproxy = self.load_authproxy()
        config = self.runtime_config(authproxy)

        class FakeUpstreamResponse:
            def __init__(self):
                self.content = b"ok"
                self.status_code = 200
                self.headers = {}

        class FakeUpstreamClient:
            def __init__(self):
                self.calls = []

            async def request(self, *args, **kwargs):
                self.calls.append({"args": args, "kwargs": kwargs})
                return FakeUpstreamResponse()

        upstream_client = FakeUpstreamClient()
        request = self.make_request(
            upstream_client,
            headers={
                "Authorization": "Bearer dashboard-token",
                authproxy.AUTHENTICATED_USER_HEADER: "spoofed-user",
                "host": "agents.example.org",
                "x-forwarded-proto": "https",
            },
            cookies={
                authproxy.SESSION_COOKIE: json.dumps(
                    {
                        "allowed_user": "alice",
                        "user_domain": config.user_domain,
                        "agent_id": 1,
                    }
                ),
                "dashboard_cookie": "session-cookie",
            },
            path="/api/status",
            method="GET",
        )

        with mock.patch.object(authproxy, "load_config", return_value=config):
            response = asyncio.run(authproxy.proxy("api/status", request))

        self.assertEqual(response.kwargs["status_code"], 200)
        self.assertEqual(len(upstream_client.calls), 1)
        upstream_headers = upstream_client.calls[0]["kwargs"]["headers"]
        self.assertEqual(upstream_headers["Authorization"], "Bearer dashboard-token")
        self.assertEqual(upstream_headers["Host"], "127.0.0.1:9120")
        self.assertEqual(upstream_headers[authproxy.AUTHENTICATED_USER_HEADER], "alice")
        self.assertEqual(upstream_headers["Cookie"], "dashboard_cookie=session-cookie")


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
                    Path("agents") / str(index) / "metadata.json",
                    {
                        "id": index,
                        "name": "Valid Name",
                        "role": role,
                        "status": "start",
                        "allowed_user": "",
                    },
                )

            agents = self.state.read_agents_from_state()

        self.assertEqual([agent_data["role"] for agent_data in agents], list(self.state.ALLOWED_ROLES))

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
                        "allowed_user": "alice",
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
                    Path("agents") / "1" / "metadata.json",
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
                    Path("agents") / "1" / "metadata.json",
                    {
                        "id": 0,
                        "name": "Valid Name",
                        "role": "default",
                        "status": "start",
                        "allowed_user": "",
                    },
                )
                self.state.read_agents_from_state()

    def test_read_agents_from_state_rejects_id_above_supported_limit(self):
        with self.assertRaisesRegex(ValueError, "invalid id"):
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    Path("agents") / "1" / "metadata.json",
                    {
                        "id": 31,
                        "name": "Valid Name",
                        "role": "default",
                        "status": "start",
                        "allowed_user": "",
                    },
                )
                self.state.read_agents_from_state()

    def test_read_agents_from_state_normalizes_missing_and_present_allowed_user(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                Path("agents") / "1" / "metadata.json",
                {
                    "id": 1,
                    "name": "One Agent",
                    "role": "developer",
                    "status": "start",
                },
            )
            self.state.write_jsonfile(
                Path("agents") / "2" / "metadata.json",
                {
                    "id": 2,
                    "name": "Two Agent",
                    "role": "researcher",
                    "status": "stop",
                    "allowed_user": " alice ",
                },
            )

            agents = self.state.read_agents_from_state()

        self.assertEqual(agents[0]["allowed_user"], "")
        self.assertEqual(agents[1]["allowed_user"], "alice")

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

    def test_shared_route_instance_name_preserves_contract(self):
        self.assertEqual(
            self.state.shared_route_instance_name(module_id="hermes-agent1"),
            "hermes-agent1-hermes-auth",
        )

    def test_service_templates_keep_runtime_contract(self):
        service_template = SERVICE_TEMPLATE_PATH.read_text(encoding="utf-8")
        auth_template = AUTH_SERVICE_TEMPLATE_PATH.read_text(encoding="utf-8")
        pod_template = POD_SERVICE_TEMPLATE_PATH.read_text(encoding="utf-8")
        socket_template = SOCKET_SERVICE_TEMPLATE_PATH.read_text(encoding="utf-8")

        self.assertIn("Restart=on-failure", service_template)
        self.assertNotIn("Restart=always", service_template)
        self.assertNotIn("EnvironmentFile=-%S/state/hosts", service_template)
        self.assertNotIn("$PODMAN_ADD_HOST_ARGS", service_template)
        self.assertNotIn("--restart=always", service_template)
        self.assertNotIn("hermes-auth@%i.service", service_template)
        self.assertIn("--pod hermes-pod-%i", service_template)
        self.assertIn("--name hermes-%i", service_template)
        self.assertIn("--volume hermes-agent-%i-home:/opt/data", service_template)
        self.assertNotIn("--volume %S/state/agents/%i/home:/opt/data:Z", service_template)
        self.assertIn("--env-file %S/state/agent_%i.env", service_template)
        self.assertIn("ensure-agent-home-ownership --agent-id %i", service_template)
        self.assertIn("--env-file %S/state/agent_%i_secrets.env", service_template)
        self.assertIn("API_SERVER_ENABLED=true", service_template)
        self.assertIn("dashboard --host 127.0.0.1 --port 9120 --insecure --no-open -- gateway run", service_template)
        self.assertIn("gateway run", service_template)
        self.assertNotIn("seed-agent-home", service_template)

        self.assertIn("Description=Hermes shared auth proxy", auth_template)
        self.assertIn("--name hermes-auth", auth_template)
        self.assertIn("--network=slirp4netns:allow_host_loopback=true", auth_template)
        self.assertIn("--publish 127.0.0.1:${TCP_PORT}:9119", auth_template)
        self.assertIn("install -d -m 0770 %S/state/dashboard-sockets", auth_template)
        self.assertIn("EnvironmentFile=-%S/state/authproxy.env", auth_template)
        self.assertIn("--env-file %S/state/authproxy.env", auth_template)
        self.assertIn("--env-file %S/state/authproxy_secrets.env", auth_template)
        self.assertIn("AUTH_PROXY_AGENT_REGISTRY=/app/authproxy_agents.json", auth_template)
        self.assertIn("AUTH_PROXY_PORT=9119", auth_template)
        self.assertIn("--volume %S/state/dashboard-sockets:/sockets:z", auth_template)
        self.assertIn("${HERMES_AGENT_AUTH_IMAGE}", auth_template)
        self.assertIn("python /app/authproxy.py", auth_template)

        self.assertIn("Type=oneshot", pod_template)
        self.assertIn("RemainAfterExit=yes", pod_template)
        self.assertNotIn("hermes-auth@%i.service", pod_template)
        self.assertIn("--name hermes-pod-%i", pod_template)
        self.assertNotIn("--publish 127.0.0.1:${AGENT_DASHBOARD_HOST_PORT}:9120", pod_template)

        self.assertIn("Description=Hermes dashboard unix socket sidecar %i", socket_template)
        self.assertIn("Requires=hermes-pod@%i.service hermes@%i.service", socket_template)
        self.assertIn("PartOf=hermes@%i.service", socket_template)
        self.assertIn("install -d -m 0770 %S/state/dashboard-sockets", socket_template)
        self.assertIn("--name hermes-socket-%i", socket_template)
        self.assertIn("--pod hermes-pod-%i", socket_template)
        self.assertIn("--volume %S/state/dashboard-sockets:/sockets:z", socket_template)
        self.assertIn("${HERMES_AGENT_SOCKET_IMAGE}", socket_template)
        self.assertIn("UNIX-LISTEN:/sockets/agent-%i.sock,fork,unlink-early,mode=0660", socket_template)
        self.assertIn("TCP-CONNECT:127.0.0.1:9120", socket_template)

    def test_hermes_containerfile_uses_expected_base_image(self):
        containerfile = HERMES_CONTAINERFILE_PATH.read_text(encoding="utf-8")

        self.assertIn("FROM docker.io/nousresearch/hermes-agent:v2026.4.23", containerfile)
        self.assertNotIn("FROM docker.io/node:24.11.1-slim AS dashboard-builder", containerfile)
        self.assertNotIn("COPY patch_dashboard_source.py /opt/hermes/patch_dashboard_source.py", containerfile)
        self.assertNotIn("ns8-web-dist", containerfile)

    def test_auth_containerfile_installs_proxy_runtime(self):
        containerfile = AUTH_CONTAINERFILE_PATH.read_text(encoding="utf-8")

        self.assertIn("FROM docker.io/python:3.12-slim", containerfile)
        self.assertIn('org.opencontainers.image.title="hermes-agent-auth"', containerfile)
        self.assertIn("fastapi==0.115.12", containerfile)
        self.assertIn("ldap3==2.9.1", containerfile)
        self.assertIn("COPY authproxy.py /app/authproxy.py", containerfile)

    def test_socket_containerfile_installs_relay_runtime(self):
        containerfile = SOCKET_CONTAINERFILE_PATH.read_text(encoding="utf-8")

        self.assertIn("FROM docker.io/alpine:3.21", containerfile)
        self.assertIn('org.opencontainers.image.title="hermes-agent-socket"', containerfile)
        self.assertIn("apk add --no-cache socat", containerfile)
        self.assertIn('ENTRYPOINT ["/usr/bin/socat"]', containerfile)

    def test_build_images_script_publishes_socket_image_and_one_tcp_port(self):
        build_script = BUILD_IMAGES_PATH.read_text(encoding="utf-8")

        self.assertIn('"${repobase}/hermes-agent-socket:${imagetag}"', build_script)
        self.assertIn('build_component_image "hermes-agent-socket" "containers/socket"', build_script)
        self.assertIn('--label="org.nethserver.tcp-ports-demand=1"', build_script)

    def test_hermes_entrypoint_keeps_absolute_virtualenv_activation(self):
        entrypoint = HERMES_ENTRYPOINT_PATH.read_text(encoding="utf-8")

        self.assertIn('source "${INSTALL_DIR}/.venv/bin/activate"', entrypoint)
        self.assertNotIn("source .venv/bin/activate", entrypoint)
        self.assertIn('BUILT_WEB_DIST="${INSTALL_DIR}/hermes_cli/web_dist"', entrypoint)
        self.assertIn('export HERMES_WEB_DIST="$BUILT_WEB_DIST"', entrypoint)
        self.assertNotIn("PATCH_SCRIPT", entrypoint)
        self.assertNotIn("npm run build", entrypoint)
        self.assertNotIn("window.__HERMES_BASE_URL__", entrypoint)

    def test_dashboard_patch_script_removed_from_wrapper(self):
        self.assertFalse(HERMES_DASHBOARD_PATCH_PATH.exists())

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
            os.symlink("outside.env", Path("agent_5.env"))

            with self.assertRaisesRegex(ValueError, "unsafe file path"):
                self.state.write_private_textfile(Path("agent_5.env"), "AGENT_NAME=Blocked\n")

            self.assertEqual(Path("outside.env").read_text(encoding="utf-8"), "SAFE=1\n")

    def test_sync_agent_runtime_files_writes_public_env_and_secrets(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                Path("agents") / "1" / "metadata.json",
                {
                    "id": 1,
                    "name": "Alice User",
                    "role": "developer",
                    "status": "start",
                    "allowed_user": "alice",
                },
            )
            write_envfile(
                self.state.ENVIRONMENT_FILE,
                {
                    "TIMEZONE": "UTC",
                    "BASE_VIRTUALHOST": "agents.example.org",
                    "USER_DOMAIN": "example.org",
                    "SMTP_ENABLED": "1",
                    "SMTP_HOST": "smtp.example.org",
                },
            )
            write_envfile(self.state.SHARED_SECRETS_ENVFILE, {"SMTP_PASSWORD": "secret-pass"})

            with mocked_ldap_modules(
                domains={
                    "example.org": {
                        "domain_name": "example.org",
                        "host": "127.0.0.1",
                        "port": 389,
                        "base_dn": "dc=example,dc=org",
                        "schema": "rfc2307",
                        "bind_dn": "cn=ldapservice,dc=example,dc=org",
                        "bind_password": "ldap-secret",
                    }
                },
                users_by_domain={
                    "example.org": [
                        {"user": "alice", "display_name": "Alice User", "locked": False}
                    ]
                },
            ), mock.patch.object(self.sync.agent, "read_envfile", side_effect=read_envfile, create=True), mock.patch.object(
                self.sync.agent,
                "write_envfile",
                side_effect=write_envfile,
                create=True,
            ):
                self.sync.sync_agent_runtime_files()

            public_env = read_envfile(Path("agent_1.env"))
            agent_secrets = read_envfile(Path("agent_1_secrets.env"))
            authproxy_env = read_envfile(Path("authproxy.env"))
            authproxy_secrets = read_envfile(Path("authproxy_secrets.env"))
            authproxy_agents = json.loads(Path("authproxy_agents.json").read_text(encoding="utf-8"))
            shared_secrets = read_envfile(self.state.SHARED_SECRETS_ENVFILE)

            self.assertEqual(public_env["AGENT_NAME"], "Alice User")
            self.assertEqual(public_env["AGENT_ROLE"], "developer")
            self.assertEqual(public_env["AGENT_ALLOWED_USER"], "alice")
            self.assertEqual(public_env["SMTP_HOST"], "smtp.example.org")
            self.assertEqual(public_env["USER_DOMAIN"], "example.org")
            self.assertEqual(public_env["LDAP_HOST"], "10.0.2.2")
            self.assertEqual(public_env["LDAP_PORT"], "389")
            self.assertEqual(public_env["LDAP_BASE_DN"], "dc=example,dc=org")
            self.assertEqual(public_env["LDAP_SCHEMA"], "rfc2307")
            self.assertEqual(
                set(public_env),
                {
                    "AGENT_ALLOWED_USER",
                    "AGENT_ID",
                    "AGENT_NAME",
                    "AGENT_ROLE",
                    "BASE_VIRTUALHOST",
                    "LDAP_BASE_DN",
                    "LDAP_HOST",
                    "LDAP_PORT",
                    "LDAP_SCHEMA",
                    "SMTP_ENABLED",
                    "SMTP_HOST",
                    "TIMEZONE",
                    "TZ",
                    "USER_DOMAIN",
                },
            )
            self.assertEqual(agent_secrets["LDAP_BIND_DN"], "cn=ldapservice,dc=example,dc=org")
            self.assertEqual(agent_secrets["LDAP_BIND_PASSWORD"], "ldap-secret")
            self.assertEqual(agent_secrets["SMTP_PASSWORD"], "secret-pass")
            self.assertTrue(agent_secrets["HERMES_AGENT_SECRET"])
            self.assertEqual(
                set(agent_secrets),
                {"HERMES_AGENT_SECRET", "LDAP_BIND_DN", "LDAP_BIND_PASSWORD", "SMTP_PASSWORD"},
            )
            self.assertEqual(authproxy_env["USER_DOMAIN"], "example.org")
            self.assertEqual(authproxy_env["LDAP_HOST"], "10.0.2.2")
            self.assertEqual(authproxy_secrets["LDAP_BIND_DN"], "cn=ldapservice,dc=example,dc=org")
            self.assertTrue(authproxy_secrets["HERMES_AUTH_SESSION_SECRET"])
            self.assertEqual(
                authproxy_agents,
                {
                    "agents": [
                        {
                            "id": 1,
                            "name": "Alice User",
                            "allowed_user": "alice",
                            "status": "start",
                            "upstream_socket": "/sockets/agent-1.sock",
                        }
                    ]
                },
            )
            self.assertEqual(shared_secrets["SMTP_PASSWORD"], "secret-pass")
            self.assertTrue(shared_secrets["HERMES_AUTH_SESSION_SECRET"])
            self.assertEqual(
                sorted(path.name for path in Path(".").glob("agent_1*.env")),
                ["agent_1.env", "agent_1_secrets.env"],
            )
            self.assertFalse((Path("agents") / "1" / "home").exists())

    def test_sync_agent_runtime_files_creates_missing_agent_secrets_envfile(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                Path("agents") / "1" / "metadata.json",
                {
                    "id": 1,
                    "name": "Alice User",
                    "role": "developer",
                    "status": "start",
                    "allowed_user": "",
                },
            )
            write_envfile(
                self.state.ENVIRONMENT_FILE,
                {
                    "TIMEZONE": "UTC",
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

            public_env = read_envfile(Path("agent_1.env"))
            agent_secrets = read_envfile(Path("agent_1_secrets.env"))

            self.assertEqual(public_env["AGENT_NAME"], "Alice User")
            self.assertEqual(agent_secrets["SMTP_PASSWORD"], "secret-pass")
            self.assertTrue(agent_secrets["HERMES_AGENT_SECRET"])
            self.assertTrue(read_envfile(Path("authproxy_secrets.env"))["HERMES_AUTH_SESSION_SECRET"])

    def test_sync_agent_runtime_files_preserves_generated_agent_secret_on_rerun(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                Path("agents") / "3" / "metadata.json",
                {
                    "id": 3,
                    "name": "Carol Agent",
                    "role": "researcher",
                    "status": "start",
                    "allowed_user": "",
                },
            )
            write_envfile(
                self.state.ENVIRONMENT_FILE,
                {"TIMEZONE": "UTC"},
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
                first_sync_secrets = read_envfile(Path("agent_3_secrets.env"))

                write_envfile(self.state.SHARED_SECRETS_ENVFILE, {"SMTP_PASSWORD": "new-pass"})
                self.sync.sync_agent_runtime_files(agent_id=3)

            agent_secrets = read_envfile(Path("agent_3_secrets.env"))
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
                Path("agent_1.env"),
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
            self.assertIn("hermes-agent-1-home:/opt/data:z", command)
            self.assertIn(f"{(ROOT / 'imageroot' / 'templates').resolve()}:/templates:ro,z", command)
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


    def test_ensure_agent_home_ownership_uses_image_hermes_uid(self):
        with mock.patch.dict(
            os.environ,
            {"HERMES_AGENT_HERMES_IMAGE": "quay.io/example/hermes:test"},
            clear=False,
        ), mock.patch("sys.argv", [str(ENSURE_AGENT_HOME_OWNERSHIP_PATH), "--agent-id", "2"]), mock.patch(
            "subprocess.run"
        ) as run_mock, self.assertRaises(SystemExit) as exit_context:
            runpy.run_path(str(ENSURE_AGENT_HOME_OWNERSHIP_PATH), run_name="__main__")

        self.assertEqual(exit_context.exception.code, 0)
        command = run_mock.call_args.args[0]
        self.assertIn("podman", command)
        self.assertIn("run", command)
        self.assertIn("--user", command)
        self.assertEqual(command[command.index("--user") + 1], "root")
        self.assertIn("--entrypoint", command)
        self.assertEqual(command[command.index("--entrypoint") + 1], "/bin/sh")
        self.assertIn("hermes-agent-2-home:/opt/data:z", command)
        self.assertIn("quay.io/example/hermes:test", command)
        ownership_script = command[-1]
        self.assertIn("id -u hermes", ownership_script)
        self.assertIn("id -g hermes", ownership_script)
        self.assertIn("chown -R", ownership_script)
        self.assertNotIn("10000", ownership_script)

    def test_update_module_script_repairs_known_agent_home_ownership_before_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                Path("agents") / "1" / "metadata.json",
                {"id": 1, "name": "One", "role": "developer", "status": "start"},
            )
            write_envfile("agent_3.env", {"AGENT_ID": "3"})

            with mock.patch("subprocess.run", side_effect=lambda *args, **kwargs: types.SimpleNamespace(returncode=0)) as run_mock:
                runpy.run_path(str(UPDATE_OWNERSHIP_SCRIPT_PATH), run_name="__main__")

            logged_commands = [call.args[0] for call in run_mock.call_args_list]
            self.assertEqual(
                logged_commands,
                [
                    ["systemctl", "--user", "is-active", "--quiet", "hermes@1.service"],
                    ["systemctl", "--user", "stop", "hermes-socket@1.service"],
                    ["systemctl", "--user", "stop", "hermes@1.service"],
                    ["runagent", "ensure-agent-home-ownership", "--agent-id", "1"],
                    ["systemctl", "--user", "start", "hermes@1.service"],
                    ["systemctl", "--user", "start", "hermes-socket@1.service"],
                    ["systemctl", "--user", "is-active", "--quiet", "hermes@3.service"],
                    ["systemctl", "--user", "stop", "hermes-socket@3.service"],
                    ["systemctl", "--user", "stop", "hermes@3.service"],
                    ["runagent", "ensure-agent-home-ownership", "--agent-id", "3"],
                    ["systemctl", "--user", "start", "hermes@3.service"],
                    ["systemctl", "--user", "start", "hermes-socket@3.service"],
                ],
            )
            ensure_indexes = [
                index
                for index, call in enumerate(run_mock.call_args_list)
                if call.args[0][:2] == ["runagent", "ensure-agent-home-ownership"]
            ]
            self.assertEqual(ensure_indexes, [3, 9])
            for index, call in enumerate(run_mock.call_args_list):
                self.assertEqual(call.kwargs.get("check"), index in ensure_indexes)

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
                    Path("agents") / "1" / "metadata.json",
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
                        "TCP_PORT": "20001",
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
                                "instance": "hermes-agent1-hermes-auth",
                                "lets_encrypt_cleanup": True,
                            },
                        ),
                        mock.call(
                            agent_id="module/traefik1",
                            action="set-route",
                            data={
                                "instance": "hermes-agent1-hermes-auth",
                                "url": "http://127.0.0.1:20001",
                                "host": "new.example.org",
                                "http2https": True,
                                "lets_encrypt": True,
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
                    Path("agents") / "1" / "metadata.json",
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
                        "TCP_PORT": "20001",
                        self.state.BASE_VIRTUALHOST_ENV: "agents.example.org",
                        self.state.LETS_ENCRYPT_ENV: "false",
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
                            action="set-route",
                            data={
                                "instance": "hermes-agent1-hermes-auth",
                                "url": "http://127.0.0.1:20001",
                                "host": "agents.example.org",
                                "http2https": True,
                                "lets_encrypt": False,
                                "lets_encrypt_cleanup": True,
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

    def test_remove_deleted_routes_is_a_noop(self):
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
                    Path("agents") / "1" / "metadata.json",
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

    def test_sync_agent_runtime_files_preserves_existing_agent_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                Path("agents") / "3" / "metadata.json",
                {"id": 3, "name": "Carol Agent", "role": "researcher", "status": "start"},
            )
            write_envfile(
                self.state.ENVIRONMENT_FILE,
                {"TIMEZONE": "UTC"},
            )
            write_envfile(
                Path("agent_3_secrets.env"),
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

            agent_secrets = read_envfile(Path("agent_3_secrets.env"))
            self.assertEqual(agent_secrets["HERMES_AGENT_SECRET"], "preserved")
            self.assertEqual(agent_secrets["SMTP_PASSWORD"], "new-pass")
            self.assertEqual(set(agent_secrets), {"HERMES_AGENT_SECRET", "SMTP_PASSWORD"})

    def test_configure_module_reconciles_removed_and_started_agents(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock(side_effect=set_env_side_effect))
        setattr(agent_stub, "unset_env", mock.Mock(side_effect=unset_env_side_effect))
        setattr(agent_stub, "bind_user_domains", mock.Mock(return_value=True))
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    Path("agents") / "2" / "metadata.json",
                    {"id": 2, "name": "Old Agent", "role": "default", "status": "stop"},
                )
                write_envfile(Path("agent_2.env"), {"AGENT_NAME": "Old Agent"})
                write_envfile(
                    Path("agent_2_secrets.env"),
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
                        "user_domain": "",
                        "agents": [
                            {
                                "id": 1,
                                "name": "New Agent",
                                "role": "developer",
                                "status": "start",
                                "allowed_user": "",
                            }
                        ]
                    }
                )

                with mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TIMEZONE": "UTC",
                        "HERMES_AGENT_HERMES_IMAGE": "quay.io/example/hermes:test",
                    },
                    clear=False,
                ), mock.patch("subprocess.run", side_effect=run_side_effect) as run_command:
                    run_action(CONFIGURE_MODULE_ACTION_DIR, request)

                self.assertEqual(
                    self.state.read_jsonfile(Path("agents") / "1" / "metadata.json"),
                    {
                        "id": 1,
                        "name": "New Agent",
                        "role": "developer",
                        "status": "start",
                        "allowed_user": "",
                    },
                )
                self.assertFalse((Path("agents") / "2").exists())
                self.assertFalse(Path("agent_2.env").exists())
                self.assertFalse(Path("agent_2_secrets.env").exists())
                agent_stub.set_env.assert_not_called()
                agent_stub.bind_user_domains.assert_called_once_with([])
                command_list = [call.args[0] for call in run_command.call_args_list]
                self.assertEqual(
                    command_list[:6],
                    [
                        ["systemctl", "--user", "disable", "--now", "hermes-socket@2.service"],
                        ["systemctl", "--user", "disable", "--now", "hermes@2.service"],
                        ["systemctl", "--user", "stop", "hermes-pod@2.service"],
                        ["podman", "pod", "rm", "--force", "hermes-pod-2"],
                        ["podman", "rm", "--force", "hermes-2"],
                        ["podman", "rm", "--force", "hermes-socket-2"],
                    ],
                )
                self.assertEqual(
                    command_list[6:9],
                    [
                        ["runagent", "remove-agent-state", "--agent-id", "2"],
                        ["podman", "volume", "exists", "hermes-agent-2-home"],
                        ["podman", "volume", "rm", "--force", "hermes-agent-2-home"],
                    ],
                )
                self.assertIn(["runagent", "discover-smarthost"], command_list)
                self.assertIn(["runagent", "sync-agent-runtime"], command_list)
                self.assertIn(["systemctl", "--user", "daemon-reload"], command_list)
                self.assertIn(["systemctl", "--user", "enable", "hermes@1.service"], command_list)
                self.assertIn(["systemctl", "--user", "enable", "hermes-socket@1.service"], command_list)
                self.assertIn(["systemctl", "--user", "stop", "hermes-socket@1.service"], command_list)
                self.assertIn(["systemctl", "--user", "stop", "hermes@1.service"], command_list)
                self.assertIn(["systemctl", "--user", "start", "hermes-socket@1.service"], command_list)
                self.assertIn(["systemctl", "--user", "start", "hermes@1.service"], command_list)
                self.assertIn(["systemctl", "--user", "disable", "--now", "hermes-auth.service"], command_list)
                self.assertIn(["podman", "rm", "--force", "hermes-auth"], command_list)
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
        setattr(agent_stub, "bind_user_domains", mock.Mock(return_value=True))
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
                        "TCP_PORT": "20001",
                    },
                )

                request = json.dumps(
                    {
                        "base_virtualhost": "agents.example.org",
                        "user_domain": "example.org",
                        "lets_encrypt": True,
                        "agents": [
                            {
                                "id": 1,
                                "name": "Route Agent",
                                "role": "developer",
                                "status": "start",
                                "allowed_user": "alice",
                            }
                        ],
                    }
                )

                with mocked_ldap_modules(
                    domains={
                        "example.org": {
                            "domain_name": "example.org",
                            "host": "127.0.0.1",
                            "port": 389,
                            "base_dn": "dc=example,dc=org",
                            "schema": "rfc2307",
                            "bind_dn": "cn=ldapservice,dc=example,dc=org",
                            "bind_password": "ldap-secret",
                        }
                    },
                    users_by_domain={
                        "example.org": [
                            {"user": "alice", "display_name": "Alice User", "locked": False}
                        ]
                    },
                ), mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TIMEZONE": "UTC",
                        "TCP_PORT": "20001",
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
                self.assertIn(mock.call("USER_DOMAIN", "example.org"), agent_stub.set_env.call_args_list)
                self.assertIn(mock.call("LETS_ENCRYPT", "true"), agent_stub.set_env.call_args_list)
                agent_stub.bind_user_domains.assert_called_once_with(["example.org"])
                agent_stub.resolve_agent_id.assert_called_once_with("traefik@node")
                self.assertEqual(
                    agent_tasks_stub.run.call_args_list,
                    [
                        mock.call(
                            agent_id="module/traefik1",
                            action="set-route",
                            data={
                                "instance": "hermes-agent1-hermes-auth",
                                "url": "http://127.0.0.1:20001",
                                "host": "agents.example.org",
                                "http2https": True,
                                "lets_encrypt": True,
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

    def test_configure_module_with_empty_virtualhost_does_not_require_traefik(self):
        original_agent = sys.modules.get("agent")
        original_agent_tasks = sys.modules.get("agent.tasks")
        agent_tasks_stub = types.ModuleType("agent.tasks")
        setattr(agent_tasks_stub, "run", mock.Mock(return_value={"exit_code": 0}))

        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_env", mock.Mock(side_effect=set_env_side_effect))
        setattr(agent_stub, "unset_env", mock.Mock(side_effect=unset_env_side_effect))
        setattr(agent_stub, "bind_user_domains", mock.Mock(return_value=True))
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
                        "user_domain": "",
                        "agents": [
                            {
                                "id": 1,
                                "name": "Route Agent",
                                "role": "developer",
                                "status": "start",
                                "allowed_user": "",
                            }
                        ],
                    }
                )

                with mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TIMEZONE": "UTC",
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
                agent_stub.bind_user_domains.assert_called_once_with([])
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
        setattr(agent_stub, "bind_user_domains", mock.Mock(return_value=True))
        setattr(agent_stub, "resolve_agent_id", mock.Mock(return_value="module/traefik1"))
        setattr(agent_stub, "assert_exp", mock.Mock())
        setattr(agent_stub, "tasks", agent_tasks_stub)
        sys.modules["agent"] = agent_stub
        sys.modules["agent.tasks"] = agent_tasks_stub

        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.write_jsonfile(
                    Path("agents") / "2" / "metadata.json",
                    {"id": 2, "name": "Old Agent", "role": "default", "status": "stop"},
                )
                write_envfile(Path("agent_2.env"), {"AGENT_NAME": "Old Agent"})
                write_envfile(
                    Path("agent_2_secrets.env"),
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
                        "user_domain": "",
                        "agents": [
                            {
                                "id": 1,
                                "name": "New Agent",
                                "role": "developer",
                                "status": "start",
                                "allowed_user": "",
                            }
                        ],
                    }
                )

                with mock.patch.dict(
                    os.environ,
                    {
                        "MODULE_ID": "hermes-agent1",
                        "TIMEZONE": "UTC",
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
                            data={
                                "instance": "hermes-agent1-hermes-auth",
                            },
                        ),
                    ],
                )
                agent_stub.bind_user_domains.assert_called_once_with([])
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
                    Path("agent_4.env"),
                    {"AGENT_NAME": "Route Agent"},
                )
                write_envfile(
                    Path("agent_4_secrets.env"),
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
                self.assertEqual(
                    agent_tasks_stub.run.call_args_list,
                    [
                        mock.call(
                            agent_id="module/traefik1",
                            action="delete-route",
                            data={"instance": "hermes-agent1-hermes-auth"},
                        ),
                    ],
                )
                self.assertEqual(
                    run_command.call_args_list,
                    [
                        mock.call(
                            ["systemctl", "--user", "disable", "--now", "hermes-auth.service"],
                            check=False,
                        ),
                        mock.call(["podman", "rm", "--force", "hermes-auth"], check=False),
                        mock.call(
                            ["systemctl", "--user", "disable", "--now", "hermes-socket@4.service"],
                            check=False,
                        ),
                        mock.call(
                            ["systemctl", "--user", "disable", "--now", "hermes@4.service"],
                            check=False,
                        ),
                        mock.call(
                            ["systemctl", "--user", "stop", "hermes-pod@4.service"],
                            check=False,
                        ),
                        mock.call(["podman", "pod", "rm", "--force", "hermes-pod-4"], check=False),
                        mock.call(["podman", "rm", "--force", "hermes-4"], check=False),
                        mock.call(["podman", "rm", "--force", "hermes-socket-4"], check=False),
                        mock.call(["runagent", "remove-agent-state", "--agent-id", "4"], check=True),
                        mock.call(["podman", "volume", "exists", "hermes-agent-4-home"], check=False),
                        mock.call(["podman", "volume", "rm", "--force", "hermes-agent-4-home"], check=True),
                    ],
                )
                self.assertFalse(Path("agent_4.env").exists())
                self.assertFalse(Path("agent_4_secrets.env").exists())
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
                    Path("agents") / "1" / "metadata.json",
                    {"id": 1, "name": "One Agent", "role": "default", "status": "start"},
                )
                write_envfile(Path("agent_2.env"), {"AGENT_NAME": "Two Agent"})

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
                                "instance": "hermes-agent1-hermes-auth",
                                "lets_encrypt_cleanup": True,
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

    def test_get_configuration_returns_desired_state_only(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                Path("agents") / "1" / "metadata.json",
                {
                    "id": 1,
                    "name": "Runtime Agent",
                    "role": "developer",
                    "status": "stop",
                    "allowed_user": "alice",
                },
            )
            stdout = io.StringIO()

            with mock.patch.dict(
                os.environ,
                {
                    self.state.BASE_VIRTUALHOST_ENV: "agents.example.org",
                    self.state.USER_DOMAIN_ENV: "example.org",
                    self.state.LETS_ENCRYPT_ENV: "true",
                },
                clear=False,
            ), mock.patch("sys.stdout", stdout):
                runpy.run_path(str(GET_CONFIGURATION_PATH), run_name="__main__")

            self.assertEqual(
                json.loads(stdout.getvalue()),
                {
                    "base_virtualhost": "agents.example.org",
                    "user_domain": "example.org",
                    "lets_encrypt": True,
                    "agents": [
                        {
                            "id": 1,
                            "name": "Runtime Agent",
                            "role": "developer",
                            "status": "stop",
                            "allowed_user": "alice",
                        }
                    ]
                },
            )

    def test_get_agent_runtime_reports_actual_runtime_status(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.write_jsonfile(
                Path("agents") / "1" / "metadata.json",
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
                Path("agents") / "1" / "metadata.json",
                {
                    "id": 1,
                    "name": "One Agent",
                    "role": "default",
                    "status": "start",
                    "allowed_user": "",
                },
            )
            write_envfile(Path("agent_2.env"), {"AGENT_NAME": "Two Agent"})
            write_envfile(Path("agent_3_secrets.env"), {"HERMES_AGENT_SECRET": "secret"})

            self.assertEqual(self.state.list_known_agent_ids(), [1, 2, 3])

    def test_list_known_agent_ids_ignores_out_of_range_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            self.state.ensure_private_directory(Path("agents") / "31")
            write_envfile(Path("agent_32.env"), {"AGENT_NAME": "Ignored Agent"})
            write_envfile(Path("agent_0_secrets.env"), {"HERMES_AGENT_SECRET": "ignored"})

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
                self.state.ensure_private_directory(Path("agents") / "4")
                self.state.ensure_private_directory(self.state.AGENT_DASHBOARD_SOCKETS_DIR)
                write_envfile(Path("agent_4.env"), {"AGENT_NAME": "Four Agent"})
                write_envfile(Path("agent_4_secrets.env"), {"HERMES_AGENT_SECRET": "secret"})
                (self.state.AGENT_DASHBOARD_SOCKETS_DIR / "agent-4.sock").write_text("socket", encoding="utf-8")

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

                self.assertTrue(Path("agent_4.env").exists())
                self.assertTrue(Path("agent_4_secrets.env").exists())
                self.assertTrue((Path("agents") / "4").exists())
                self.assertTrue((self.state.AGENT_DASHBOARD_SOCKETS_DIR / "agent-4.sock").exists())
        finally:
            sys.argv[:] = original_argv

    def test_remove_agent_state_removes_dashboard_socket_on_success(self):
        original_argv = sys.argv[:]
        try:
            with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
                self.state.ensure_private_directory(Path("agents") / "4")
                self.state.ensure_private_directory(self.state.AGENT_DASHBOARD_SOCKETS_DIR)
                write_envfile(Path("agent_4.env"), {"AGENT_NAME": "Four Agent"})
                write_envfile(Path("agent_4_secrets.env"), {"HERMES_AGENT_SECRET": "secret"})
                (self.state.AGENT_DASHBOARD_SOCKETS_DIR / "agent-4.sock").write_text("socket", encoding="utf-8")

                def run_side_effect(command, check=False, **kwargs):
                    if command == ["podman", "volume", "exists", "hermes-agent-4-home"]:
                        return types.SimpleNamespace(returncode=1)
                    return types.SimpleNamespace(returncode=0)

                sys.argv[:] = [str(REMOVE_AGENT_STATE_PATH), "--agent-id", "4"]
                with mock.patch("subprocess.run", side_effect=run_side_effect):
                    with self.assertRaises(SystemExit) as exit_error:
                        runpy.run_path(str(REMOVE_AGENT_STATE_PATH), run_name="__main__")

                self.assertEqual(exit_error.exception.code, 0)

                self.assertFalse(Path("agent_4.env").exists())
                self.assertFalse(Path("agent_4_secrets.env").exists())
                self.assertFalse((Path("agents") / "4").exists())
                self.assertFalse((self.state.AGENT_DASHBOARD_SOCKETS_DIR / "agent-4.sock").exists())
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

    def test_configure_module_validation_requires_user_domain_and_allowed_user_for_published_dashboard(self):
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
                            "base_virtualhost": "agents.example.org",
                            "agents": [
                                {
                                    "id": 1,
                                    "name": "Alice Agent",
                                    "role": "developer",
                                    "status": "start",
                                }
                            ],
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
                        "field": "agents[0].allowed_user",
                        "parameter": "agents",
                        "value": None,
                        "error": "agent_allowed_user_required",
                    }
                ],
            )
            agent_stub.set_status.assert_called_once_with("validation-failed")
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

    def test_configure_module_validation_rejects_unknown_user_domain_user(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "set_status", mock.Mock())
        sys.modules["agent"] = agent_stub

        try:
            stdout = io.StringIO()
            with mocked_ldap_modules(
                domains={
                    "example.org": {
                        "domain_name": "example.org",
                        "host": "127.0.0.1",
                        "port": 389,
                        "base_dn": "dc=example,dc=org",
                        "schema": "rfc2307",
                        "bind_dn": "cn=ldapservice,dc=example,dc=org",
                        "bind_password": "ldap-secret",
                    }
                },
                users_by_domain={"example.org": [{"user": "alice", "display_name": "Alice User", "locked": False}]},
            ), mock.patch(
                "sys.stdin",
                io.StringIO(
                    json.dumps(
                        {
                            "base_virtualhost": "agents.example.org",
                            "user_domain": "example.org",
                            "agents": [
                                {
                                    "id": 1,
                                    "name": "Alice Agent",
                                    "role": "developer",
                                    "status": "start",
                                    "allowed_user": "bob",
                                }
                            ],
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
                        "field": "agents[0].allowed_user",
                        "parameter": "agents",
                        "value": "bob",
                        "error": "agent_allowed_user_invalid",
                    }
                ],
            )
            agent_stub.set_status.assert_called_once_with("validation-failed")
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

    def test_configure_user_domain_step_binds_selected_domain(self):
        original_agent = sys.modules.get("agent")
        agent_stub = types.ModuleType("agent")
        setattr(agent_stub, "bind_user_domains", mock.Mock(return_value=True))
        sys.modules["agent"] = agent_stub

        try:
            with mock.patch("sys.stdin", io.StringIO(json.dumps({"user_domain": "Example.ORG"}))):
                runpy.run_path(
                    str(CONFIGURE_MODULE_ACTION_DIR / "25configure-user-domain"),
                    run_name="__main__",
                )

            agent_stub.bind_user_domains.assert_called_once_with(["example.org"])
        finally:
            if original_agent is not None:
                sys.modules["agent"] = original_agent
            else:
                del sys.modules["agent"]

    def test_list_user_domains_action_returns_sorted_domain_metadata(self):
        stdout = io.StringIO()
        with mocked_ldap_modules(
            domains={
                "b.example.org": {
                    "domain_name": "b.example.org",
                    "host": "127.0.0.1",
                    "port": 389,
                    "base_dn": "dc=b,dc=example,dc=org",
                    "schema": "ad",
                    "location": "internal",
                },
                "a.example.org": {
                    "domain_name": "a.example.org",
                    "host": "127.0.0.1",
                    "port": 389,
                    "base_dn": "dc=a,dc=example,dc=org",
                    "schema": "rfc2307",
                    "location": "external",
                },
            }
        ), mock.patch("sys.stdin", io.StringIO("{}")), mock.patch("sys.stdout", stdout):
            runpy.run_path(str(LIST_USER_DOMAINS_PATH), run_name="__main__")

        self.assertEqual(
            json.loads(stdout.getvalue()),
            {
                "domains": [
                    {"name": "a.example.org", "schema": "rfc2307", "location": "external"},
                    {"name": "b.example.org", "schema": "ad", "location": "internal"},
                ]
            },
        )

    def test_list_domain_users_action_returns_sorted_users(self):
        stdout = io.StringIO()
        with mocked_ldap_modules(
            domains={
                "example.org": {
                    "domain_name": "example.org",
                    "host": "127.0.0.1",
                    "port": 389,
                    "base_dn": "dc=example,dc=org",
                    "schema": "rfc2307",
                    "bind_dn": "cn=ldapservice,dc=example,dc=org",
                    "bind_password": "ldap-secret",
                }
            },
            users_by_domain={
                "example.org": [
                    {"user": "zoe", "display_name": "Zoe Agent", "locked": False},
                    {"user": "alice", "display_name": "Alice Agent", "locked": True},
                ]
            },
        ), mock.patch("sys.stdin", io.StringIO(json.dumps({"domain": "example.org"}))), mock.patch(
            "sys.stdout",
            stdout,
        ):
            runpy.run_path(str(LIST_DOMAIN_USERS_PATH), run_name="__main__")

        self.assertEqual(
            json.loads(stdout.getvalue()),
            {
                "users": [
                    {"user": "alice", "display_name": "Alice Agent", "locked": True},
                    {"user": "zoe", "display_name": "Zoe Agent", "locked": False},
                ]
            },
        )

    def test_sync_agent_runtime_files_requires_existing_agent(self):
        with tempfile.TemporaryDirectory() as temp_dir, working_directory(temp_dir):
            with mock.patch.object(self.sync.agent, "read_envfile", side_effect=read_envfile, create=True), mock.patch.object(
                self.sync.agent,
                "write_envfile",
                side_effect=write_envfile,
                create=True,
            ), self.assertRaisesRegex(ValueError, "agent 99 not found"):
                self.sync.sync_agent_runtime_files(agent_id=99)
