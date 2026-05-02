#!/usr/bin/env python3

from __future__ import annotations

import argparse
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--port", required=True, type=int)
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    directory = Path(args.directory).resolve()
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
