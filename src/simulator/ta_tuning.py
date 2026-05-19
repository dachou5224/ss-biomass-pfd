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
