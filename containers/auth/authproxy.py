#!/usr/bin/env python3

import json
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from html import escape
from urllib.parse import parse_qs

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer
from ldap3 import ALL, Connection, Server
from ldap3.utils.conv import escape_filter_chars


SESSION_COOKIE = "hermes_dashboard_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
LOGIN_PATH = "/login"
LOGOUT_PATH = "/logout"
TARGET_PATH_PATTERN = re.compile(r"^/hermes-(\d+)(?:/(dashboard|chat)(?:/.*)?|/?)$")
AUTHENTICATED_USER_HEADER = "X-Hermes-Authenticated-User"
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
LOGGER = logging.getLogger("hermes.authproxy")


@dataclass(frozen=True)
class AgentRecord:
    agent_id: int
    agent_name: str
    allowed_user: str
    status: str
    upstream_url: str = ""
    dashboard_upstream_socket: str = ""
    chat_upstream_socket: str = ""

    @property
    def display_name(self):
        return self.agent_name or f"Agent {self.agent_id}"

    @property
    def upstream_origin(self):
        if self.upstream_url:
            return self.upstream_url.rstrip("/")
        return f"http://agent-{self.agent_id}"

    def upstream_socket_for(self, app_name):
        if app_name == "chat":
            return self.chat_upstream_socket
        return self.dashboard_upstream_socket

    def has_upstream_for(self, app_name):
        return bool(self.upstream_url or self.upstream_socket_for(app_name))


@dataclass(frozen=True)
class RuntimeConfig:
    user_domain: str
    ldap_host: str
    ldap_port: int
    ldap_base_dn: str
    ldap_schema: str
    ldap_bind_dn: str
    ldap_bind_password: str
    session_secret: str
    agents_by_id: dict
    agents_by_user: dict


def env(name, default=""):
    return (os.getenv(name, default) or "").strip()


def env_flag(name, default=False):
    value = env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def configure_logging():
    if LOGGER.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.propagate = False

    level_name = env("AUTH_PROXY_LOG_LEVEL", "INFO").upper()
    LOGGER.setLevel(getattr(logging, level_name, logging.INFO))


configure_logging()


def load_agent_registry(path):
    registry_path = path or "/app/authproxy_agents.json"

    try:
        with open(registry_path, "r", encoding="utf-8") as registry_file:
            payload = json.load(registry_file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}, {}

    agents_by_id = {}
    agents_by_user = {}
    for raw_agent in payload.get("agents", []):
        try:
            agent_record = AgentRecord(
                agent_id=int(raw_agent["id"]),
                agent_name=str(raw_agent.get("name") or "").strip(),
                allowed_user=str(raw_agent["allowed_user"]).strip(),
                status=str(raw_agent.get("status") or "").strip().lower(),
                upstream_url=str(raw_agent.get("upstream_url") or "").rstrip("/"),
                dashboard_upstream_socket=str(
                    raw_agent.get("dashboard_upstream_socket") or raw_agent.get("upstream_socket") or ""
                ).strip(),
                chat_upstream_socket=str(raw_agent.get("chat_upstream_socket") or "").strip(),
            )
        except (KeyError, TypeError, ValueError):
            continue

        if not agent_record.allowed_user or not agent_record.has_upstream_for("dashboard"):
            continue
        if agent_record.dashboard_upstream_socket and not agent_record.dashboard_upstream_socket.startswith("/"):
            continue
        if agent_record.chat_upstream_socket and not agent_record.chat_upstream_socket.startswith("/"):
            continue
        if agent_record.allowed_user in agents_by_user:
            return {}, {}

        agents_by_id[agent_record.agent_id] = agent_record
        agents_by_user[agent_record.allowed_user] = agent_record

    return agents_by_id, agents_by_user


