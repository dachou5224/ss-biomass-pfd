from __future__ import annotations

import pandas as pd

from .parameters import (
    DEFAULT_CASE_ID,
    DEFAULT_CHEMISTRY_SETUP,
    DEFAULT_REACTOR_SPECS,
    INCI_C_CONVERSION,  # noqa: F401 — 供 backend 等模块 from .data import
    feeds_to_tuples,
    load_json_config,
)
from .elemental import BIOMASS_SAMPLES
from .reference_streams import (
    attach_dbi_inci_boundary_to_expected,
    attach_inci_stream_to_expected,
    attach_rgpox_stream_to_expected,
)


def _build_reference_cases() -> dict:
    raw = load_json_config("reference_cases")
    cases: dict = {}
    for case_id, payload in raw.items():
        if case_id.startswith("_"):
            continue
        cases[case_id] = {
            "sample": payload["sample"],
            "feeds": feeds_to_tuples(payload["feeds"]),
            "expected": dict(payload["expected"]),
        }
    for case_id in cases:
        biomass_feed_kg_h = float((cases[case_id]["feeds"].get("Biomass") or (0.0, 0.0, 0.0))[0])
        expected = attach_dbi_inci_boundary_to_expected(
            cases[case_id]["expected"],
            case_id,
            biomass_feed_kg_h=biomass_feed_kg_h,
        )
        expected = attach_inci_stream_to_expected(expected, case_id)
        cases[case_id]["expected"] = attach_rgpox_stream_to_expected(expected, case_id)
    return cases


REFERENCE_CASES = _build_reference_cases()


def build_feed_df(case_id: str | None = None) -> pd.DataFrame:
    case_id = case_id or DEFAULT_CASE_ID
    case = REFERENCE_CASES[case_id]
    rows = []
    for stream_name, payload in case["feeds"].items():
        mass, temp_c, p_bar = payload
        rows.append(
            {
                "Stream": stream_name,
                "MassFlow_kg_h": mass,
                "Temp_C": temp_c,
                "Pressure_bar": p_bar,
            }
        )
    return pd.DataFrame(rows)


def build_specs_df() -> pd.DataFrame:
    rows = [{"Parameter": key, "Value": value} for key, value in DEFAULT_REACTOR_SPECS.items()]
    return pd.DataFrame(rows)


def build_chem_df(case_id: str | None = None) -> pd.DataFrame:
    case_id = case_id or DEFAULT_CASE_ID
    config = dict(DEFAULT_CHEMISTRY_SETUP)
    sample_id = REFERENCE_CASES[case_id]["sample"]
    config["Sample"] = sample_id
    sample = BIOMASS_SAMPLES[sample_id]
    config["Biomass VM Dry wt%"] = sample.vd_pct_dry
    config["Biomass FC Dry wt%"] = sample.fcd_pct_dry
    rows = [{"Field": key, "Value": value} for key, value in config.items()]
    return pd.DataFrame(rows)
