"""Tiny static server for the PPC EV Siting Lab frontend.

No dependencies, no build step. Serves the frontend directory and opens the UI.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import webbrowser
from pathlib import Path


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml",
    }

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        print(f"[frontend] {self.address_string()} — {fmt % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the PPC EV Siting Lab frontend")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    handler = functools.partial(Handler, directory=str(root))
    server = None
    port = args.port
    for candidate in range(args.port, args.port + 20):
        try:
            server = http.server.ThreadingHTTPServer((args.host, candidate), handler)
            port = candidate
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit(f"Could not bind {args.host}:{args.port}–{args.port + 19}")
    url = f"http://{args.host}:{port}/"
    print(f"PPC EV Siting Lab frontend: {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
