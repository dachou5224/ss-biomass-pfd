"""Versioned API route constants and lightweight schema notes."""

from __future__ import annotations

HEALTH_ROUTE = "/health"

# Pure compute contract (UI-agnostic)
COMPUTE_SIMULATE_LITE_ROUTE = "/v1/compute/simulate-lite"
COMPUTE_SIMULATE_FULL_ROUTE = "/v1/compute/simulate-full"

# Excel adapter routes (UI-coupled compatibility layer)
DEMO_INPUT_READ_ROUTE = "/v1/demo/input-read"
DEMO_OUTPUT_PACK_ROUTE = "/v1/demo/output-pack"
DEMO_SIMULATE_LITE_ROUTE = "/v1/demo/simulate-lite"
DEMO_OUTPUT_PACK_TSV_ROUTE = "/v1/demo/output-pack.tsv"
DEMO_SIMULATE_LITE_TSV_ROUTE = "/v1/demo/simulate-lite.tsv"

JSON_ROUTES = {
    DEMO_INPUT_READ_ROUTE,
    DEMO_OUTPUT_PACK_ROUTE,
    DEMO_SIMULATE_LITE_ROUTE,
    COMPUTE_SIMULATE_LITE_ROUTE,
    COMPUTE_SIMULATE_FULL_ROUTE,
}

TSV_ROUTES = {
    DEMO_OUTPUT_PACK_TSV_ROUTE,
    DEMO_SIMULATE_LITE_TSV_ROUTE,
}
