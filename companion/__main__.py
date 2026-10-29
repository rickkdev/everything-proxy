"""Command line entry: connect, serve, mcp, status, disconnect."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import threading
import webbrowser

from . import db as store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m companion", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    connect = commands.add_parser("connect", help="grant read-only Gmail access (OAuth, stored in macOS Keychain)")
    connect.add_argument("--client-secrets", type=Path, required=True, help="Google OAuth 'Desktop app' client JSON")
    connect.add_argument("--no-browser", action="store_true")
    commands.add_parser("disconnect", help="revoke the Gmail grant and delete it from the Keychain")
    serve = commands.add_parser("serve", help="run the local companion and browser UI on 127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--max-messages", type=int, default=100, help="initial import cap (most recent first)")
    serve.add_argument("--window-days", type=int, default=30)
    serve.add_argument("--no-model", action="store_true", help="sync and filter only; skip local extraction")
    serve.add_argument("--open", action="store_true", help="open the UI in the default browser")
    serve.add_argument("--no-pairing-expiry", action="store_true", help="pairing codes stay valid until used (still single use)")
    commands.add_parser("mcp", help="serve read-only MCP tools over stdio")
    commands.add_parser("status", help="print the sanitized status that MCP clients see")
    args = parser.parse_args(argv)

    if args.command == "connect":
        from .gmail import connect as run_connect

        grant = run_connect(args.client_secrets, open_browser=not args.no_browser)
        print(f"Connected {grant.email} with gmail.readonly. The refresh token is in the macOS Keychain.")
        return 0
    if args.command == "disconnect":
        from .gmail import disconnect

        print("Grant revoked and removed." if disconnect() else "No Gmail grant was stored.")
        return 0
    if args.command == "mcp":
        from .mcp_server import main as mcp_main

        return mcp_main()
    if args.command == "status":
        from .release import ReleaseService, ReleaseSession

        print(json.dumps(ReleaseService(store.connect(), "cli").get_status(ReleaseSession()), indent=2))
        return 0
    return _serve(args)


def _serve(args: argparse.Namespace) -> int:
    from . import privacy
    from .gmail import GmailClient, Grant
    from .model import BonsaiExtractor, runtime_available
    from .server import PAIRING_SECONDS, STATIC_DIR, Companion, serve
    from .sync import Gateway

    if not (STATIC_DIR / "index.html").is_file():
        print("Browser UI is not built. Run: (cd browser && npm install && npm run build)", file=sys.stderr)
        return 1
    grant = Grant.load()
    client = GmailClient(grant) if grant else None
    unavailable = runtime_available()
    extractor = None if args.no_model or unavailable else BonsaiExtractor()
    gateway = Gateway(store.connect(), client, extractor, args.max_messages, args.window_days) if client else None
    app = Companion(args.port, gateway, grant.email if grant else None,
                    math.inf if args.no_pairing_expiry else PAIRING_SECONDS)
    try:
        server = serve(app)
    except OSError as error:
        print(f"Cannot bind 127.0.0.1:{args.port}: {error}", file=sys.stderr)
        return 1

    print("Loading the local privacy detector...", flush=True)
    privacy.detector()
    stop = threading.Event()
    if gateway:
        threading.Thread(target=gateway.run_forever, args=(stop,), daemon=True).start()
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print(f"\nEverything Proxy is running at {app.origin}/  (loopback only)")
    print(f"Gmail: {grant.email if grant else 'not connected; run: python -m companion connect --client-secrets <file>'}")
    print(f"Local model: {'disabled' if extractor is None else 'Ternary-Bonsai-2-27B (MLX, starts on first message)'}"
          + (f" — {unavailable}" if unavailable else ""))
    validity = "valid until used" if args.no_pairing_expiry else "valid 5 minutes"
    print(f"\nPairing code ({validity}, single use):\n\n    {app.pairing_secret}\n")
    print("Press Enter for a new pairing code. Ctrl+C stops the companion.", flush=True)
    if args.open:
        webbrowser.open(app.origin + "/")
    try:
        for _ in sys.stdin:
            print(f"\nNew pairing code:\n\n    {app.new_pairing_secret()}\n", flush=True)
        stop.wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.shutdown()
        if extractor is not None:
            extractor.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
