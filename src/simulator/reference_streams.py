"""从 data/reference/ 加载 DBI 等参考物流表（CSV），供对标使用。

data/reference/ 下文件均自 PDF 提取，已列入 .gitignore，不得 push；见 data/reference/README.md。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .parameters import INCI_WET_MAJOR_KEYS, PATHS_CFG, PROJECT_ROOT, load_json_config

DEFAULT_INCI_STREAMS_CSV = PROJECT_ROOT / PATHS_CFG["inci_streams_csv"]
DEFAULT_RGPOX_STREAMS_CSV = PROJECT_ROOT / PATHS_CFG["rgpox_streams_csv"]
DEFAULT_DBI_MASS_BALANCE_CSV = PROJECT_ROOT / PATHS_CFG["dbi_mass_balance_csv"]
DEFAULT_DBI_INCI_STREAM_TABLE_CSV = PROJECT_ROOT / "data/reference/dbi_inci_stream_table_case1.csv"


def _parse_percentish(value: Any) -> Optional[float]:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    return float(text)


def overall_biomass_carbon_conversion_from_boundary_streams(
    *,
    biomass_feed_kg_h: float,
    biomass_moisture_wt_pct: float,
    biomass_carbon_wt_pct_dry: float,
    bottom_slag_kg_h: float,
    bottom_slag_carbon_wt_pct_dry: float,
    entrained_solid_kg_h: float,
    entrained_solid_carbon_wt_pct_dry: float,
) -> Dict[str, float]:
    """Compute overall biomass carbon conversion from PFD/stream-table boundary solids."""
    dry_biomass_kg_h = max(float(biomass_feed_kg_h), 0.0) * max(100.0 - float(biomass_moisture_wt_pct), 0.0) / 100.0
    biomass_carbon_in_kg_h = dry_biomass_kg_h * max(float(biomass_carbon_wt_pct_dry), 0.0) / 100.0
    bottom_slag_carbon_kg_h = max(float(bottom_slag_kg_h), 0.0) * max(float(bottom_slag_carbon_wt_pct_dry), 0.0) / 100.0
    entrained_solid_carbon_kg_h = (
        max(float(entrained_solid_kg_h), 0.0) * max(float(entrained_solid_carbon_wt_pct_dry), 0.0) / 100.0
    )
    unconverted_carbon_kg_h = bottom_slag_carbon_kg_h + entrained_solid_carbon_kg_h
    conversion_pct = None
    if biomass_carbon_in_kg_h > 0.0:
        conversion_pct = 100.0 * (biomass_carbon_in_kg_h - unconverted_carbon_kg_h) / biomass_carbon_in_kg_h
    return {
        "biomass_dry_kg_h": dry_biomass_kg_h,
        "biomass_carbon_in_kg_h": biomass_carbon_in_kg_h,
        "bottom_slag_carbon_kg_h": bottom_slag_carbon_kg_h,
        "entrained_solid_carbon_kg_h": entrained_solid_carbon_kg_h,
        "unconverted_carbon_kg_h": unconverted_carbon_kg_h,
        "overall_biomass_carbon_conversion_pct": conversion_pct,
    }


def wet_mol_pct_to_dry_full(wet_mol_pct: Dict[str, float]) -> Dict[str, float]:
    """湿基 mol/mol % → 全干气 mol/mol %（分母 = 100 − H2O）。"""
    h2o = wet_mol_pct.get("H2O", 0.0)
    dry_sum = 100.0 - h2o
    if dry_sum <= 0.0:
        return {}
    return {k: round(v / dry_sum * 100.0, 5) for k, v in wet_mol_pct.items() if k != "H2O"}


def wet_mol_pct_major_subset(wet_mol_pct: Dict[str, float]) -> Dict[str, float]:
    """湿基全组分中提取主组分 + H2O 子集。"""
    return {k: wet_mol_pct[k] for k in INCI_WET_MAJOR_KEYS if k in wet_mol_pct}


@lru_cache(maxsize=4)
def _load_inci_streams_csv(csv_path: str) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"INCI 参考物流表不存在: {path}")
    return pd.read_csv(path)


def load_inci_stream_reference(
    case_id: str,
    *,
    csv_path: Path | str | None = None,
    stream_id: str = "13PGI-1",
    basis: str = "wet_mol_pct",
) -> Optional[Dict[str, Any]]:
    """
    按 case 读取 INCI 出口参考物流。

    返回 dict：meta（stream 工况）、wet_mol_pct、dry_full_mol_pct、wet_major_mol_pct。
    CSV 中无对应 case 时返回 None。
    """
    path = Path(csv_path) if csv_path is not None else DEFAULT_INCI_STREAMS_CSV
    df = _load_inci_streams_csv(str(path.resolve()))
    mask = (df["case"] == case_id) & (df["stream_id"] == stream_id) & (df["basis"] == basis)
    subset = df.loc[mask]
    if subset.empty:
        return None

    row0 = subset.iloc[0]
    meta = {
        "stream_id": str(row0["stream_id"]),
        "description": str(row0["description"]),
        "temperature_c": float(row0["temperature_c"]),
        "pressure_mpa_a": float(row0["pressure_mpa_a"]),
        "gas_flow_kg_h": float(row0["gas_flow_kg_h"]),
        "total_flow_kg_h": float(row0["total_flow_kg_h"]),
        "source": str(row0["source"]),
    }
    wet_mol_pct = {str(r["component"]): float(r["mol_pct"]) for _, r in subset.iterrows()}
    return {
        "meta": meta,
        "wet_mol_pct": wet_mol_pct,
        "dry_full_mol_pct": wet_mol_pct_to_dry_full(wet_mol_pct),
        "wet_major_mol_pct": wet_mol_pct_major_subset(wet_mol_pct),
    }


def attach_inci_stream_to_expected(
    expected: Dict[str, Any],
    case_id: str,
    *,
    csv_path: Path | str | None = None,
) -> Dict[str, Any]:
    """将 CSV 中的 INCI 全组分表合并进 REFERENCE_CASES expected 字段。"""
    stream = load_inci_stream_reference(case_id, csv_path=csv_path)
    if stream is None:
        return expected
    out = dict(expected)
    out["inci_comp_wet_full"] = dict(stream["wet_mol_pct"])
    out["inci_comp_dry_full"] = dict(stream["dry_full_mol_pct"])
    out["inci_comp_wet"] = dict(stream["wet_major_mol_pct"])
    out["inci_stream_meta"] = dict(stream["meta"])
    return out


@lru_cache(maxsize=4)
def _load_rgpox_streams_csv(csv_path: str) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"RGPOX 参考物流表不存在: {path}")
    return pd.read_csv(path)


def load_rgpox_stream_reference(
    case_id: str,
    *,
    csv_path: Path | str | None = None,
    stream_id: str = "15PGR-2",
    basis: str = "wet_mol_pct",
) -> Optional[Dict[str, Any]]:
    """按 case 读取 RGPOX 出口参考物流（默认 15PGR-2 湿基）。"""
    path = Path(csv_path) if csv_path is not None else DEFAULT_RGPOX_STREAMS_CSV
    if not path.is_file():
        return None
    df = _load_rgpox_streams_csv(str(path.resolve()))
    mask = (df["case"] == case_id) & (df["stream_id"] == stream_id) & (df["basis"] == basis)
    subset = df.loc[mask]
    if subset.empty:
        return None

    row0 = subset.iloc[0]
    meta = {
        "stream_id": str(row0["stream_id"]),
        "description": str(row0["description"]),
        "temperature_c": float(row0["temperature_c"]),
        "pressure_mpa_a": float(row0["pressure_mpa_a"]),
        "gas_flow_kg_h": float(row0["gas_flow_kg_h"]),
        "total_flow_kg_h": float(row0.get("total_flow_kg_h", row0["gas_flow_kg_h"])),
        "source": str(row0["source"]),
    }
    wet_mol_pct = {str(r["component"]): float(r["mol_pct"]) for _, r in subset.iterrows()}
    return {
        "meta": meta,
        "wet_mol_pct": wet_mol_pct,
        "dry_full_mol_pct": wet_mol_pct_to_dry_full(wet_mol_pct),
        "wet_major_mol_pct": wet_mol_pct_major_subset(wet_mol_pct),
    }


def attach_rgpox_stream_to_expected(
    expected: Dict[str, Any],
    case_id: str,
    *,
    csv_path: Path | str | None = None,
) -> Dict[str, Any]:
    """将 CSV 中的 RGPOX 湿基表合并进 expected（本地 CSV 缺失时保留 JSON 内 pox_comp_wet）。"""
    post = load_rgpox_stream_reference(case_id, csv_path=csv_path, stream_id="15PGR-2", basis="wet_mol_pct")
    ante = load_rgpox_stream_reference(case_id, csv_path=csv_path, stream_id="15PGR-1", basis="wet_mol_pct")
    if post is None and ante is None:
        return expected
    out = dict(expected)
    if post is not None:
        out["pox_comp_wet_full"] = dict(post["wet_mol_pct"])
        out["pox_comp_dry_full"] = dict(post["dry_full_mol_pct"])
        out["pox_comp_wet"] = dict(post["wet_major_mol_pct"])
        out["pox_stream_meta"] = dict(post["meta"])
        out["pox_gas_kg_h"] = float(post["meta"]["gas_flow_kg_h"])
    if ante is not None:
        out["pox_comp_wet_ante_full"] = dict(ante["wet_mol_pct"])
        out["pox_comp_wet_ante"] = dict(ante["wet_major_mol_pct"])
        out["pox_gibbs_stream_meta"] = dict(ante["meta"])
        out["pox_gas_ante_kg_h"] = float(ante["meta"]["gas_flow_kg_h"])
    return out


def expected_pox_gas_ante_kg_h(expected: Dict[str, Any]) -> float:
    """DBI 15PGR-1 湿煤气目标 (kg/h)；优先 JSON/CSV 显式字段，禁止湿基反推。"""
    if expected.get("pox_gas_ante_kg_h") is not None:
        return float(expected["pox_gas_ante_kg_h"])
    raise KeyError("expected 缺少 pox_gas_ante_kg_h（Unit 15 PDF 15PGR-1 湿煤气 7760 kg/h）")


@lru_cache(maxsize=4)
def _load_dbi_mass_balance_csv(csv_path: str) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"DBI INCI 质量衡算表不存在: {path}")
    return pd.read_csv(path)


@lru_cache(maxsize=4)
def _load_dbi_inci_stream_table_csv(csv_path: str) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"DBI INCI stream table 不存在: {path}")
    return pd.read_csv(path)


def load_dbi_inci_stream_value(
    case_id: str,
    *,
    stream_id: str,
    section: str,
    property: str,
    csv_path: Path | str | None = None,
) -> Optional[Dict[str, Any]]:
    """Read a single scalar value from the Unit 13 DBI stream table."""
    path = Path(csv_path) if csv_path is not None else DEFAULT_DBI_INCI_STREAM_TABLE_CSV
    if not path.is_file():
        return None
    df = _load_dbi_inci_stream_table_csv(str(path.resolve()))
    mask = (
        (df["case"] == case_id)
        & (df["stream_id"] == stream_id)
        & (df["section"] == section)
        & (df["property"] == property)
    )
    subset = df.loc[mask]
    if subset.empty:
        return None
    row0 = subset.iloc[0]
    return {
        "stream_id": stream_id,
        "section": section,
        "property": property,
        "unit": str(row0["unit"]),
        "value_raw": row0["value"],
        "value": _parse_percentish(row0["value"]),
    }


def load_dbi_inci_mass_balance(
    case_id: str,
    *,
    csv_path: Path | str | None = None,
) -> Optional[Dict[str, Any]]:
    """
    加载 DBI INCI 边界质量衡算参考（净进料 + 出口分相）。

    仅含越过 INCI 包络的 stream；p2 表中 13HS1-2~5 / 13OG2-2~5 等为总管→烧嘴内部分配，不在此列。
    """
    path = Path(csv_path) if csv_path is not None else DEFAULT_DBI_MASS_BALANCE_CSV
    df = _load_dbi_mass_balance_csv(str(path.resolve()))
    subset = df.loc[df["case"] == case_id].copy()
    if subset.empty:
        return None

    def _rows(role: str) -> List[Dict[str, Any]]:
        part = subset.loc[subset["balance_role"] == role]
        out: List[Dict[str, Any]] = []
        for _, r in part.iterrows():
            mass = r["mass_kg_h"]
            out.append(
                {
                    "stream_id": str(r["stream_id"]),
                    "description": str(r["description"]),
                    "direction": str(r["direction"]),
                    "balance_role": role,
                    "mass_kg_h": float(mass) if pd.notna(mass) else None,
                    "model_feed_key": str(r["model_feed_key"]) if pd.notna(r.get("model_feed_key")) else "",
                    "note": str(r["note"]) if pd.notna(r.get("note")) else "",
                }
            )
        return out

    net_inlet = _rows("net_inlet")
    outlet_roles = (
        "outlet_gas",
        "outlet_volatiles",
        "outlet_entrained_solid",
        "outlet_total",
        "outlet_slag",
        "bypass",
    )
    outlets: List[Dict[str, Any]] = []
    for role in outlet_roles:
        outlets.extend(_rows(role))

    def _sum_mass(rows: List[Dict[str, Any]]) -> float | None:
        vals = [r["mass_kg_h"] for r in rows if r["mass_kg_h"] is not None]
        return sum(vals) if vals else None

    return {
        "case_id": case_id,
        "net_inlet": net_inlet,
        "outlets": outlets,
        "net_inlet_sum_kg_h": _sum_mass(net_inlet),
        "outlet_gas_kg_h": next((r["mass_kg_h"] for r in outlets if r["balance_role"] == "outlet_gas"), None),
        "outlet_volatiles_kg_h": next(
            (r["mass_kg_h"] for r in outlets if r["balance_role"] == "outlet_volatiles"), None
        ),
        "outlet_entrained_kg_h": next(
            (r["mass_kg_h"] for r in outlets if r["balance_role"] == "outlet_entrained_solid"), None
        ),
        "outlet_total_kg_h": next((r["mass_kg_h"] for r in outlets if r["balance_role"] == "outlet_total"), None),
        "outlet_slag_kg_h": next((r["mass_kg_h"] for r in outlets if r["balance_role"] == "outlet_slag"), None),
        "net_steam_kg_h": next(
            (r["mass_kg_h"] for r in net_inlet if r["stream_id"] == "13HS1-1"), None
        ),
        "net_oxygen_kg_h": next(
            (r["mass_kg_h"] for r in net_inlet if r["stream_id"] == "13OG2-1"), None
        ),
        "net_steam_oxygen_sum_kg_h": (
            (next((r["mass_kg_h"] for r in net_inlet if r["stream_id"] == "13HS1-1"), 0.0) or 0.0)
            + (next((r["mass_kg_h"] for r in net_inlet if r["stream_id"] == "13OG2-1"), 0.0) or 0.0)
        ),
    }


def attach_dbi_inci_boundary_to_expected(
    expected: Dict[str, Any],
    case_id: str,
    *,
    biomass_feed_kg_h: float | None = None,
    stream_table_csv: Path | str | None = None,
) -> Dict[str, Any]:
    """Attach DBI INCI boundary-carbon basis derived from PFD/stream-table data when available."""
    if biomass_feed_kg_h is None:
        return expected

    moisture = load_dbi_inci_stream_value(
        case_id,
        stream_id="13C-4",
        section="solid_phase",
        property="moisture",
        csv_path=stream_table_csv,
    )
    biomass_carbon = load_dbi_inci_stream_value(
        case_id,
        stream_id="13C-4",
        section="solid_phase",
        property="carbon",
        csv_path=stream_table_csv,
    )
    slag_carbon = load_dbi_inci_stream_value(
        case_id,
        stream_id="13LBS-1",
        section="solid_phase",
        property="carbon",
        csv_path=stream_table_csv,
    )
    if moisture is None or biomass_carbon is None or slag_carbon is None:
        return expected

    try:
        rgpox_cfg = dict(load_json_config("dbi_rgpox_inlet").get(case_id, {})).get("15PGI-1", {})
    except FileNotFoundError:
        return expected
    solid_kg_h = rgpox_cfg.get("solid_kg_h")
    solid_carbon_wt_pct_dry = rgpox_cfg.get("solid_dust_carbon_wt_pct_dry")
    if solid_kg_h is None or solid_carbon_wt_pct_dry is None:
        return expected

    basis = overall_biomass_carbon_conversion_from_boundary_streams(
        biomass_feed_kg_h=biomass_feed_kg_h,
        biomass_moisture_wt_pct=float(moisture["value"] or 0.0),
        biomass_carbon_wt_pct_dry=float(biomass_carbon["value"] or 0.0),
        bottom_slag_kg_h=float(expected.get("inci_slag_kg_h", 0.0)),
        bottom_slag_carbon_wt_pct_dry=float(slag_carbon["value"] or 0.0),
        entrained_solid_kg_h=float(solid_kg_h),
        entrained_solid_carbon_wt_pct_dry=float(solid_carbon_wt_pct_dry),
    )
    out = dict(expected)
    out["dbi_inci_boundary_basis"] = {
        **basis,
        "biomass_feed_kg_h": float(biomass_feed_kg_h),
        "biomass_moisture_wt_pct": float(moisture["value"] or 0.0),
        "biomass_carbon_wt_pct_dry": float(biomass_carbon["value"] or 0.0),
        "bottom_slag_total_kg_h": float(expected.get("inci_slag_kg_h", 0.0)),
        "bottom_slag_carbon_wt_pct_dry": float(slag_carbon["value"] or 0.0),
        "entrained_solid_total_kg_h": float(solid_kg_h),
        "entrained_solid_carbon_wt_pct_dry": float(solid_carbon_wt_pct_dry),
        "basis_streams": {
            "biomass_feed": "13C-4",
            "bottom_slag": "13LBS-1",
            "entrained_solid": "15PGI-1",
        },
    }
    return out
