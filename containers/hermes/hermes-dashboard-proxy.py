#!/usr/bin/env python3

import argparse
import http.client
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


TEXT_CONTENT_TYPES = (
    "text/html",
    "text/css",
    "application/javascript",
    "text/javascript",
)

SAFE_PREFIX_PATTERN = re.compile(r"^/[A-Za-z0-9._/-]*$")

HOP_BY_HOP_REQUEST_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def normalize_prefix(value):
    prefix = (value or "").strip()
    if not prefix:
        return ""
    prefix = "/" + prefix.strip("/")
    if not SAFE_PREFIX_PATTERN.fullmatch(prefix):
        return ""
    return prefix


def rewrite_text(text, prefix):
    if not prefix:
        return text

    replacements = (
        ('"/api', f'"{prefix}/api'),
        ("'/api", f"'{prefix}/api"),
        ("`/api", f"`{prefix}/api"),
        ('"/assets', f'"{prefix}/assets'),
        ("'/assets", f"'{prefix}/assets"),
        ("`/assets", f"`{prefix}/assets"),
        ('"/favicon.ico', f'"{prefix}/favicon.ico'),
        ("'/favicon.ico", f"'{prefix}/favicon.ico"),
        ("url(/assets", f"url({prefix}/assets"),
        ("content=\"/", f"content=\"{prefix}/"),
        ("href=\"/", f"href=\"{prefix}/"),
        ("src=\"/", f"src=\"{prefix}/"),
    )

    for old, new in replacements:
        text = text.replace(old, new)

    if "</head>" in text:
        text = text.replace(
            "</head>",
            f"<script>window.__HERMES_DASHBOARD_PREFIX__ = {json.dumps(prefix)};</script></head>",
            1,
        )

    return text


class DashboardProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream_host = "127.0.0.1"
    upstream_port = 19119

    def do_GET(self):
        self._forward_request()

    def do_POST(self):
        self._forward_request()

    def do_PUT(self):
        self._forward_request()

    def do_DELETE(self):
        self._forward_request()

    def do_PATCH(self):
        self._forward_request()

    def do_OPTIONS(self):
        self._forward_request()

    def log_message(self, format, *args):
        return

    def _forward_request(self):
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        request_body = self.rfile.read(content_length) if content_length else None

        forwarded_headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_REQUEST_HEADERS and key.lower() != "x-forwarded-prefix"
        }
        forwarded_headers["Host"] = f"{self.upstream_host}:{self.upstream_port}"
        forwarded_headers["Accept-Encoding"] = "identity"

        connection = http.client.HTTPConnection(
            self.upstream_host,
            self.upstream_port,
            timeout=30,
        )
        try:
            connection.request(
                self.command,
                self.path,
                body=request_body,
                headers=forwarded_headers,
            )
            upstream_response = connection.getresponse()
            response_body = upstream_response.read()
            content_type = upstream_response.getheader("Content-Type", "")
            prefix = normalize_prefix(self.headers.get("X-Forwarded-Prefix"))

            if any(content_type.startswith(value) for value in TEXT_CONTENT_TYPES):
                charset_match = re.search(r"charset=([^;]+)", content_type, re.IGNORECASE)
                charset = charset_match.group(1) if charset_match else "utf-8"
                text_body = response_body.decode(charset, errors="replace")
                response_body = rewrite_text(text_body, prefix).encode(charset)

            self.send_response(upstream_response.status, upstream_response.reason)
            for header, value in upstream_response.getheaders():
                header_lower = header.lower()
                if header_lower in {"content-length", "connection", "transfer-encoding"}:
                    continue
                self.send_header(header, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        finally:
            connection.close()


def main():
    parser = argparse.ArgumentParser(description="Proxy Hermes dashboard behind a path-prefixed Traefik route")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=9119)
    parser.add_argument("--dashboard-host", default="127.0.0.1")
    parser.add_argument("--dashboard-port", type=int, default=19119)
    args = parser.parse_args()

    handler_class = type(
        "ConfiguredDashboardProxyHandler",
        (DashboardProxyHandler,),
        {
            "upstream_host": args.dashboard_host,
            "upstream_port": args.dashboard_port,
        },
    )

    with ThreadingHTTPServer((args.listen_host, args.listen_port), handler_class) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()