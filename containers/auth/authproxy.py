#!/usr/bin/env python3

import base64
import binascii
import os
from dataclasses import dataclass
from html import escape

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer
from ldap3 import ALL, Connection, Server
from ldap3.utils.conv import escape_filter_chars


SESSION_COOKIE = "hermes_dashboard_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
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


@dataclass(frozen=True)
class RuntimeConfig:
    agent_id: str
    agent_name: str
    allowed_user: str
    user_domain: str
    ldap_host: str
    ldap_port: int
    ldap_base_dn: str
    ldap_schema: str
    ldap_bind_dn: str
    ldap_bind_password: str
    session_secret: str
    dashboard_upstream_url: str
    base_url: str

    @property
    def realm(self):
        agent_label = self.agent_name or f"Agent {self.agent_id}".strip()
        return f"Hermes dashboard: {agent_label}"


def env(name, default=""):
    return (os.getenv(name, default) or "").strip()


def normalize_prefix(value):
    prefix = (value or "").strip()
    if not prefix:
        return ""
    if not prefix.startswith("/"):
        prefix = f"/{prefix}"
    return prefix.rstrip("/") or "/"


def load_config():
    ldap_port = int(env("LDAP_PORT", "389") or "389")
    return RuntimeConfig(
        agent_id=env("AGENT_ID"),
        agent_name=env("AGENT_NAME") or env("AGENT_ID"),
        allowed_user=env("AGENT_ALLOWED_USER"),
        user_domain=env("USER_DOMAIN").lower(),
        ldap_host=env("LDAP_HOST"),
        ldap_port=ldap_port,
        ldap_base_dn=env("LDAP_BASE_DN"),
        ldap_schema=env("LDAP_SCHEMA").lower(),
        ldap_bind_dn=env("LDAP_BIND_DN"),
        ldap_bind_password=env("LDAP_BIND_PASSWORD"),
        session_secret=env("HERMES_AGENT_SECRET"),
        dashboard_upstream_url=env("DASHBOARD_UPSTREAM_URL", "http://127.0.0.1:9120").rstrip("/"),
        base_url=normalize_prefix(env("BASE_URL")),
    )


def configuration_complete(config):
    required_values = (
        config.allowed_user,
        config.user_domain,
        config.ldap_host,
        config.ldap_base_dn,
        config.session_secret,
        config.dashboard_upstream_url,
    )
    return all(required_values)


def session_serializer(config):
    return URLSafeTimedSerializer(config.session_secret, salt="hermes-dashboard-auth")


def request_prefix(request, config):
    forwarded_prefix = request.headers.get("x-forwarded-prefix", "")
    return normalize_prefix(forwarded_prefix) or config.base_url or "/"


