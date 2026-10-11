#!/usr/bin/env python3
"""Serve mockup/ static files and proxy /api/* to the Siftivex API."""

from __future__ import annotations

import argparse
import http.client
import re
import sys
import threading
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOCKUP = ROOT / "mockup"
DEFAULT_API = "http://127.0.0.1:8787"

# Browsers reach this server through SSH / editor port forwarding, where one TCP
# connection per request exhausts the tunnel. Keep-alive + caching of image
# bytes keeps the connection count near the browser's per-host limit (~6).
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
    "date",
    "server",
}
IMAGE_PATH = re.compile(r"^/api/images/[^/]+/(thumbnail|preview)(\?|$)")
IMAGE_CACHE_CONTROL = "private, max-age=86400"


class ThreadedServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 256


class MockupHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    api_base = DEFAULT_API
    _upstream = threading.local()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(MOCKUP), **kwargs)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy("GET")
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy("HEAD")
            return
        super().do_HEAD()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy("POST")
            return
        self.send_error(405, "Method Not Allowed")

    def end_headers(self) -> None:
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _upstream_conn(self, fresh: bool = False) -> http.client.HTTPConnection:
        conn = getattr(self._upstream, "conn", None)
        if conn is None or fresh:
            if conn is not None:
                conn.close()
            parsed = urllib.parse.urlsplit(self.api_base)
            conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=300)
            self._upstream.conn = conn
        return conn

    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "content-length", "connection", "keep-alive")
        }
        if body is not None:
            headers["Content-Length"] = str(len(body))

        resp = None
        resp_body = b""
        for attempt in range(2):
            conn = self._upstream_conn(fresh=attempt > 0)
            try:
                conn.request(method, self.path, body=body, headers=headers)
                resp = conn.getresponse()
                resp_body = resp.read()
                break
            except (OSError, http.client.HTTPException) as exc:
                resp = None
                if attempt == 1:
                    self.send_error(502, f"API unreachable ({self.api_base}): {exc}")
                    return

        self.send_response(resp.status)
        for key, value in resp.getheaders():
            if key.lower() not in HOP_BY_HOP:
                self.send_header(key, value)
        if resp.status == 200 and IMAGE_PATH.match(self.path):
            self.send_header("Cache-Control", IMAGE_CACHE_CONTROL)
        self.send_header("Access-Control-Allow-Origin", "*")
        if resp.status not in (204, 304):
            self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        if method != "HEAD" and resp.status not in (204, 304):
            self.wfile.write(resp_body)

    def log_message(self, fmt: str, *args) -> None:
        if args and isinstance(args[0], str) and args[0].startswith(("GET /api/", "POST /api/")):
            sys.stderr.write("PROXY %s\n" % (fmt % args))
            return
        super().log_message(fmt, *args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Siftivex layout mockup server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5199)
    parser.add_argument("--api", default=DEFAULT_API, help="Upstream API base URL")
    args = parser.parse_args()

    MockupHandler.api_base = args.api.rstrip("/")
    server = ThreadedServer((args.host, args.port), MockupHandler)
    print(f"Mockup:  http://{args.host}:{args.port}/")
    print(f"API proxy → {MockupHandler.api_base}")
    print("Layout Lab 右下でレイアウト調整 · Ctrl+C で停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
