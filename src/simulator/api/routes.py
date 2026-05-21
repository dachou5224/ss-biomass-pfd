"""Route handlers for Excel/demo API contracts."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from simulator.api import schemas
from simulator.webservice_demo import (
    build_compute_response,
    build_input_read_response,
    build_output_pack_response,
    build_output_pack_tsv,
)


def handle_get(path: str) -> Dict[str, Any]:
    if path == schemas.HEALTH_ROUTE:
        return {"status_code": 200, "json": {"status": "ok", "service": "excel-webservice-demo"}}
    return {"status_code": 404, "json": {"error": f"unknown path: {path}"}}


def handle_post(path: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    if path == schemas.DEMO_INPUT_READ_ROUTE:
        return {"status_code": 200, "json": build_input_read_response(payload)}

    if path == schemas.COMPUTE_SIMULATE_LITE_ROUTE:
        return {"status_code": 200, "json": build_compute_response(payload)}

    if path in (schemas.DEMO_OUTPUT_PACK_ROUTE, schemas.DEMO_SIMULATE_LITE_ROUTE):
        return {"status_code": 200, "json": build_output_pack_response(payload)}

    if path in schemas.TSV_ROUTES:
        return {"status_code": 200, "tsv": build_output_pack_tsv(payload)}

    return {"status_code": 404, "json": {"error": f"unknown path: {path}"}}