def parse_basic_auth(request):
    authorization = request.headers.get("authorization", "")
    scheme, _, encoded_value = authorization.partition(" ")
    if scheme.lower() != "basic" or not encoded_value:
        return None

    try:
        decoded = base64.b64decode(encoded_value, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None

    username, separator, password = decoded.partition(":")
    if not separator:
        return None

    return username, password


def user_search_filter(username, schema):
    escaped_username = escape_filter_chars(username)
    if "ad" in schema:
        filters = (
            f"(sAMAccountName={escaped_username})",
            f"(userPrincipalName={escaped_username})",
            f"(uid={escaped_username})",
        )
    else:
        filters = (
            f"(uid={escaped_username})",
            f"(cn={escaped_username})",
            f"(mail={escaped_username})",
            f"(sAMAccountName={escaped_username})",
        )

    return f"(|{''.join(filters)})"


def ldap_server(config):
    return Server(config.ldap_host, port=config.ldap_port, use_ssl=config.ldap_port == 636, get_info=ALL)


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
    if username != config.allowed_user or not password:
        return False

    user_dn = lookup_user_dn(username, config)
    if not user_dn:
        return False

    try:
        with Connection(ldap_server(config), user=user_dn, password=password, auto_bind=True):
            return True
    except Exception:
        return False


def session_payload(username, prefix, config):
    return {
        "allowed_user": username,
        "user_domain": config.user_domain,
        "prefix": prefix or "/",
    }


def read_session(request, prefix, config):
    cookie_value = request.cookies.get(SESSION_COOKIE)
    if not cookie_value or not config.session_secret:
        return None

    try:
        payload = session_serializer(config).loads(cookie_value, max_age=SESSION_TTL_SECONDS)
    except (BadSignature, BadTimeSignature):
        return None

    if payload.get("allowed_user") != config.allowed_user:
        return None
    if payload.get("user_domain") != config.user_domain:
        return None
    if payload.get("prefix") != (prefix or "/"):
        return None

    return payload.get("allowed_user")


def challenge_response(config):
    return PlainTextResponse(
        "Dashboard authentication required.",
        status_code=401,
        headers={
            "Cache-Control": "no-store",
            "WWW-Authenticate": f'Basic realm="{config.realm}", charset="UTF-8"',
        },
    )


def configuration_required_response(config):
    agent_label = escape(config.agent_name or f"Agent {config.agent_id}")
    html = f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{agent_label} dashboard requires configuration</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 2rem;
        background: #f4efe5;
        color: #1f2933;
        font-family: "IBM Plex Sans", sans-serif;
      }}
      main {{
        max-width: 40rem;
        background: rgba(255, 255, 255, 0.88);
        border: 1px solid rgba(31, 41, 51, 0.12);
        border-radius: 1rem;
        padding: 2rem;
        box-shadow: 0 1.5rem 3rem rgba(31, 41, 51, 0.12);
      }}
      h1 {{ margin-top: 0; font-size: 1.75rem; }}
      p {{ line-height: 1.6; }}
      code {{ font-family: "IBM Plex Mono", monospace; }}
    </style>
  </head>
  <body>
    <main>
      <h1>Dashboard access is not configured</h1>
      <p>{agent_label} is published, but dashboard authentication is still missing required settings.</p>
      <p>Select a shared <code>user_domain</code> and an agent <code>allowed_user</code> in the module settings, then save the configuration to enable access.</p>
    </main>
  </body>
</html>
"""
    return HTMLResponse(html, status_code=503, headers={"Cache-Control": "no-store"})


def upstream_headers(request):
    forwarded_headers = {}
    for name, value in request.headers.items():
        lower_name = name.lower()
        if lower_name in HOP_BY_HOP_HEADERS or lower_name in {"authorization", "host", "content-length"}:
            continue
        if lower_name == "cookie":
            continue
        forwarded_headers[name] = value

    filtered_cookies = [
        f"{name}={value}"
        for name, value in request.cookies.items()
        if name != SESSION_COOKIE
    ]
    if filtered_cookies:
        forwarded_headers["Cookie"] = "; ".join(filtered_cookies)

    return forwarded_headers


def response_headers(upstream_response, prefix):
    headers = {}
    for name, value in upstream_response.headers.items():
        lower_name = name.lower()
        if lower_name in HOP_BY_HOP_HEADERS or lower_name == "content-length":
            continue
        if lower_name == "location" and value.startswith("/") and prefix:
            headers[name] = f"{prefix}{value}"
            continue
        headers[name] = value
    return headers


app = FastAPI()


@app.on_event("startup")
async def startup():
    app.state.client = httpx.AsyncClient(timeout=60.0, follow_redirects=False)


@app.on_event("shutdown")
async def shutdown():
    await app.state.client.aclose()


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def proxy(path: str, request: Request):
    del path
    config = load_config()
    prefix = request_prefix(request, config)

    if not configuration_complete(config):
        return configuration_required_response(config)

    authenticated_user = read_session(request, prefix, config)
    session_is_new = False
    if authenticated_user is None:
        credentials = parse_basic_auth(request)
        if credentials is None or not authenticate_credentials(credentials[0], credentials[1], config):
            return challenge_response(config)
        authenticated_user = credentials[0]
        session_is_new = True

    upstream_url = f"{config.dashboard_upstream_url}{request.url.path}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    upstream_response = await app.state.client.request(
        method=request.method,
        url=upstream_url,
        headers=upstream_headers(request),
        content=await request.body(),
    )

    response = Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers(upstream_response, prefix),
    )

    if session_is_new:
        response.set_cookie(
            SESSION_COOKIE,
            session_serializer(config).dumps(session_payload(authenticated_user, prefix, config)),
            max_age=SESSION_TTL_SECONDS,
            path=prefix or "/",
            httponly=True,
            samesite="lax",
            secure=request.headers.get("x-forwarded-proto", "http") == "https",
        )

    return response


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=env("AUTH_PROXY_HOST", "0.0.0.0"),
        port=int(env("AUTH_PROXY_PORT", "9119") or "9119"),
    )