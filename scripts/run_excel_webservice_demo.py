#!/usr/bin/env python3
"""WPS Excel 联调轻量 API 服务（输入读取/输出整理）。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from simulator.api.app import create_server, parse_allowed_origins, print_startup_routes


def main() -> None:
    parser = argparse.ArgumentParser(description="Run lightweight webservice for WPS Excel demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--api-key", default="", help="API key for X-API-Key header; empty means disabled")
    parser.add_argument(
        "--allowed-origins",
        default="",
        help="Comma-separated CORS allowlist. Empty uses SIM_API_ALLOWED_ORIGINS or '*'",
    )
    args = parser.parse_args()

    api_key = args.api_key.strip() or os.getenv("SIM_API_KEY", "").strip()
    raw_origins = args.allowed_origins.strip() or os.getenv("SIM_API_ALLOWED_ORIGINS", "*")
    server = create_server(args.host, args.port, api_key=api_key, allowed_origins=parse_allowed_origins(raw_origins))
    print_startup_routes(args.host, args.port)
    print(f"Auth enabled: {'yes' if api_key else 'no'}")
    print(f"CORS allowlist: {','.join(sorted(parse_allowed_origins(raw_origins)))}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("Demo service stopped.")


if __name__ == "__main__":
    main()