def load_config():
    ldap_port = int(env("LDAP_PORT", "389") or "389")
    agents_by_id, agents_by_user = load_agent_registry(env("AUTH_PROXY_AGENT_REGISTRY", "/app/authproxy_agents.json"))
    return RuntimeConfig(
        user_domain=env("USER_DOMAIN").lower(),
        ldap_host=env("LDAP_HOST"),
        ldap_port=ldap_port,
        ldap_base_dn=env("LDAP_BASE_DN"),
        ldap_schema=env("LDAP_SCHEMA").lower(),
        ldap_bind_dn=env("LDAP_BIND_DN"),
        ldap_bind_password=env("LDAP_BIND_PASSWORD"),
        session_secret=env("HERMES_AUTH_SESSION_SECRET"),
        agents_by_id=agents_by_id,
        agents_by_user=agents_by_user,
    )


def configuration_complete(config):
    required_values = (
        config.user_domain,
        config.ldap_host,
        config.ldap_base_dn,
        config.session_secret,
    )
    return all(required_values) and bool(config.agents_by_id)


def session_serializer(config):
    return URLSafeTimedSerializer(config.session_secret, salt="hermes-dashboard-auth")


def client_host(request):
    client = getattr(request, "client", None)
    return getattr(client, "host", "-") or "-"


def log_auth_event(event, request, agent_id="", username="", auth_method="", detail=""):
    parts = [
        f"event={event}",
        f"agent_id={agent_id or '-'}",
        f"method={getattr(request, 'method', '-')}",
        f"path={getattr(getattr(request, 'url', None), 'path', '-')}",
        f"remote={client_host(request)}",
    ]
    if username:
        parts.append(f"user={username}")
    if auth_method:
        parts.append(f"auth_method={auth_method}")
    if detail:
        parts.append(f"detail={detail}")
    LOGGER.info(" ".join(parts))


def debug_enabled():
    return env_flag("DEBUG") or env_flag("AUTH_PROXY_DEBUG")


def log_debug_event(event, request, agent_id="", detail=""):
    if not debug_enabled():
        return
    log_auth_event(event, request, agent_id=agent_id, detail=detail)


def user_search_filter(username, schema):
    escaped_username = escape_filter_chars(username)
    if "ad" in schema:
        attributes = ("sAMAccountName", "userPrincipalName", "uid")
    else:
        attributes = ("uid", "cn", "mail")

    filters = tuple(f"({attribute}={escaped_username})" for attribute in attributes)
    return f"(|{''.join(filters)})"


def ldap_server(config):
    return Server(config.ldap_host, port=config.ldap_port, use_ssl=config.ldap_port == 636, get_info=ALL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=60.0, follow_redirects=False)
    app.state.uds_clients = {}
    try:
        yield
    finally:
        for client in app.state.uds_clients.values():
            await client.aclose()
        await app.state.client.aclose()


def lookup_user_dn(username, config):
    bind_user = config.ldap_bind_dn or None
    bind_password = config.ldap_bind_password or None
    connection = Connection(
        ldap_server(config),
        user=bind_user,
        password=bind_password,
        auto_bind=True,
    )

    with connection:
        if not connection.search(
            search_base=config.ldap_base_dn,
            search_filter=user_search_filter(username, config.ldap_schema),
            attributes=[],
            size_limit=2,
        ):
            return None

        if len(connection.entries) != 1:
            return None

        return connection.entries[0].entry_dn


def authenticate_credentials(username, password, config):
    if not username or not password:
        return False

    user_dn = lookup_user_dn(username, config)
    if not user_dn:
        return False

    try:
        with Connection(ldap_server(config), user=user_dn, password=password, auto_bind=True):
            return True
    except Exception:
        return False


def target_route(path):
    match = TARGET_PATH_PATTERN.fullmatch(path or "/")
    if match is None:
        return None
    agent_id = int(match.group(1))
    app_name = match.group(2)
    return agent_id, app_name


def target_agent_id(path):
    route = target_route(path)
    if route is None:
        return None
    return route[0]


def normalized_path(path):
    value = path or "/"
    if not value.startswith("/"):
        value = f"/{value}"
    return value


def request_path(request):
    return normalized_path(request.url.path)


