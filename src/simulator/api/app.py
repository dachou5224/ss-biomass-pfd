"""HTTP app entrypoint for simulator API."""

from __future__ import annotations

import hmac
import json
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, FrozenSet, Optional

from simulator.api.routes import handle_get, handle_post


class SimulatorApiHandler(BaseHTTPRequestHandler):
    server_version = "SimulatorAPI/0.1"
    api_key: str = ""
    allowed_origins: FrozenSet[str] = frozenset({"*"})

    def _request_id(self) -> str:
        return self.headers.get("X-Request-ID", "")

    def _resolve_allow_origin(self) -> str:
        origin = self.headers.get("Origin", "")
        if "*" in self.allowed_origins:
            return "*"
        if origin and origin in self.allowed_origins:
            return origin
        return ""

    def _send_cors_headers(self) -> None:
        allow_origin = self._resolve_allow_origin()
        if allow_origin:
            self.send_header("Access-Control-Allow-Origin", allow_origin)
        if allow_origin and allow_origin != "*":
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key, X-Request-ID")

    def _log_access(self, *, method: str, path: str, status: int, start: float) -> None:
        latency_ms = int((time.time() - start) * 1000.0)
        rid = self._request_id()
        print(
            f"[api] ts={datetime.now(timezone.utc).isoformat()} "
            f"method={method} path={path} status={status} latency_ms={latency_ms} request_id={rid}"
        )

    def _is_authorized(self) -> bool:
        if not self.api_key:
            return True
        got = self.headers.get("X-API-Key", "")
        return hmac.compare_digest(got, self.api_key)

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_tsv(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/tab-separated-values; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        if not raw:
            return {}
        return dict(json.loads(raw.decode("utf-8")))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        start = time.time()
        result = handle_get(self.path)
        self._send_json(result["status_code"], result["json"])
        self._log_access(method="GET", path=self.path, status=result["status_code"], start=start)

    def do_POST(self) -> None:  # noqa: N802
        start = time.time()
        try:
            if not self._is_authorized():
                self._send_json(401, {"error": "unauthorized"})
                self._log_access(method="POST", path=self.path, status=401, start=start)
                return
            payload = self._read_json()
            result = handle_post(self.path, payload)
            if "json" in result:
                self._send_json(result["status_code"], result["json"])
            else:
                self._send_tsv(result["status_code"], result["tsv"])
            self._log_access(method="POST", path=self.path, status=result["status_code"], start=start)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            self._log_access(method="POST", path=self.path, status=400, start=start)
        except json.JSONDecodeError as exc:
            self._send_json(400, {"error": f"invalid json: {exc}"})
            self._log_access(method="POST", path=self.path, status=400, start=start)


def parse_allowed_origins(raw: Optional[str]) -> FrozenSet[str]:
    if raw is None or not raw.strip():
        return frozenset({"*"})
    values = [x.strip() for x in raw.split(",")]
    cleaned = frozenset(x for x in values if x)
    return cleaned if cleaned else frozenset({"*"})


def create_server(
    host: str,
    port: int,
    *,
    api_key: Optional[str] = None,
    allowed_origins: Optional[FrozenSet[str]] = None,
) -> ThreadingHTTPServer:
    SimulatorApiHandler.api_key = (api_key or "").strip()
    SimulatorApiHandler.allowed_origins = allowed_origins or parse_allowed_origins(
        os.getenv("SIM_API_ALLOWED_ORIGINS", "*")
    )
    return ThreadingHTTPServer((host, port), SimulatorApiHandler)


def print_startup_routes(host: str, port: int) -> None:
    print(f"Demo service started: http://{host}:{port}")
    print("GET  /health")
    print("POST /v1/compute/simulate-lite")
    print("POST /v1/demo/input-read")
    print("POST /v1/demo/output-pack")
    print("POST /v1/demo/simulate-lite")
    print("POST /v1/demo/output-pack.tsv")
    print("POST /v1/demo/simulate-lite.tsv")
