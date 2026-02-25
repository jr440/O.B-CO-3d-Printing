#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from build_site import build_site
from ingest import ingest_all, watch_invoices


def serve_site(port: int = 5173):
    site_dir = ROOT / "site"
    site_dir.mkdir(exist_ok=True)
    os.chdir(site_dir)

    import http.server
    import socketserver

    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving site at http://localhost:{port}")
        print("Press Ctrl+C to stop")
        httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser(
        description="Run filament tracker tasks from one command"
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="quick",
        choices=["quick", "ingest", "refresh", "build", "watch", "serve", "all"],
        help=(
            "quick=ingest+build (default), ingest=process new invoices, refresh=reprocess all invoices, "
            "build=build site from db, watch=ingest existing then watch folder, "
            "serve=host site, all=quick then serve"
        ),
    )
    parser.add_argument("--port", type=int, default=5173, help="Port for serve/all")

    args = parser.parse_args()

    if args.action == "quick":
        ingest_all()
    elif args.action == "ingest":
        ingest_all()
    elif args.action == "refresh":
        ingest_all(reprocess_existing=True)
    elif args.action == "build":
        build_site(str(ROOT / "site" / "db.json"))
    elif args.action == "watch":
        ingest_all()
        watch_invoices()
    elif args.action == "serve":
        serve_site(args.port)
    elif args.action == "all":
        ingest_all()
        serve_site(args.port)


if __name__ == "__main__":
    main()
