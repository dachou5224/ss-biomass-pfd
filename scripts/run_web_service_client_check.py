#!/usr/bin/env python3
"""在无 Excel 环境下复现 WebServiceDemo.js 的请求逻辑（冒烟测试）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "https://simapi.nice-ai.dev"


def _load_api_key() -> str:
    env = os.getenv("SIM_API_KEY", "").strip()
    if env:
        return env
    try:
        out = subprocess.check_output(
            ["ssh", "-o", "BatchMode=yes", "nice-ai-LZ", "grep SIM_API_KEY /etc/default/ss-biomass-api"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip().split("=", 1)[1]
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError):
        return ""


def _request(method: str, url: str, *, api_key: str = "", body: dict | None = None) -> tuple[int, str]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def main() -> int:
    base = os.getenv("DEMO_BASE_URL", DEFAULT_BASE).rstrip("/")
    api_key = _load_api_key()
    if not api_key:
        print("缺少 SIM_API_KEY（环境变量或 ssh nice-ai-LZ）", file=sys.stderr)
        return 1

    status, text = _request("GET", f"{base}/health")
    print(f"GET /health -> {status}")
    print(text[:200])
    if status != 200:
        return 1

    payload = {
        "case_id": "Case-1",
        "pfd_feeds": {
            "Biomass": {"mass_kg_h": 4100, "temp_c": 25, "pressure_bar": 1.0},
            "O2IN": {"mass_kg_h": 1400, "temp_c": 25, "pressure_bar": 1.0},
        },
        "o2in_composition": {"O2": 95.0, "N2": 1.75, "Ar": 3.25},
    }
    status, text = _request("POST", f"{base}/v1/compute/simulate-lite", api_key=api_key, body=payload)
    print(f"POST /v1/compute/simulate-lite -> {status}")
    data = json.loads(text)
    print(f"status={data.get('status')} kpi_rows={len(data.get('kpi_rows', []))}")
    for row in (data.get("kpi_rows") or [])[:3]:
        print(f"  - {row.get('metric')}: {row.get('value')} {row.get('unit')}")
    return 0 if status == 200 and data.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
