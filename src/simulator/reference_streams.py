"""从 data/reference/ 加载 DBI 等参考物流表（CSV），供对标使用。

data/reference/ 下文件均自 PDF 提取，已列入 .gitignore，不得 push；见 data/reference/README.md。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .parameters import INCI_WET_MAJOR_KEYS, PATHS_CFG, PROJECT_ROOT

DEFAULT_INCI_STREAMS_CSV = PROJECT_ROOT / PATHS_CFG["inci_streams_csv"]
DEFAULT_RGPOX_STREAMS_CSV = PROJECT_ROOT / PATHS_CFG["rgpox_streams_csv"]
DEFAULT_DBI_MASS_BALANCE_CSV = PROJECT_ROOT / PATHS_CFG["dbi_mass_balance_csv"]


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
    stream = load_rgpox_stream_reference(case_id, csv_path=csv_path)
    if stream is None:
        return expected
    out = dict(expected)
    out["pox_comp_wet_full"] = dict(stream["wet_mol_pct"])
    out["pox_comp_dry_full"] = dict(stream["dry_full_mol_pct"])
    wet_major = dict(stream["wet_major_mol_pct"])
    out["pox_comp_wet"] = wet_major
    out["pox_stream_meta"] = dict(stream["meta"])
    return out


@lru_cache(maxsize=4)
def _load_dbi_mass_balance_csv(csv_path: str) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"DBI INCI 质量衡算表不存在: {path}")
    return pd.read_csv(path)


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
