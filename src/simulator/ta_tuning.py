"""INCI WGS / 甲烷化 TA 湿基组成调参（对标 DBI 13PGI-1 湿基主组分 + H2O）。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from . import rgpox as rgpox_mod
from .backend import _calc_rmsd_pct, run_fixed_temperature_simulation
from .data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from .parameters import INCI_WET_MAJOR_KEYS, RGPOX_CFG, model_parameters
from .rgpox import o2_to_gibbs_char_mol_ratio_from_cfg

TA_CHEM_FIELDS = (
    "TA DeltaT WGS (C)",
    "TA DeltaT Meth (C)",
    "WGS Equilibrium Approach Eta",
    "Meth Equilibrium Approach Eta",
)


@dataclass(frozen=True)
class TaTuneResult:
    case_id: str
    rmsd_wet_pct: float
    dt_wgs_c: float
    dt_meth_c: float
    eta_wgs: float
    eta_meth: float
    comp_wet_vol_pct: Dict[str, float]

    @property
    def h2o_wet_pct(self) -> float:
        return float(self.comp_wet_vol_pct.get("H2O", 0.0))


def wet_major_reference(case_id: str) -> Optional[Dict[str, float]]:
    expected = REFERENCE_CASES.get(case_id, {}).get("expected", {})
    ref = expected.get("inci_comp_wet")
    if not ref:
        wet_full = expected.get("inci_comp_wet_full")
        if not wet_full:
            return None
        ref = {k: wet_full[k] for k in INCI_WET_MAJOR_KEYS if k in wet_full}
    return dict(ref)


def set_ta_on_chem_df(
    chem_df: pd.DataFrame,
    *,
    dt_wgs_c: float,
    dt_meth_c: float,
    eta_wgs: float,
    eta_meth: float,
) -> pd.DataFrame:
    out = chem_df.copy()
    for field, val in zip(
        TA_CHEM_FIELDS,
        (dt_wgs_c, dt_meth_c, eta_wgs, eta_meth),
    ):
        out.loc[out["Field"] == field, "Value"] = val
    return out


def evaluate_inci_wet_rmsd(
    case_id: str,
    *,
    dt_wgs_c: float,
    dt_meth_c: float,
    eta_wgs: float,
    eta_meth: float,
    feed_df: Optional[pd.DataFrame] = None,
    specs_df: Optional[pd.DataFrame] = None,
    chem_df: Optional[pd.DataFrame] = None,
) -> TaTuneResult:
    ref = wet_major_reference(case_id)
    if ref is None:
        raise ValueError(f"工况 {case_id} 无湿基参考组成 (inci_comp_wet / inci_comp_wet_full)")

    feed_df = feed_df if feed_df is not None else build_feed_df(case_id)
    specs_df = specs_df if specs_df is not None else build_specs_df()
    base_chem = chem_df if chem_df is not None else build_chem_df(case_id)
    chem = set_ta_on_chem_df(
        base_chem,
        dt_wgs_c=dt_wgs_c,
        dt_meth_c=dt_meth_c,
        eta_wgs=eta_wgs,
        eta_meth=eta_meth,
    )
    res = run_fixed_temperature_simulation(feed_df, specs_df, chem)
    model = res.inci_comp_wet_vol_pct
    keys = [k for k in INCI_WET_MAJOR_KEYS if k in ref]
    rmsd = _calc_rmsd_pct(model, ref, keys)
    return TaTuneResult(
        case_id=case_id,
        rmsd_wet_pct=rmsd,
        dt_wgs_c=dt_wgs_c,
        dt_meth_c=dt_meth_c,
        eta_wgs=eta_wgs,
        eta_meth=eta_meth,
        comp_wet_vol_pct=dict(model),
    )


def grid_search_inci_ta(
    case_id: str = "Case-1",
    *,
    dt_wgs_values: Sequence[float] = (-60, -30, 0, 30, 60, 70, 80),
    dt_meth_values: Sequence[float] = (0, 200, 300, 375, 400, 500, 600),
    eta_wgs_values: Sequence[float] = (0.3, 0.45, 0.6, 0.75, 1.0),
    eta_meth_values: Sequence[float] = (0.2, 0.4, 0.55, 0.7),
) -> List[TaTuneResult]:
    """笛卡尔网格扫描；按湿基五组分 RMSD 升序返回。"""
    if wet_major_reference(case_id) is None:
        raise ValueError(f"工况 {case_id} 无湿基参考表，无法调参")

    feed_df = build_feed_df(case_id)
    specs_df = build_specs_df()
    chem_df = build_chem_df(case_id)
    results: List[TaTuneResult] = []
    for dt_wgs in dt_wgs_values:
        for dt_meth in dt_meth_values:
            for eta_wgs in eta_wgs_values:
                for eta_meth in eta_meth_values:
                    results.append(
                        evaluate_inci_wet_rmsd(
                            case_id,
                            dt_wgs_c=float(dt_wgs),
                            dt_meth_c=float(dt_meth),
                            eta_wgs=float(eta_wgs),
                            eta_meth=float(eta_meth),
                            feed_df=feed_df,
                            specs_df=specs_df,
                            chem_df=chem_df,
                        )
                    )
    results.sort(key=lambda r: (r.rmsd_wet_pct, abs(r.h2o_wet_pct - ref_h2o(case_id))))
    return results


def ref_h2o(case_id: str) -> float:
    ref = wet_major_reference(case_id) or {}
    return float(ref.get("H2O", 0.0))


def best_inci_ta_for_wet(
    case_id: str = "Case-1",
    **grid_kwargs,
) -> TaTuneResult:
    return grid_search_inci_ta(case_id, **grid_kwargs)[0]


# --- RGPOX 湿基 TA（对标 15PGR-2 / pox_comp_wet）---

RGPOX_TA_CHEM_FIELDS = (
    "RGPOX TA DeltaT WGS (C)",
    "RGPOX TA DeltaT Meth (C)",
    "RGPOX WGS Equilibrium Approach Eta",
    "RGPOX Meth Equilibrium Approach Eta",
    "RGPOX TA DeltaT OxCO (C)",
    "RGPOX TA DeltaT OxH2 (C)",
    "RGPOX TA DeltaT OxCH4 (C)",
)


@dataclass(frozen=True)
class RgpoxTaTuneResult:
    case_id: str
    rmsd_wet_pct: float
    dt_wgs_c: float
    dt_meth_c: float
    eta_wgs: float
    eta_meth: float
    dt_ox_co_c: float
    dt_ox_h2_c: float
    dt_ox_ch4_c: float
    comp_wet_vol_pct: Dict[str, float]

    @property
    def h2o_wet_pct(self) -> float:
        return float(self.comp_wet_vol_pct.get("H2O", 0.0))


def rgpox_wet_major_reference(case_id: str, *, ante_quench: bool = True) -> Optional[Dict[str, float]]:
    """RGPOX 湿基对标：默认 15PGR-1 反应区 @1400°C（Gibbs+TA）；急冷后见 pox_comp_wet。"""
    expected = REFERENCE_CASES.get(case_id, {}).get("expected", {})
    if ante_quench:
        ref = expected.get("pox_comp_wet_ante")
        if ref:
            return dict(ref)
    ref = expected.get("pox_comp_wet")
    if ref:
        return dict(ref)
    wet_full = expected.get("pox_comp_wet_full")
    if not wet_full:
        return None
    return {k: wet_full[k] for k in INCI_WET_MAJOR_KEYS if k in wet_full}


def set_rgpox_ta_on_chem_df(
    chem_df: pd.DataFrame,
    *,
    dt_wgs_c: float,
    dt_meth_c: float,
    eta_wgs: float,
    eta_meth: float,
    dt_ox_co_c: float = 0.0,
    dt_ox_h2_c: float = 0.0,
    dt_ox_ch4_c: float = 0.0,
) -> pd.DataFrame:
    out = chem_df.copy()
    pairs = (
        (RGPOX_TA_CHEM_FIELDS[0], dt_wgs_c),
        (RGPOX_TA_CHEM_FIELDS[1], dt_meth_c),
        (RGPOX_TA_CHEM_FIELDS[2], eta_wgs),
        (RGPOX_TA_CHEM_FIELDS[3], eta_meth),
        (RGPOX_TA_CHEM_FIELDS[4], dt_ox_co_c),
        (RGPOX_TA_CHEM_FIELDS[5], dt_ox_h2_c),
        (RGPOX_TA_CHEM_FIELDS[6], dt_ox_ch4_c),
    )
    for field, val in pairs:
        out.loc[out["Field"] == field, "Value"] = val
    return out


def evaluate_rgpox_wet_rmsd(
    case_id: str,
    *,
    dt_wgs_c: float,
    dt_meth_c: float,
    eta_wgs: float,
    eta_meth: float,
    dt_ox_co_c: float = 0.0,
    dt_ox_h2_c: float = 0.0,
    dt_ox_ch4_c: float = 0.0,
    feed_df: Optional[pd.DataFrame] = None,
    specs_df: Optional[pd.DataFrame] = None,
    chem_df: Optional[pd.DataFrame] = None,
) -> RgpoxTaTuneResult:
    ref = rgpox_wet_major_reference(case_id)
    if ref is None:
        raise ValueError(f"工况 {case_id} 无 pox_comp_wet 参考")

    feed_df = feed_df if feed_df is not None else build_feed_df(case_id)
    specs_df = specs_df if specs_df is not None else build_specs_df()
    base_chem = chem_df if chem_df is not None else build_chem_df(case_id)
    chem = set_rgpox_ta_on_chem_df(
        base_chem,
        dt_wgs_c=dt_wgs_c,
        dt_meth_c=dt_meth_c,
        eta_wgs=eta_wgs,
        eta_meth=eta_meth,
        dt_ox_co_c=dt_ox_co_c,
        dt_ox_h2_c=dt_ox_h2_c,
        dt_ox_ch4_c=dt_ox_ch4_c,
    )
    res = run_fixed_temperature_simulation(feed_df, specs_df, chem)
    if res.rgpox_inlet_audit and not res.rgpox_inlet_audit.ready_for_ta_tuning:
        raise RuntimeError(f"RGPOX 进料门禁未通过: {res.rgpox_inlet_audit.blockers}")
    model = res.pox_comp_wet_ante_vol_pct
    keys = [k for k in INCI_WET_MAJOR_KEYS if k in ref]
    rmsd = _calc_rmsd_pct(model, ref, keys)
    return RgpoxTaTuneResult(
        case_id=case_id,
        rmsd_wet_pct=rmsd,
        dt_wgs_c=dt_wgs_c,
        dt_meth_c=dt_meth_c,
        eta_wgs=eta_wgs,
        eta_meth=eta_meth,
        dt_ox_co_c=dt_ox_co_c,
        dt_ox_h2_c=dt_ox_h2_c,
        dt_ox_ch4_c=dt_ox_ch4_c,
        comp_wet_vol_pct=dict(model),
    )


def ref_rgpox_h2o(case_id: str) -> float:
    ref = rgpox_wet_major_reference(case_id) or {}
    return float(ref.get("H2O", 0.0))


def grid_search_rgpox_ta(
    case_id: str = "Case-1",
    *,
    dt_wgs_values: Sequence[float] = (-120, -80, -40, 0, 40, 80),
    dt_meth_values: Sequence[float] = (-200, 0, 200, 400),
    dt_ox_co_values: Sequence[float] = (0.0,),
    dt_ox_h2_values: Sequence[float] = (0.0,),
    dt_ox_ch4_values: Sequence[float] = (0.0,),
    eta_wgs_values: Sequence[float] = (1.0,),
    eta_meth_values: Sequence[float] = (1.0,),
) -> List[RgpoxTaTuneResult]:
    if rgpox_wet_major_reference(case_id) is None:
        raise ValueError(f"工况 {case_id} 无 pox_comp_wet，无法调参")

    feed_df = build_feed_df(case_id)
    specs_df = build_specs_df()
    chem_df = build_chem_df(case_id)
    results: List[RgpoxTaTuneResult] = []
    for dt_wgs in dt_wgs_values:
        for dt_meth in dt_meth_values:
            for eta_wgs in eta_wgs_values:
                for eta_meth in eta_meth_values:
                    for dt_ox_co in dt_ox_co_values:
                        for dt_ox_h2 in dt_ox_h2_values:
                            for dt_ox_ch4 in dt_ox_ch4_values:
                                results.append(
                                    evaluate_rgpox_wet_rmsd(
                                        case_id,
                                        dt_wgs_c=float(dt_wgs),
                                        dt_meth_c=float(dt_meth),
                                        eta_wgs=float(eta_wgs),
                                        eta_meth=float(eta_meth),
                                        dt_ox_co_c=float(dt_ox_co),
                                        dt_ox_h2_c=float(dt_ox_h2),
                                        dt_ox_ch4_c=float(dt_ox_ch4),
                                        feed_df=feed_df,
                                        specs_df=specs_df,
                                        chem_df=chem_df,
                                    )
                                )
    h2o_ref = ref_rgpox_h2o(case_id)
    results.sort(key=lambda r: (r.rmsd_wet_pct, abs(r.h2o_wet_pct - h2o_ref)))
    return results


def best_rgpox_ta_for_wet(case_id: str = "Case-1", **grid_kwargs) -> RgpoxTaTuneResult:
    return grid_search_rgpox_ta(case_id, **grid_kwargs)[0]


# --- Phase 6：middle-way + 气相/异相 TA 联合扫描（η 固定 1.0）---

PHASE6_MIDDLE_WAY_CHAR: Dict[str, Any] = {
    "o2_to_gibbs_mode": "full_feed",
    "reaction_sequence": "gas_equilibrium_first",
    "post_char_use_remaining_o2": False,
    "enable_steam_gasification": True,
    "enable_boudouard": True,
    "char_co2_replace_fraction": 0.0,
    "char_steam_fraction": 1.0,
    "gasification_order": "steam_first",
}


def _major_four_abs_max_pp(delta_pp: Mapping[str, float]) -> float:
    return max(abs(float(delta_pp.get(k, 0.0))) for k in ("CO", "CO2", "H2", "H2O"))


def meets_phase6d_targets(
    row: RgpoxCombinedTaTuneResult,
    *,
    co_co2_max_pp: float = 1.5,
    h2_h2o_max_pp: float = 2.0,
    min_ante_kg_h: float = 7680.0,
) -> bool:
    d = row.delta_pp
    return (
        row.pox_gas_ante_kg_h >= min_ante_kg_h
        and abs(d.get("CO", 0.0)) <= co_co2_max_pp
        and abs(d.get("CO2", 0.0)) <= co_co2_max_pp
        and abs(d.get("H2", 0.0)) <= h2_h2o_max_pp
        and abs(d.get("H2O", 0.0)) <= h2_h2o_max_pp
    )


@dataclass(frozen=True)
class RgpoxCombinedTaTuneResult:
    case_id: str
    rmsd_wet_pct: float
    dt_wgs_c: float
    dt_meth_c: float
    dt_ox_co_c: float
    dt_ox_h2_c: float
    dt_ox_ch4_c: float
    dt_boudouard_c: float
    dt_char_steam_c: float
    char_boud_fraction: float | None
    comp_wet_vol_pct: Dict[str, float]
    delta_pp: Dict[str, float]
    pox_gas_ante_kg_h: float
    pox_ash_kg_h: float

    @property
    def h2o_wet_pct(self) -> float:
        return float(self.comp_wet_vol_pct.get("H2O", 0.0))

    @property
    def co_co2_mae_pp(self) -> float:
        return _co_co2_mae_pp(self.delta_pp)


def evaluate_rgpox_combined_ta(
    case_id: str,
    *,
    dt_wgs_c: float,
    dt_meth_c: float = 0.0,
    dt_ox_co_c: float = 0.0,
    dt_ox_h2_c: float = 0.0,
    dt_ox_ch4_c: float = 0.0,
    dt_boudouard_c: float = 0.0,
    dt_char_steam_c: float = 0.0,
    char_overrides: Mapping[str, Any] | None = None,
    feed_df: Optional[pd.DataFrame] = None,
    specs_df: Optional[pd.DataFrame] = None,
    chem_df: Optional[pd.DataFrame] = None,
) -> RgpoxCombinedTaTuneResult:
    """气相 TA + char 异相 TA 联合评估；所有 η 固定 1.0。"""
    ref = rgpox_wet_major_reference(case_id)
    if ref is None:
        raise ValueError(f"工况 {case_id} 无 pox_comp_wet_ante / pox_comp_wet 参考")

    feed_df = feed_df if feed_df is not None else build_feed_df(case_id)
    specs_df = specs_df if specs_df is not None else build_specs_df()
    base_chem = chem_df if chem_df is not None else build_chem_df(case_id)
    chem = set_rgpox_ta_on_chem_df(
        base_chem,
        dt_wgs_c=float(dt_wgs_c),
        dt_meth_c=float(dt_meth_c),
        eta_wgs=1.0,
        eta_meth=1.0,
        dt_ox_co_c=float(dt_ox_co_c),
        dt_ox_h2_c=float(dt_ox_h2_c),
        dt_ox_ch4_c=float(dt_ox_ch4_c),
    )

    hetero_ta = {
        "enabled": True,
        "dt_boudouard_c": float(dt_boudouard_c),
        "dt_char_steam_c": float(dt_char_steam_c),
        "eta_boudouard": 1.0,
        "eta_char_steam": 1.0,
    }
    merged_char = {**PHASE6_MIDDLE_WAY_CHAR, **dict(char_overrides or {}), "hetero_ta": hetero_ta}
    alpha_raw = merged_char.get("char_boud_fraction")
    char_boud_fraction = None if alpha_raw is None else float(alpha_raw)
    with patched_rgpox_char_gasification(merged_char):
        res = run_fixed_temperature_simulation(feed_df, specs_df, chem)
    if res.rgpox_inlet_audit and not res.rgpox_inlet_audit.ready_for_ta_tuning:
        raise RuntimeError(f"RGPOX 进料门禁未通过: {res.rgpox_inlet_audit.blockers}")

    model = res.pox_comp_wet_ante_vol_pct
    keys = [k for k in INCI_WET_MAJOR_KEYS if k in ref]
    rmsd = _calc_rmsd_pct(model, ref, keys)
    delta = _wet_delta_pp(model, ref)
    return RgpoxCombinedTaTuneResult(
        case_id=case_id,
        rmsd_wet_pct=rmsd,
        dt_wgs_c=float(dt_wgs_c),
        dt_meth_c=float(dt_meth_c),
        dt_ox_co_c=float(dt_ox_co_c),
        dt_ox_h2_c=float(dt_ox_h2_c),
        dt_ox_ch4_c=float(dt_ox_ch4_c),
        dt_boudouard_c=float(dt_boudouard_c),
        dt_char_steam_c=float(dt_char_steam_c),
        char_boud_fraction=char_boud_fraction,
        comp_wet_vol_pct=dict(model),
        delta_pp=delta,
        pox_gas_ante_kg_h=float(res.pox_gas_ante_kg_h),
        pox_ash_kg_h=float(res.pox_ash_kg_h),
    )


def grid_search_rgpox_combined_ta(
    case_id: str = "Case-1",
    *,
    dt_wgs_values: Sequence[float] = (-120, -80, -40, 0, 40),
    dt_meth_values: Sequence[float] = (0.0, 200.0),
    dt_ox_co_values: Sequence[float] = (0.0,),
    dt_ox_h2_values: Sequence[float] = (0.0,),
    dt_ox_ch4_values: Sequence[float] = (0.0,),
    dt_boudouard_values: Sequence[float] = (-80, -40, 0, 40, 80),
    dt_char_steam_values: Sequence[float] = (-80, -40, 0, 40, 80),
    char_boud_fraction_values: Sequence[float | None] = (None,),
    char_overrides: Mapping[str, Any] | None = None,
    min_ante_kg_h: float | None = None,
    sort_by: str = "rmsd",
) -> List[RgpoxCombinedTaTuneResult]:
    """middle-way 基线下联合扫描气相 + 异相 TA（η 全 1.0）。"""
    if rgpox_wet_major_reference(case_id) is None:
        raise ValueError(f"工况 {case_id} 无 pox_comp_wet，无法调参")

    feed_df = build_feed_df(case_id)
    specs_df = build_specs_df()
    chem_df = build_chem_df(case_id)
    results: List[RgpoxCombinedTaTuneResult] = []
    for dt_wgs in dt_wgs_values:
        for dt_meth in dt_meth_values:
            for dt_ox_co in dt_ox_co_values:
                for dt_ox_h2 in dt_ox_h2_values:
                    for dt_ox_ch4 in dt_ox_ch4_values:
                        for dt_boud in dt_boudouard_values:
                            for dt_steam in dt_char_steam_values:
                                for alpha in char_boud_fraction_values:
                                    overrides = dict(char_overrides or {})
                                    if alpha is not None:
                                        overrides["char_boud_fraction"] = float(alpha)
                                    row = evaluate_rgpox_combined_ta(
                                        case_id,
                                        dt_wgs_c=float(dt_wgs),
                                        dt_meth_c=float(dt_meth),
                                        dt_ox_co_c=float(dt_ox_co),
                                        dt_ox_h2_c=float(dt_ox_h2),
                                        dt_ox_ch4_c=float(dt_ox_ch4),
                                        dt_boudouard_c=float(dt_boud),
                                        dt_char_steam_c=float(dt_steam),
                                        char_overrides=overrides or None,
                                        feed_df=feed_df,
                                        specs_df=specs_df,
                                        chem_df=chem_df,
                                    )
                                    if min_ante_kg_h is not None and row.pox_gas_ante_kg_h < min_ante_kg_h:
                                        continue
                                    results.append(row)
    h2o_ref = ref_rgpox_h2o(case_id)
    if sort_by == "phase6d":
        results.sort(
            key=lambda r: (
                0 if meets_phase6d_targets(r, min_ante_kg_h=min_ante_kg_h or 7680.0) else 1,
                _major_four_abs_max_pp(r.delta_pp),
                r.rmsd_wet_pct,
                r.co_co2_mae_pp,
                abs(r.h2o_wet_pct - h2o_ref),
            )
        )
    else:
        results.sort(key=lambda r: (r.rmsd_wet_pct, r.co_co2_mae_pp, abs(r.h2o_wet_pct - h2o_ref)))
    return results


# --- RGPOX char 气化 / O₂ 路径（15PGR-1 湿基，聚焦 CO–CO₂ 氧化–还原平衡）---

CHAR_GASIFICATION_GRID_KEYS = (
    "reaction_sequence",
    "o2_to_gibbs_mode",
    "char_co2_replace_fraction",
    "enable_boudouard",
    "enable_steam_gasification",
    "char_steam_fraction",
    "char_boud_fraction",
    "gasification_order",
    "syngas_h2_o2_fraction",
)


@contextmanager
def patched_rgpox_char_gasification(overrides: Mapping[str, Any]) -> Iterator[None]:
    """临时覆盖 RGPOX char_gasification 子配置（扫描用，不写回 JSON）。"""
    base_cfg = dict(RGPOX_CFG)
    char_base = dict(base_cfg.get("char_gasification", {}))
    char_next = {**char_base, **dict(overrides)}
    next_cfg = {**base_cfg, "char_gasification": char_next}
    prev_rgpox = rgpox_mod.RGPOX_CFG
    rgpox_mod.RGPOX_CFG = next_cfg
    try:
        yield
    finally:
        rgpox_mod.RGPOX_CFG = prev_rgpox


@dataclass(frozen=True)
class RgpoxCharTuneResult:
    case_id: str
    rmsd_wet_pct: float
    co_co2_mae_pp: float
    char_co2_replace_fraction: float
    enable_boudouard: bool
    enable_steam_gasification: bool
    char_steam_fraction: float
    o2_to_gibbs_mode: str
    reaction_sequence: str
    gasification_order: str
    syngas_h2_o2_fraction: float
    o2_to_gibbs_char_mol_ratio: float | None
    post_char_use_remaining_o2: bool
    comp_wet_vol_pct: Dict[str, float]
    delta_pp: Dict[str, float]
    pox_ash_kg_h: float
    pox_gas_ante_kg_h: float

    @property
    def h2o_wet_pct(self) -> float:
        return float(self.comp_wet_vol_pct.get("H2O", 0.0))


def _wet_delta_pp(model: Mapping[str, float], ref: Mapping[str, float]) -> Dict[str, float]:
    return {k: float(model.get(k, 0.0)) - float(ref.get(k, 0.0)) for k in INCI_WET_MAJOR_KEYS}


def _co_co2_mae_pp(delta_pp: Mapping[str, float]) -> float:
    return abs(float(delta_pp.get("CO", 0.0))) + abs(float(delta_pp.get("CO2", 0.0)))


def evaluate_rgpox_char_gasification(
    case_id: str,
    *,
    char_overrides: Mapping[str, Any],
    dt_wgs_c: float | None = None,
    dt_meth_c: float | None = None,
    feed_df: Optional[pd.DataFrame] = None,
    specs_df: Optional[pd.DataFrame] = None,
    chem_df: Optional[pd.DataFrame] = None,
) -> RgpoxCharTuneResult:
    ref = rgpox_wet_major_reference(case_id)
    if ref is None:
        raise ValueError(f"工况 {case_id} 无 pox_comp_wet_ante / pox_comp_wet 参考")

    mp = model_parameters()["chemistry_setup"]
    feed_df = feed_df if feed_df is not None else build_feed_df(case_id)
    specs_df = specs_df if specs_df is not None else build_specs_df()
    base_chem = chem_df if chem_df is not None else build_chem_df(case_id)
    chem = set_rgpox_ta_on_chem_df(
        base_chem,
        dt_wgs_c=float(dt_wgs_c if dt_wgs_c is not None else mp["RGPOX TA DeltaT WGS (C)"]),
        dt_meth_c=float(dt_meth_c if dt_meth_c is not None else mp["RGPOX TA DeltaT Meth (C)"]),
        eta_wgs=float(mp["RGPOX WGS Equilibrium Approach Eta"]),
        eta_meth=float(mp["RGPOX Meth Equilibrium Approach Eta"]),
        dt_ox_co_c=float(mp.get("RGPOX TA DeltaT OxCO (C)", 0.0)),
        dt_ox_h2_c=float(mp.get("RGPOX TA DeltaT OxH2 (C)", 0.0)),
        dt_ox_ch4_c=float(mp.get("RGPOX TA DeltaT OxCH4 (C)", 0.0)),
    )

    char_cfg = dict(RGPOX_CFG.get("char_gasification", {}))
    merged = {**char_cfg, **dict(char_overrides)}
    with patched_rgpox_char_gasification(merged):
        res = run_fixed_temperature_simulation(feed_df, specs_df, chem)
    if res.rgpox_inlet_audit and not res.rgpox_inlet_audit.ready_for_ta_tuning:
        raise RuntimeError(f"RGPOX 进料门禁未通过: {res.rgpox_inlet_audit.blockers}")

    model = res.pox_comp_wet_ante_vol_pct
    keys = [k for k in INCI_WET_MAJOR_KEYS if k in ref]
    rmsd = _calc_rmsd_pct(model, ref, keys)
    delta = _wet_delta_pp(model, ref)
    return RgpoxCharTuneResult(
        case_id=case_id,
        rmsd_wet_pct=rmsd,
        co_co2_mae_pp=_co_co2_mae_pp(delta),
        char_co2_replace_fraction=float(merged.get("char_co2_replace_fraction", 0.0)),
        enable_boudouard=bool(merged.get("enable_boudouard", True)),
        enable_steam_gasification=bool(merged.get("enable_steam_gasification", True)),
        char_steam_fraction=float(merged.get("char_steam_fraction", 1.0)),
        o2_to_gibbs_mode=str(merged.get("o2_to_gibbs_mode", "char_stoich_co")),
        reaction_sequence=str(merged.get("reaction_sequence", "gas_equilibrium_first")),
        gasification_order=str(merged.get("gasification_order", "boudouard_first")),
        syngas_h2_o2_fraction=float(merged.get("syngas_h2_o2_fraction", 0.0)),
        o2_to_gibbs_char_mol_ratio=(
            float(merged["o2_to_gibbs_char_mol_ratio"])
            if "o2_to_gibbs_char_mol_ratio" in merged
            else o2_to_gibbs_char_mol_ratio_from_cfg(merged)
        ),
        post_char_use_remaining_o2=bool(merged.get("post_char_use_remaining_o2", False)),
        comp_wet_vol_pct=dict(model),
        delta_pp=delta,
        pox_ash_kg_h=float(res.pox_ash_kg_h),
        pox_gas_ante_kg_h=float(res.pox_gas_ante_kg_h),
    )


def grid_search_rgpox_char_gasification(
    case_id: str = "Case-1",
    *,
    char_co2_replace_values: Sequence[float] = (0.375, 0.25, 0.15, 0.0),
    enable_boudouard_values: Sequence[bool] = (True, False),
    enable_steam_values: Sequence[bool] = (True,),
    char_steam_fraction_values: Sequence[float] = (1.0, 0.5),
    o2_to_gibbs_mode_values: Sequence[str] = ("char_stoich_co",),
    reaction_sequence_values: Sequence[str] = ("gas_equilibrium_first",),
    gasification_order_values: Sequence[str] = ("boudouard_first",),
    syngas_h2_o2_fraction_values: Sequence[float] = (0.11,),
    sort_by: str = "co_co2",
) -> List[RgpoxCharTuneResult]:
    """扫描 char 异相 / O₂ 路径；sort_by='co_co2' 优先 CO–CO₂ 偏差，'rmsd' 为全湿基 RMSD。"""
    if rgpox_wet_major_reference(case_id) is None:
        raise ValueError(f"工况 {case_id} 无 pox_comp_wet，无法调参")

    feed_df = build_feed_df(case_id)
    specs_df = build_specs_df()
    chem_df = build_chem_df(case_id)
    results: List[RgpoxCharTuneResult] = []
    for replace_frac in char_co2_replace_values:
        for boud in enable_boudouard_values:
            for steam_on in enable_steam_values:
                for steam_frac in char_steam_fraction_values:
                    if not steam_on and steam_frac != char_steam_fraction_values[0]:
                        continue
                    for o2_mode in o2_to_gibbs_mode_values:
                        for seq in reaction_sequence_values:
                            for order in gasification_order_values:
                                for h2_o2_frac in syngas_h2_o2_fraction_values:
                                    overrides: Dict[str, Any] = {
                                        "char_co2_replace_fraction": float(replace_frac),
                                        "enable_boudouard": bool(boud),
                                        "enable_steam_gasification": bool(steam_on),
                                        "char_steam_fraction": float(steam_frac),
                                        "o2_to_gibbs_mode": str(o2_mode),
                                        "reaction_sequence": str(seq),
                                        "gasification_order": str(order),
                                        "syngas_h2_o2_fraction": float(h2_o2_frac),
                                    }
                                    if not steam_on:
                                        overrides["char_steam_fraction"] = 0.0
                                    results.append(
                                        evaluate_rgpox_char_gasification(
                                            case_id,
                                            char_overrides=overrides,
                                            feed_df=feed_df,
                                            specs_df=specs_df,
                                            chem_df=chem_df,
                                        )
                                    )
    h2o_ref = ref_rgpox_h2o(case_id)
    if sort_by == "rmsd":
        results.sort(key=lambda r: (r.rmsd_wet_pct, r.co_co2_mae_pp, abs(r.h2o_wet_pct - h2o_ref)))
    else:
        results.sort(key=lambda r: (r.co_co2_mae_pp, r.rmsd_wet_pct, abs(r.h2o_wet_pct - h2o_ref)))
    return results