def normalize_next_path(candidate, fallback="/"):
    value = normalized_path(candidate or fallback)
    if value.startswith("//"):
        return fallback
    if value in {LOGIN_PATH, LOGOUT_PATH}:
        return fallback
    route = target_route(value)
    if route is not None and route[1] is None:
        return fallback
    return value


def session_payload(username, agent_record, config):
    return {
        "allowed_user": username,
        "user_domain": config.user_domain,
        "agent_id": agent_record.agent_id,
    }


def read_session(request, config):
    cookie_value = request.cookies.get(SESSION_COOKIE)
    if not cookie_value or not config.session_secret:
        return None

    try:
        payload = session_serializer(config).loads(cookie_value, max_age=SESSION_TTL_SECONDS)
    except (BadSignature, BadTimeSignature):
        return None

    if payload.get("user_domain") != config.user_domain:
        return None

    username = payload.get("allowed_user")
    agent_record = config.agents_by_id.get(payload.get("agent_id"))
    if agent_record is None or agent_record.allowed_user != username or agent_record.status != "start":
        return None

    return {
        "username": username,
        "agent": agent_record,
    }


def find_assigned_agent(config, username):
    return config.agents_by_user.get((username or "").strip())


def login_target_agent(config, username, explicit_agent_id=None):
    agent_record = find_assigned_agent(config, username)
    if agent_record is None:
        return None
    if explicit_agent_id is not None and agent_record.agent_id != explicit_agent_id:
        return None
    if agent_record.status != "start":
        return None
    return agent_record


