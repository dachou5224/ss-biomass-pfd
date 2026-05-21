"""WPS Excel 联调用轻量 WebService 逻辑（不执行全流程 Gibbs 求解）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping

from .web_ui import (
    O2IN_COMPOSITION_KEYS,
    PFD_FEED_LINES,
    build_chem_df_from_inputs,
    build_feed_df_from_inputs,
    build_specs_df_from_inputs,
    default_inputs,
)


@dataclass(frozen=True)
class LiteChecks:
    total_feed_kg_h: float
    total_inci_feed_kg_h: float
    total_rgpox_feed_kg_h: float
    total_slag_feed_kg_h: float
    o2in_sum_mol_pct: float
    o2in_is_100_pct: bool
    negative_feed_count: int


def _to_float(value: Any, *, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须为数字，当前={value!r}") from exc


def _merge_inputs(payload: Mapping[str, Any]) -> Dict[str, Any]:
    case_id = str(payload.get("case_id") or "Case-1")
    inputs = default_inputs(case_id)

    if "system_p_bar" in payload:
        inputs["system_p_bar"] = _to_float(payload["system_p_bar"], field="system_p_bar")

    if "pfd_feeds" in payload:
        pfd_feeds = dict(inputs.get("pfd_feeds") or {})
        for stream, raw in dict(payload["pfd_feeds"]).items():
            row = dict(raw or {})
            current = dict(pfd_feeds.get(stream) or {})
            if "mass_kg_h" in row:
                current["mass_kg_h"] = _to_float(row["mass_kg_h"], field=f"pfd_feeds.{stream}.mass_kg_h")
            if "temp_c" in row:
                current["temp_c"] = _to_float(row["temp_c"], field=f"pfd_feeds.{stream}.temp_c")
            if "pressure_bar" in row:
                current["pressure_bar"] = _to_float(row["pressure_bar"], field=f"pfd_feeds.{stream}.pressure_bar")
            pfd_feeds[str(stream)] = current
        inputs["pfd_feeds"] = pfd_feeds

    if "o2in_composition" in payload:
        comp = dict(inputs.get("o2in_composition") or {})
        for sp in O2IN_COMPOSITION_KEYS:
            if sp in payload["o2in_composition"]:
                comp[sp] = _to_float(payload["o2in_composition"][sp], field=f"o2in_composition.{sp}")
        inputs["o2in_composition"] = comp

    if "o2pox" in payload:
        o2pox = dict(inputs.get("o2pox") or {})
        raw_o2pox = dict(payload["o2pox"] or {})
        if "purity_vol_pct" in raw_o2pox:
            o2pox["purity_vol_pct"] = _to_float(raw_o2pox["purity_vol_pct"], field="o2pox.purity_vol_pct")
        inputs["o2pox"] = o2pox

    if "biomass" in payload:
        biomass = dict(inputs.get("biomass") or {})
        for key, val in dict(payload["biomass"] or {}).items():
            biomass[key] = val if key == "preset" else _to_float(val, field=f"biomass.{key}")
        inputs["biomass"] = biomass

    if "chemistry" in payload:
        chemistry = dict(inputs.get("chemistry") or {})
        for field, val in dict(payload["chemistry"] or {}).items():
            chemistry[str(field)] = val
        inputs["chemistry"] = chemistry

    return inputs


def _calc_checks(inputs: Mapping[str, Any]) -> LiteChecks:
    pfd_feeds = dict(inputs.get("pfd_feeds") or {})
    section_sum = {"INCI": 0.0, "RGPOX": 0.0, "SLAG": 0.0}
    negative = 0
    total = 0.0
    for line in PFD_FEED_LINES:
        mass = _to_float((pfd_feeds.get(line.backend_stream) or {}).get("mass_kg_h", 0.0), field=line.backend_stream)
        total += mass
        section_sum[line.section] += mass
        if mass < 0.0:
            negative += 1

    o2in = dict(inputs.get("o2in_composition") or {})
    o2_sum = sum(_to_float(o2in.get(sp, 0.0), field=f"o2in.{sp}") for sp in O2IN_COMPOSITION_KEYS)

    return LiteChecks(
        total_feed_kg_h=total,
        total_inci_feed_kg_h=section_sum["INCI"],
        total_rgpox_feed_kg_h=section_sum["RGPOX"],
        total_slag_feed_kg_h=section_sum["SLAG"],
        o2in_sum_mol_pct=o2_sum,
        o2in_is_100_pct=abs(o2_sum - 100.0) <= 0.2,
        negative_feed_count=negative,
    )


def build_input_read_response(payload: Mapping[str, Any]) -> Dict[str, Any]:
    inputs = _merge_inputs(payload)
    feed_df = build_feed_df_from_inputs(inputs)
    specs_df = build_specs_df_from_inputs(inputs)
    chem_df = build_chem_df_from_inputs(inputs)
    checks = _calc_checks(inputs)
    return {
        "mode": "input-read",
        "inputs": {
            "case_id": inputs["case_id"],
            "system_p_bar": inputs["system_p_bar"],
            "o2in_composition": dict(inputs.get("o2in_composition") or {}),
            "o2pox": dict(inputs.get("o2pox") or {}),
        },
        "tables": {
            "feed": feed_df.to_dict(orient="records"),
            "specs": specs_df.to_dict(orient="records"),
            "chemistry": chem_df.to_dict(orient="records"),
        },
        "checks": asdict(checks),
    }


def build_output_pack_response(payload: Mapping[str, Any]) -> Dict[str, Any]:
    base = build_compute_response(payload)
    checks = LiteChecks(**dict(base["checks"]))
    kpi_rows = [
        {"metric": "TOTAL_FEED_KG_H", "value": round(checks.total_feed_kg_h, 3), "unit": "kg/h"},
        {"metric": "INCI_FEED_KG_H", "value": round(checks.total_inci_feed_kg_h, 3), "unit": "kg/h"},
        {"metric": "RGPOX_FEED_KG_H", "value": round(checks.total_rgpox_feed_kg_h, 3), "unit": "kg/h"},
        {"metric": "SLAG_FEED_KG_H", "value": round(checks.total_slag_feed_kg_h, 3), "unit": "kg/h"},
        {"metric": "O2IN_SUM_MOL_PCT", "value": round(checks.o2in_sum_mol_pct, 4), "unit": "%"},
        {"metric": "NEGATIVE_FEED_COUNT", "value": checks.negative_feed_count, "unit": "-"},
    ]
    return {
        "mode": "output-pack",
        "status": base["status"],
        "kpi_rows": base["kpi_rows"],
        # VBA 可直接映射到命名区域
        "named_ranges": {
            "Output_Demo_KPI": [[row["metric"], row["value"], row["unit"]] for row in kpi_rows],
        },
        "checks": base["checks"],
    }


def build_compute_response(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """纯计算契约：仅返回计算结果，不包含任何 Excel/UI 映射结构。"""
    inputs = _merge_inputs(payload)
    checks = _calc_checks(inputs)
    kpi_rows = [
        {"metric": "TOTAL_FEED_KG_H", "value": round(checks.total_feed_kg_h, 3), "unit": "kg/h"},
        {"metric": "INCI_FEED_KG_H", "value": round(checks.total_inci_feed_kg_h, 3), "unit": "kg/h"},
        {"metric": "RGPOX_FEED_KG_H", "value": round(checks.total_rgpox_feed_kg_h, 3), "unit": "kg/h"},
        {"metric": "SLAG_FEED_KG_H", "value": round(checks.total_slag_feed_kg_h, 3), "unit": "kg/h"},
        {"metric": "O2IN_SUM_MOL_PCT", "value": round(checks.o2in_sum_mol_pct, 4), "unit": "%"},
        {"metric": "NEGATIVE_FEED_COUNT", "value": checks.negative_feed_count, "unit": "-"},
    ]
    return {
        "status": "ok" if checks.o2in_is_100_pct and checks.negative_feed_count == 0 else "check",
        "kpi_rows": kpi_rows,
        "checks": asdict(checks),
    }


def build_output_pack_tsv(payload: Mapping[str, Any]) -> str:
    out = build_output_pack_response(payload)
    rows = [("METRIC", "VALUE", "UNIT"), ("STATUS", out["status"], "-")]
    for row in out["kpi_rows"]:
        rows.append((str(row["metric"]), str(row["value"]), str(row["unit"])))
    return "\n".join("\t".join(r) for r in rows)
