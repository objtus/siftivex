#!/usr/bin/env python3
"""Serve mockup/ static files and proxy /api/* to the Siftivex API."""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOCKUP = ROOT / "mockup"
DEFAULT_API = "http://127.0.0.1:8787"


class MockupHandler(SimpleHTTPRequestHandler):
    api_base = DEFAULT_API

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(MOCKUP), **kwargs)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy()
            return
        super().do_GET()

    def _proxy(self) -> None:
        url = f"{self.api_base}{self.path}"
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                body = resp.read()
                self.send_response(resp.status)
                skip = {"transfer-encoding", "connection", "content-encoding"}
                for key, value in resp.headers.items():
                    if key.lower() not in skip:
                        self.send_header(key, value)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "text/plain"))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except OSError as exc:
            self.send_error(502, f"API unreachable ({self.api_base}): {exc}")

    def log_message(self, fmt: str, *args) -> None:
        if args and isinstance(args[0], str) and args[0].startswith("GET /api/"):
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
    server = ThreadingHTTPServer((args.host, args.port), MockupHandler)
    print(f"Mockup:  http://{args.host}:{args.port}/")
    print(f"API proxy → {MockupHandler.api_base}")
    print("Layout Lab 右下でレイアウト調整 · Ctrl+C で停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