def configuration_required_response():
    html = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Hermes dashboard access requires configuration</title>
    <style>
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 2rem;
        background: #f4efe5;
        color: #1f2933;
        font-family: \"IBM Plex Sans\", sans-serif;
      }
      main {
        max-width: 40rem;
        background: rgba(255, 255, 255, 0.88);
        border: 1px solid rgba(31, 41, 51, 0.12);
        border-radius: 1rem;
        padding: 2rem;
        box-shadow: 0 1.5rem 3rem rgba(31, 41, 51, 0.12);
      }
      h1 { margin-top: 0; font-size: 1.75rem; }
      p { line-height: 1.6; }
      code { font-family: \"IBM Plex Mono\", monospace; }
    </style>
  </head>
  <body>
    <main>
      <h1>Dashboard access is not configured</h1>
      <p>The shared auth service is published, but dashboard authentication is still missing required settings.</p>
      <p>Select a shared <code>user_domain</code> and one unique <code>allowed_user</code> per agent in the module settings, then save the configuration to enable access.</p>
    </main>
  </body>
</html>
"""
    return HTMLResponse(html, status_code=503, headers={"Cache-Control": "no-store"})


def login_form_response(config, request, error_message="", username="", explicit_agent_id=None, next_path="/"):
    target_record = config.agents_by_id.get(explicit_agent_id) if explicit_agent_id is not None else None
    title = target_record.display_name if target_record is not None else "Hermes dashboard login"
    heading = f"Sign in to {target_record.display_name}" if target_record is not None else "Sign in to your Hermes dashboard"
    helper = (
        f"Authenticate to access {target_record.display_name}."
        if target_record is not None
        else "Authenticate with your assigned account to access the dashboard routed to your session."
    )
    error_html = f"<p class=\"error\">{escape(error_message)}</p>" if error_message else ""
    action_path = request_path(request) if explicit_agent_id is not None else LOGIN_PATH
    html = f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{escape(title)}</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 2rem;
        background:
          radial-gradient(circle at top left, rgba(207, 177, 135, 0.28), transparent 34%),
          linear-gradient(145deg, #efe6d7 0%, #f8f4ed 48%, #e4ddd0 100%);
        color: #1f2933;
        font-family: \"IBM Plex Sans\", sans-serif;
      }}
      main {{
        width: min(100%, 28rem);
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid rgba(31, 41, 51, 0.12);
        border-radius: 1.25rem;
        padding: 2rem;
        box-shadow: 0 1.5rem 3rem rgba(31, 41, 51, 0.12);
      }}
      h1 {{ margin: 0 0 0.75rem; font-size: 1.75rem; }}
      p {{ line-height: 1.6; margin: 0 0 1rem; }}
      label {{ display: block; margin-top: 1rem; font-weight: 600; }}
      input {{
        width: 100%;
        box-sizing: border-box;
        margin-top: 0.35rem;
        padding: 0.8rem 0.95rem;
        border-radius: 0.75rem;
        border: 1px solid rgba(31, 41, 51, 0.18);
        font: inherit;
      }}
      button {{
        margin-top: 1.25rem;
        width: 100%;
        padding: 0.9rem 1rem;
        border: 0;
        border-radius: 999px;
        background: #205493;
        color: #fff;
        font: inherit;
        font-weight: 600;
        cursor: pointer;
      }}
      .error {{
        margin-top: 1rem;
        padding: 0.85rem 1rem;
        border-radius: 0.75rem;
        background: rgba(176, 18, 18, 0.08);
        color: #7f1d1d;
      }}
      .meta {{ color: #52606d; font-size: 0.95rem; }}
    </style>
  </head>
  <body>
    <main>
      <h1>{escape(heading)}</h1>
      <p>{escape(helper)}</p>
      {error_html}
      <form method=\"post\" action=\"{escape(action_path)}\">
        <input type=\"hidden\" name=\"next\" value=\"{escape(next_path)}\" />
        <label for=\"username\">Username</label>
        <input id=\"username\" name=\"username\" type=\"text\" autocomplete=\"username\" value=\"{escape(username)}\" required />
        <label for=\"password\">Password</label>
        <input id=\"password\" name=\"password\" type=\"password\" autocomplete=\"current-password\" required />
        <button type=\"submit\">Sign in</button>
      </form>
      <p class=\"meta\">Requests are routed to the dashboard assigned to the authenticated session.</p>
    </main>
  </body>
</html>
"""
    return HTMLResponse(html, status_code=401 if error_message else 200, headers={"Cache-Control": "no-store"})


def status_page_response(session_data, current_path):
    agent_record = session_data["agent"]
    helper = "Your session will proxy dashboard requests on this host to the assigned agent."
    current_target = target_agent_id(current_path)
    if current_target is not None and current_target != agent_record.agent_id:
        helper = f"Your active session is assigned to {agent_record.display_name}; this page only manages that session."
    html = f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{escape(agent_record.display_name)} session</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 2rem;
        background: linear-gradient(160deg, #f3efe8 0%, #e8e0d2 100%);
        color: #1f2933;
        font-family: \"IBM Plex Sans\", sans-serif;
      }}
      main {{
        width: min(100%, 28rem);
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid rgba(31, 41, 51, 0.12);
        border-radius: 1.25rem;
        padding: 2rem;
        box-shadow: 0 1.5rem 3rem rgba(31, 41, 51, 0.12);
      }}
      h1 {{ margin-top: 0; font-size: 1.7rem; }}
      p {{ line-height: 1.6; }}
      .actions {{ display: flex; gap: 0.75rem; margin-top: 1.5rem; }}
      a, button {{
        flex: 1 1 auto;
        text-align: center;
        padding: 0.9rem 1rem;
        border-radius: 999px;
        font: inherit;
        font-weight: 600;
        text-decoration: none;
      }}
      a {{ background: #205493; color: #fff; }}
      button {{ border: 0; background: #9f2d20; color: #fff; cursor: pointer; }}
      form {{ flex: 1 1 auto; margin: 0; }}
      code {{ font-family: \"IBM Plex Mono\", monospace; }}
    </style>
  </head>
  <body>
    <main>
      <h1>Signed in to {escape(agent_record.display_name)}</h1>
      <p>Authenticated as <code>{escape(session_data['username'])}</code>.</p>
      <p>{escape(helper)}</p>
      <div class=\"actions\">
        <a href=\"/\">Open dashboard</a>
        <form method=\"post\" action=\"{LOGOUT_PATH}\">
          <input type=\"hidden\" name=\"return_to\" value=\"{escape(current_path)}\" />
          <button type=\"submit\">Log out</button>
        </form>
      </div>
    </main>
  </body>
</html>
"""
    return HTMLResponse(html, status_code=200, headers={"Cache-Control": "no-store"})


def unauthorized_response():
    return PlainTextResponse(
        "Dashboard authentication required.",
        status_code=401,
        headers={"Cache-Control": "no-store"},
    )


def upstream_unavailable_response():
    return PlainTextResponse(
        "Assigned dashboard is temporarily unavailable.",
        status_code=502,
        headers={"Cache-Control": "no-store"},
    )


async def parse_form_body(request):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        return {}

    try:
        decoded_body = (await request.body()).decode("utf-8")
    except UnicodeDecodeError:
        return {}

    return {key: values[-1] if values else "" for key, values in parse_qs(decoded_body, keep_blank_values=True).items()}


def request_next_path(request):
    path = request_path(request)
    if request.url.query:
        return f"{path}?{request.url.query}"
    return path


def upstream_headers(request, authenticated_username=""):
    forwarded_headers = {}
    for name, value in request.headers.items():
        lower_name = name.lower()
        if lower_name in HOP_BY_HOP_HEADERS or lower_name in {"host", "content-length"}:
            continue
        if lower_name == "cookie":
            continue
        if lower_name == AUTHENTICATED_USER_HEADER.lower():
            continue
        forwarded_headers[name] = value

    filtered_cookies = [
        f"{name}={value}"
        for name, value in request.cookies.items()
        if name != SESSION_COOKIE
    ]
    if filtered_cookies:
        forwarded_headers["Cookie"] = "; ".join(filtered_cookies)

    if authenticated_username:
        forwarded_headers[AUTHENTICATED_USER_HEADER] = authenticated_username

    forwarded_headers["X-Forwarded-Proto"] = request.headers.get("x-forwarded-proto", "http")
    forwarded_headers["X-Forwarded-Host"] = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    forwarded_headers["X-Forwarded-For"] = client_host(request)
    return forwarded_headers


def response_headers(upstream_response, upstream_base_url):
    headers = {}
    for name, value in upstream_response.headers.items():
        lower_name = name.lower()
        if lower_name in HOP_BY_HOP_HEADERS or lower_name == "content-length":
            continue
        if lower_name == "location" and value.startswith(upstream_base_url):
            rewritten = value[len(upstream_base_url) :]
            headers[name] = rewritten or "/"
            continue
        headers[name] = value
    return headers


def upstream_path_for_request(request, app_name):
    path = request.url.path or "/"
    if path.startswith("/"):
        prefix = None
        if app_name == "dashboard":
            prefix = f"/hermes-{target_agent_id(path)}/dashboard" if target_route(path) else None
        elif app_name == "chat":
            prefix = f"/hermes-{target_agent_id(path)}/chat" if target_route(path) else None
        if prefix and path.startswith(prefix):
            stripped = path[len(prefix):]
            return stripped or "/"
    return path


def upstream_request_url(agent_record, request, app_name):
    upstream_url = f"{agent_record.upstream_origin}{upstream_path_for_request(request, app_name)}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"
    return upstream_url


def upstream_client_for_agent(request, agent_record, app_name):
    upstream_socket = agent_record.upstream_socket_for(app_name)
    if not upstream_socket:
        return request.app.state.client

    uds_clients = getattr(request.app.state, "uds_clients", None)
    if uds_clients is None:
        uds_clients = {}
        request.app.state.uds_clients = uds_clients

    client = uds_clients.get(upstream_socket)
    if client is None:
        client = httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=False,
            transport=httpx.AsyncHTTPTransport(uds=upstream_socket),
        )
        uds_clients[upstream_socket] = client

    return client


async def proxy_to_agent(agent_record, request, authenticated_username="", app_name="dashboard"):
    upstream_url = upstream_request_url(agent_record, request, app_name)
    upstream_client = upstream_client_for_agent(request, agent_record, app_name)

    log_debug_event(
        "proxy_forward",
        request,
        agent_id=str(agent_record.agent_id),
        detail=f"upstream_url={upstream_url}",
    )

    try:
        upstream_response = await upstream_client.request(
            method=request.method,
            url=upstream_url,
            headers=upstream_headers(request, authenticated_username=authenticated_username),
            content=await request.body(),
        )
    except httpx.RequestError as exc:
        log_auth_event(
            "proxy_failed",
            request,
            agent_id=str(agent_record.agent_id),
            detail=f"{exc.__class__.__name__}:{exc}",
        )
        return upstream_unavailable_response()

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers(upstream_response, agent_record.upstream_origin),
    )


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.post(LOGOUT_PATH)
async def logout(request: Request):
    form_data = await parse_form_body(request)
    response = RedirectResponse(
        normalize_next_path(form_data.get("return_to"), "/"),
        status_code=303,
    )
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def proxy(path: str, request: Request):
    del path
    config = load_config()
    current_path = request_path(request)
    explicit_route = target_route(current_path)
    explicit_agent = explicit_route[0] if explicit_route is not None else None
    explicit_app = explicit_route[1] if explicit_route is not None else None

    log_debug_event(
        "request_received",
        request,
        agent_id=str(explicit_agent or ""),
    )

    if not configuration_complete(config):
        return configuration_required_response()

    session_data = read_session(request, config)

    if request.method == "POST" and (current_path == LOGIN_PATH or (explicit_agent is not None and explicit_app is None)):
        form_data = await parse_form_body(request)
        username = (form_data.get("username") or "").strip()
        password = form_data.get("password") or ""
        next_path = normalize_next_path(form_data.get("next"), "/")

        log_auth_event(
            "auth_attempt",
            request,
            agent_id=str(explicit_agent or ""),
            username=username,
            auth_method="form",
        )

        target_record = login_target_agent(config, username, explicit_agent_id=explicit_agent)
        if target_record is None or not authenticate_credentials(username, password, config):
            log_auth_event(
                "auth_failed",
                request,
                agent_id=str(explicit_agent or ""),
                username=username,
                auth_method="form",
                detail="invalid_credentials_or_assignment",
            )
            return login_form_response(
                config,
                request,
                error_message="Invalid credentials or no running dashboard is assigned to this account.",
                username=username,
                explicit_agent_id=explicit_agent,
                next_path=next_path,
            )

        response = RedirectResponse(next_path, status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            session_serializer(config).dumps(session_payload(username, target_record, config)),
            max_age=SESSION_TTL_SECONDS,
            path="/",
            httponly=True,
            samesite="lax",
            secure=request.headers.get("x-forwarded-proto", "http") == "https",
        )
        log_auth_event(
            "auth_success",
            request,
            agent_id=str(target_record.agent_id),
            username=username,
            auth_method="form",
        )
        return response

    if explicit_agent is not None and explicit_app is None:
        if session_data is not None:
            return status_page_response(session_data, current_path)
        return login_form_response(config, request, explicit_agent_id=explicit_agent, next_path="/")

    if current_path == LOGIN_PATH:
        if session_data is not None:
            return RedirectResponse("/", status_code=303)
        return login_form_response(
            config,
            request,
            next_path=normalize_next_path(request_next_path(request), "/"),
        )

    if session_data is None:
        if request.method not in {"GET", "HEAD"}:
            log_auth_event(
                "auth_failed",
                request,
                auth_method="session",
                detail="missing_session",
            )
            return unauthorized_response()
        return login_form_response(
            config,
            request,
            next_path=normalize_next_path(request_next_path(request), "/"),
        )

    log_auth_event(
        "auth_success",
        request,
        agent_id=str(session_data["agent"].agent_id),
        username=session_data["username"],
        auth_method="session",
    )
    return await proxy_to_agent(
        session_data["agent"],
        request,
        authenticated_username=session_data["username"],
        app_name=explicit_app or "dashboard",
    )


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=env("AUTH_PROXY_HOST", "0.0.0.0"),
        port=int(env("AUTH_PROXY_PORT", "9119") or "9119"),
    )