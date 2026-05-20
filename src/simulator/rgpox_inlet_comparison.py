"""RGPOX 边界进料：DBI Unit 15 stream table vs 模型进料对比。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .data import REFERENCE_CASES
from .feed_streams import inci_o2_stream_species_kg_h, split_gas_stream_mass_kg_h
from .inlet_comparison import InletCompareRow, aggregate_inlet_comparison
from .parameters import (
    INLET_COMPARE_MIN_KG_H,
    dbi_rgpox_case1_inlet,
    dbi_rgpox_inlet_config,
    has_dbi_rgpox_inlet_config,
)
from .reference_streams import load_inci_stream_reference
from .species import INCI_UNMODELLED_WET_SPECIES


def _safe_rgpox_inlet_cfg() -> Dict[str, object] | None:
    if not has_dbi_rgpox_inlet_config():
        return None
    try:
        return dbi_rgpox_inlet_config()
    except (FileNotFoundError, KeyError, TypeError):
        return None


def _calc_rmsd_pct(pred: Dict[str, float], ref: Dict[str, float], keys: List[str]) -> float:
    if not keys:
        return 0.0
    arr = [pred.get(k, 0.0) - ref.get(k, 0.0) for k in keys]
    return float(np.sqrt(np.mean(np.square(arr))))


@dataclass(frozen=True)
class RgpoxInletAudit:
    """RGPOX 进料对标结果；`ready_for_ta_tuning` 为 False 时不应开始 TA 调参。"""

    case_id: str
    mass_rows: List[InletCompareRow]
    composition_rows: List[InletCompareRow]
    aggregated_mass: List[InletCompareRow]
    gas_wet_rmsd_pct: float | None
    ready_for_ta_tuning: bool
    blockers: Tuple[str, ...]


def _dbi_15ogi1_species_mass(total_kg_h: float) -> Dict[str, float]:
    try:
        og = dbi_rgpox_case1_inlet()["15OG1"]
    except (FileNotFoundError, KeyError, TypeError):
        return {}
    return split_gas_stream_mass_kg_h(total_kg_h, og["mol_pct"])


def _dbi_stream_mass_components(case_id: str) -> Dict[str, Dict[str, float]]:
    if case_id != "Case-1":
        return {}
    try:
        case = dbi_rgpox_case1_inlet()
        pgi = case["15PGI-1"]
        og = case["15OG1"]
    except (FileNotFoundError, KeyError, TypeError):
        return {}
    og_species = _dbi_15ogi1_species_mass(og["total_kg_h"])
    return {
        "15PGI-1": {
            "total": pgi["total_kg_h"],
            "fluid_gas": pgi["fluid_gas_kg_h"],
            "volatiles": pgi["volatiles_kg_h"],
            "solid": pgi["solid_kg_h"],
        },
        "15OG1": {
            "total": og["total_kg_h"],
            "oxygen_total": og["total_kg_h"],
            **og_species,
        },
    }


def _model_stream_mass_components(
    *,
    gas_mass_kg_h: float,
    tar_mass_kg_h: float,
    entrained_solid_kg_h: float,
    o2pox_total_kg_h: float,
    chem: Dict[str, str],
) -> Dict[str, Dict[str, float]]:
    og_species = inci_o2_stream_species_kg_h(o2pox_total_kg_h, chem)
    return {
        "15PGI-1": {
            "total": gas_mass_kg_h + tar_mass_kg_h + entrained_solid_kg_h,
            "fluid_gas": gas_mass_kg_h,
            "volatiles": tar_mass_kg_h,
            "solid": entrained_solid_kg_h,
        },
        "15OG1": {
            "total": o2pox_total_kg_h,
            "oxygen_total": o2pox_total_kg_h,
            **og_species,
        },
    }


def build_rgpox_inlet_mass_comparison(
    *,
    gas_mass_kg_h: float,
    tar_mass_kg_h: float,
    entrained_solid_kg_h: float,
    o2pox_total_kg_h: float,
    chem: Dict[str, str],
    case_id: str = "Case-1",
    mass_tol_kg_h: float = 0.1,
) -> List[InletCompareRow]:
    """按 15PGI-1 / 15OG1 分行对比质量流量 (kg/h)。"""
    dbi = _dbi_stream_mass_components(case_id)
    model = _model_stream_mass_components(
        gas_mass_kg_h=gas_mass_kg_h,
        tar_mass_kg_h=tar_mass_kg_h,
        entrained_solid_kg_h=entrained_solid_kg_h,
        o2pox_total_kg_h=o2pox_total_kg_h,
        chem=chem,
    )
    if not dbi:
        return []

    cfg = _safe_rgpox_inlet_cfg()
    if cfg is None:
        return []
    inlet_streams = tuple(cfg.get("rgpox_inlet_streams", ("15PGI-1", "15OG1")))

    line_keys = ("fluid_gas", "volatiles", "solid", "oxygen_total", "O2", "N2", "Ar", "total")
    rows: List[InletCompareRow] = []
    for stream_id in inlet_streams:
        d = dbi.get(stream_id, {})
        m = model.get(stream_id, {})
        keys = [k for k in line_keys if k in d or k in m]
        seen = set()
        for key in keys:
            if key in seen:
                continue
            seen.add(key)
            dv, mv = d.get(key, 0.0), m.get(key, 0.0)
            if abs(dv) < INLET_COMPARE_MIN_KG_H and abs(mv) < INLET_COMPARE_MIN_KG_H:
                continue
            rows.append(InletCompareRow(stream_id, key, dv, mv))
        rows.append(
            InletCompareRow(
                stream_id,
                "TOTAL",
                d.get("total", 0.0),
                m.get("total", 0.0),
            )
        )
    return rows


def build_rgpox_inlet_composition_comparison(
    gas_wet_vol_pct: Dict[str, float],
    *,
    case_id: str = "Case-1",
) -> List[InletCompareRow]:
    """15PGI-1 气相湿基 mol% vs DBI（与 13PGI-1 同源 CSV）。"""
    ref = load_inci_stream_reference(case_id)
    if ref is None:
        return []
    dbi_wet = ref["wet_mol_pct"]
    keys = sorted(set(dbi_wet) | set(gas_wet_vol_pct))
    rows: List[InletCompareRow] = []
    for comp in keys:
        if comp in INCI_UNMODELLED_WET_SPECIES:
            continue
        dv = dbi_wet.get(comp, 0.0)
        mv = gas_wet_vol_pct.get(comp, 0.0)
        if abs(dv) < 1e-6 and abs(mv) < 1e-6:
            continue
        rows.append(InletCompareRow("15PGI-1", comp, dv, mv))
    return rows


def assess_rgpox_inlet_readiness(
    mass_rows: List[InletCompareRow],
    composition_rows: List[InletCompareRow],
    *,
    mass_tol_kg_h: float,
    gas_wet_rmsd_limit: float,
) -> Tuple[bool, Tuple[str, ...], float | None]:
    blockers: List[str] = []

    check_lines = {
        ("15PGI-1", "solid"): "15PGI-1 夹带固相",
        ("15OG1", "oxygen_total"): "15OG1 氧枪质量",
    }
    for row in mass_rows:
        label = check_lines.get((row.stream_id, row.component))
        if label is None:
            continue
        if abs(row.delta_kg_h) > mass_tol_kg_h:
            blockers.append(
                f"{label}: DBI={row.dbi_kg_h:.2f} vs 模型={row.model_kg_h:.2f} kg/h (Δ={row.delta_kg_h:+.2f})"
            )

    dbi_wet = {r.component: r.dbi_kg_h for r in composition_rows}
    model_wet = {r.component: r.model_kg_h for r in composition_rows}
    cfg = _safe_rgpox_inlet_cfg()
    wet_ref_keys = tuple(cfg.get("compare_gas_wet_species", ())) if cfg is not None else ()
    wet_keys = [k for k in wet_ref_keys if k in dbi_wet]
    gas_rmsd = _calc_rmsd_pct(model_wet, dbi_wet, wet_keys) if wet_keys else None
    # 气相组成继承 INCI，不作为 TA 门禁阻塞项

    return len(blockers) == 0, tuple(blockers), gas_rmsd


def build_rgpox_inlet_audit(
    *,
    case_id: str,
    gas_mass_kg_h: float,
    gas_wet_vol_pct: Dict[str, float],
    tar_mass_kg_h: float,
    entrained_solid_kg_h: float,
    o2pox_total_kg_h: float,
    chem: Dict[str, str],
    mass_tol_kg_h: float,
    gas_wet_rmsd_limit: float,
) -> Optional[RgpoxInletAudit]:
    if case_id not in REFERENCE_CASES:
        return None
    if _safe_rgpox_inlet_cfg() is None:
        return None
    mass_rows = build_rgpox_inlet_mass_comparison(
        gas_mass_kg_h=gas_mass_kg_h,
        tar_mass_kg_h=tar_mass_kg_h,
        entrained_solid_kg_h=entrained_solid_kg_h,
        o2pox_total_kg_h=o2pox_total_kg_h,
        chem=chem,
        case_id=case_id,
        mass_tol_kg_h=mass_tol_kg_h,
    )
    comp_rows = build_rgpox_inlet_composition_comparison(gas_wet_vol_pct, case_id=case_id)
    ready, blockers, gas_rmsd = assess_rgpox_inlet_readiness(
        mass_rows,
        comp_rows,
        mass_tol_kg_h=mass_tol_kg_h,
        gas_wet_rmsd_limit=gas_wet_rmsd_limit,
    )
    return RgpoxInletAudit(
        case_id=case_id,
        mass_rows=mass_rows,
        composition_rows=comp_rows,
        aggregated_mass=aggregate_inlet_comparison(mass_rows),
        gas_wet_rmsd_pct=gas_rmsd,
        ready_for_ta_tuning=ready,
        blockers=blockers,
    )
