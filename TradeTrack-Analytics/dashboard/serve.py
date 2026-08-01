"""Serve the dashboard with caching switched off.

python -m http.server sends no cache-control headers, so a browser is free to
reuse app.js and data.js from a previous visit. After a pipeline rebuild that
means the page silently renders the OLD payload — filters appear to do nothing
because the data behind them never changed. This sends no-store instead, so a
plain reload always fetches what is on disk.

Run:  python dashboard/serve.py [port]
"""
from __future__ import annotations

import functools
import http.server
import os
import sys

DIRECTORY = os.path.dirname(os.path.abspath(__file__))


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):        # keep the console readable
        pass


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = functools.partial(NoCacheHandler, directory=DIRECTORY)
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"TradeTrack dashboard -> http://127.0.0.1:{port}")
        print(f"serving {DIRECTORY} with caching disabled (Ctrl-C to stop)")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
