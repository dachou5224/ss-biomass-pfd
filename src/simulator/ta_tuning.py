"""INCI WGS / 甲烷化 TA 湿基组成调参（对标 DBI 13PGI-1 湿基主组分 + H2O）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from .backend import _calc_rmsd_pct, run_fixed_temperature_simulation
from .data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from .parameters import INCI_WET_MAJOR_KEYS

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
