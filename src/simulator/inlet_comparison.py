"""INCI 边界进料：DBI stream table vs 模型 feeds 组分对比。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .data import REFERENCE_CASES, build_chem_df
from .elemental import BIOMASS_SAMPLES, biomass_to_elemental_moles
from .feed_streams import inci_o2_stream_species_kg_h
from .parameters import (
    COMPARE_SPECIES,
    INCI_INLET_STREAMS,
    INLET_COMPARE_MIN_KG_H,
    dbi_case1_inlet,
)

# DBI PDF Case-I p2 边界 stream（config/dbi_inlet.json）
DBI_CASE1_INLET = dbi_case1_inlet()


@dataclass(frozen=True)
class InletCompareRow:
    stream_id: str
    component: str
    dbi_kg_h: float
    model_kg_h: float

    @property
    def delta_kg_h(self) -> float:
        return self.model_kg_h - self.dbi_kg_h


def _og_stream_species_mass(total_kg_h: float, mol_pct: Dict[str, float]) -> Dict[str, float]:
    mws = {"O2": 31.998, "N2": 28.014, "Ar": 39.948}
    avg_mw = sum(mol_pct[k] / 100.0 * mws[k] for k in mol_pct)
    n_mol_h = total_kg_h / avg_mw * 1000.0
    return {k: n_mol_h * mol_pct[k] / 100.0 * mws[k] / 1000.0 for k in mol_pct}


def _dbi_stream_components(case_id: str = "Case-1") -> Dict[str, Dict[str, float]]:
    if case_id != "Case-1":
        return {}
    d = DBI_CASE1_INLET
    b = d["13C-4"]
    prox = b["proximate_dry"]
    solid = b["solid_kg_h"]
    moisture = solid * b["moisture_wet_pct"] / 100.0
    dry = solid - moisture
    c4 = {
        "total": b["total_kg_h"],
        "H2O": moisture,
        "Ash": dry * prox["ash_pct"] / 100.0,
        "C": dry * prox["C_pct"] / 100.0,
        "H": dry * prox["H_pct"] / 100.0,
        "N": dry * prox["N_pct"] / 100.0,
        "S": dry * prox["S_pct"] / 100.0,
        "O_biomass": dry * prox["O_pct"] / 100.0,
        "CO2": b["co2_gas_kg_h"],
    }
    hs = {"total": d["13HS1-1"]["total_kg_h"], "H2O": d["13HS1-1"]["h2o_kg_h"]}
    og = {"total": d["13OG2-1"]["total_kg_h"], **_og_stream_species_mass(d["13OG2-1"]["total_kg_h"], d["13OG2-1"]["mol_pct"])}
    return {"13C-4": c4, "13HS1-1": hs, "13OG2-1": og}


def _model_stream_components(case_id: str) -> Dict[str, Dict[str, float]]:
    feed_keys = ("Biomass", "CIN", "O2IN", "H2OIN", "N2IN", "CO2IN")
    feeds = {k: REFERENCE_CASES[case_id]["feeds"][k][0] for k in feed_keys}
    sample = REFERENCE_CASES[case_id]["sample"]
    chem = {r.Field: r.Value for _, r in build_chem_df(case_id).iterrows()}
    s = BIOMASS_SAMPLES[sample]
    bio = biomass_to_elemental_moles(sample, feeds["Biomass"])
    moisture = feeds["Biomass"] * s.mad_pct / 100.0
    dry = feeds["Biomass"] - moisture
    co2 = feeds["CIN"] + feeds["CO2IN"]
    c4 = {
        "total": feeds["Biomass"] + co2,
        "H2O": moisture,
        "Ash": bio["Ash_kg_h"],
        "C": dry * s.cd_pct_dry / 100.0,
        "H": dry * s.hd_pct_dry / 100.0,
        "N": dry * s.nd_pct_dry / 100.0,
        "S": dry * s.sd_pct_dry / 100.0,
        "O_biomass": dry * s.od_pct_dry / 100.0,
        "CO2": co2,
    }
    hs = {"total": feeds["H2OIN"], "H2O": feeds["H2OIN"]}
    og_parts = inci_o2_stream_species_kg_h(feeds["O2IN"], chem)
    og = {"total": feeds["O2IN"], **og_parts}
    return {"13C-4": c4, "13HS1-1": hs, "13OG2-1": og}


def build_inci_inlet_comparison(case_id: str = "Case-1") -> Optional[List[InletCompareRow]]:
    """按 PFD stream × 组分生成 DBI vs 模型进料对比行。"""
    if case_id not in REFERENCE_CASES:
        return None
    dbi = _dbi_stream_components(case_id)
    model = _model_stream_components(case_id)
    if not dbi:
        return None
    rows: List[InletCompareRow] = []
    for stream_id in INCI_INLET_STREAMS:
        d = dbi[stream_id]
        m = model[stream_id]
        keys = sorted(set(d) | set(m))
        for key in keys:
            if key == "total":
                continue
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


def aggregate_inlet_comparison(rows: List[InletCompareRow]) -> List[InletCompareRow]:
    """跨 stream 按组分加总（不含 TOTAL 行）。"""
    agg: Dict[str, float] = {}
    for row in rows:
        if row.component == "TOTAL":
            continue
        agg[row.component] = agg.get(row.component, 0.0) + row.dbi_kg_h
    agg_model: Dict[str, float] = {}
    for row in rows:
        if row.component == "TOTAL":
            continue
        agg_model[row.component] = agg_model.get(row.component, 0.0) + row.model_kg_h
    out: List[InletCompareRow] = []
    for comp in COMPARE_SPECIES:
        if comp in agg or comp in agg_model:
            out.append(
                InletCompareRow(
                    "Σ边界",
                    comp,
                    agg.get(comp, 0.0),
                    agg_model.get(comp, 0.0),
                )
            )
    dbi_tot = sum(r.dbi_kg_h for r in rows if r.component == "TOTAL")
    mod_tot = sum(r.model_kg_h for r in rows if r.component == "TOTAL")
    out.append(InletCompareRow("Σ边界", "TOTAL", dbi_tot, mod_tot))
    return out
