"""INCI / 全厂元素与 H2O 物料衡算审计。"""

from __future__ import annotations

from typing import Dict, List, Optional

from .contracts import H2OBudgetRow, InciMassAudit, MassStreamRow, StageElementBalance
from .reference_streams import load_dbi_inci_mass_balance
from .parameters import AUDIT_CFG, NUMERICAL_CFG
from .species import ATOMIC_WEIGHT, elemental_totals_from_species, species_flow_mass_kg_h
from .tar_models import TarAllocation

INCI_AUDIT_ELEMENTS = tuple(AUDIT_CFG["inci_elements"])
_MASS_CLOSURE_FLOOR = float(NUMERICAL_CFG["mass_closure_denom_floor"])


def inlet_element_mass_kg_h(inlet_elem: Dict[str, float], ash_kg_h: float) -> float:
    """进料元素质量 + 生物质灰分（灰分不参与 C/H/O 元素矩阵）。"""
    atoms_kg = sum(inlet_elem.get(el, 0.0) * ATOMIC_WEIGHT[el] / 1000.0 for el in ATOMIC_WEIGHT)
    return atoms_kg + max(ash_kg_h, 0.0)


def build_inci_stream_ledger(
    *,
    feed_map: Dict[str, float],
    gas_mass_kg_h: float,
    tar_mass_kg_h: float,
    ash_kg_h: float,
    char_after_inci_kg_h: float,
    ash_to_slag_kg_h: float,
    ash_to_pox_kg_h: float,
    char_to_slag_kg_h: float,
    char_to_pox_kg_h: float,
    slag_to_u14_kg_h: float,
    dbi_mass_balance: Optional[Dict] = None,
) -> List[MassStreamRow]:
    """按 doc/core_topology.svg 列出 INCI 边界主要物流（模型 + DBI 净进料参考）。"""
    pgi_total = gas_mass_kg_h + tar_mass_kg_h
    rows = [
        MassStreamRow(
            "13C-4",
            "in",
            "Biomass + CO2 carrier (13C-4)",
            feed_map.get("Biomass", 0.0) + feed_map.get("CIN", 0.0) + feed_map.get("CO2IN", 0.0),
        ),
        MassStreamRow("13HS1-1", "in", "HP Steam", feed_map.get("H2OIN", 0.0)),
        MassStreamRow("13OG2-1", "in", "Oxygen stream (total)", feed_map.get("O2IN", 0.0)),
        MassStreamRow("N2IN", "in", "Nitrogen", feed_map.get("N2IN", 0.0)),
        MassStreamRow("13PGI-1", "out", "Raw gas fluid phase (model)", gas_mass_kg_h, "气相；对标 DBI gas_flow"),
        MassStreamRow(
            "13PGI-1",
            "out",
            "Organic volatiles / tar (model)",
            tar_mass_kg_h,
            "Tar Yield = 0.01×C_dry；对标 DBI volatiles 18.49",
        ),
        MassStreamRow("13PGI-1", "out", "Multiphase total (model gas+tar)", pgi_total, "未含夹带固相 275 kg"),
        MassStreamRow(
            "13LBS-1",
            "out",
            "Bottom solids to Unit 14 (slag line)",
            slag_to_u14_kg_h,
            f"灰→渣 {ash_to_slag_kg_h:.1f} + 残碳；char→渣 {char_to_slag_kg_h:.1f} 未计入 DBI slag 122",
        ),
        MassStreamRow(
            "SEP2-bottom",
            "out",
            "All solids at INCI outlet (ash + char)",
            ash_kg_h + char_after_inci_kg_h,
            "= 全灰 + 全 char（SEP2 底流合计）",
        ),
        MassStreamRow("→RGPOX", "out", "Char routed to RGPOX", char_to_pox_kg_h),
        MassStreamRow("→RGPOX", "out", "Ash routed to RGPOX", ash_to_pox_kg_h),
    ]
    if dbi_mass_balance:
        rows.append(MassStreamRow("", "", "—— DBI 边界参考 ——", 0.0))
        for ref in dbi_mass_balance.get("net_inlet", []):
            sid = ref["stream_id"]
            mass = ref["mass_kg_h"]
            note = ref.get("note") or ""
            if mass is None and ref.get("model_feed_key"):
                key = ref["model_feed_key"]
                mass = feed_map.get(key, 0.0)
                note = f"{note}；模型 {key}={mass:.1f} kg/h".strip("；")
            rows.append(
                MassStreamRow(
                    f"DBI|{sid}",
                    "in",
                    ref["description"],
                    mass or 0.0,
                    f"net_inlet | {note}",
                )
            )
        rows.append(MassStreamRow("", "", "—— DBI 出口分相 ——", 0.0))
        for ref in dbi_mass_balance.get("outlets", []):
            if ref["balance_role"] == "outlet_total":
                continue
            rows.append(
                MassStreamRow(
                    f"DBI|{ref['stream_id']}",
                    "out",
                    ref["description"],
                    ref["mass_kg_h"] or 0.0,
                    ref["balance_role"],
                )
            )
    return rows


def build_inci_stage_element_balance(
    inlet_elem: Dict[str, float],
    gas_flow_mol_h: Dict[str, float],
    char_carbon_mol_h: float,
    tar_allocation: Optional[TarAllocation] = None,
    solid_s_mol_h: float = 0.0,
) -> List[StageElementBalance]:
    gas_elem = elemental_totals_from_species(gas_flow_mol_h, INCI_AUDIT_ELEMENTS)
    if tar_allocation is not None:
        gas_elem["C"] = gas_elem.get("C", 0.0) + tar_allocation.carbon_mol_h
        gas_elem["H"] = gas_elem.get("H", 0.0) + tar_allocation.hydrogen_mol_h
    solid_elem = {"C": max(char_carbon_mol_h, 0.0), "S": max(solid_s_mol_h, 0.0)}
    rows: List[StageElementBalance] = []
    for el in INCI_AUDIT_ELEMENTS:
        rows.append(
            StageElementBalance(
                stage="INCI",
                element=el,
                inlet_mol_h=inlet_elem.get(el, 0.0),
                outlet_gas_mol_h=gas_elem.get(el, 0.0),
                outlet_solid_mol_h=solid_elem.get(el, 0.0),
            )
        )
    return rows


def build_inci_h2o_budget(
    *,
    feed_h2o_mol_h: float,
    pyro_h2o_mol_h: float,
    h2o_after_gibbs_mol_h: float,
    h2o_after_ta_mol_h: float,
    h2o_final_mol_h: float,
    dry_gas_mol_h: float,
    dbi_h2o_wet_pct: Optional[float] = None,
) -> List[H2OBudgetRow]:
    rows = [
        H2OBudgetRow("进料 H2O (H2OIN + 生物质水分)", feed_h2o_mol_h),
        H2OBudgetRow("热解挥发 H2O", pyro_h2o_mol_h),
        H2OBudgetRow("Gibbs 平衡后 H2O", h2o_after_gibbs_mol_h, "受限平衡输入态"),
        H2OBudgetRow(
            "TA (WGS/甲烷化) 后 H2O",
            h2o_after_ta_mol_h,
            f"Δ = {h2o_after_ta_mol_h - h2o_after_gibbs_mol_h:+.0f} mol/h",
        ),
        H2OBudgetRow("INCI 出口气相 H2O", h2o_final_mol_h),
    ]
    if dbi_h2o_wet_pct is not None and dry_gas_mol_h > 0.0:
        target = dbi_h2o_wet_pct / (100.0 - dbi_h2o_wet_pct) * dry_gas_mol_h
        rows.append(
            H2OBudgetRow(
                f"DBI 对标所需 H2O (@{dbi_h2o_wet_pct:.2f}% wet)",
                target,
                f"缺口 = {target - h2o_final_mol_h:+.0f} mol/h（干气摩尔不变假设）",
            )
        )
    return rows


def build_inci_mass_audit(
    *,
    feed_map: Dict[str, float],
    inlet_elem: Dict[str, float],
    gas_flow_mol_h: Dict[str, float],
    char_carbon_mol_h: float,
    ash_kg_h: float,
    ash_to_slag_kg_h: float,
    ash_to_pox_kg_h: float,
    char_to_slag_kg_h: float,
    char_to_pox_kg_h: float,
    slag_to_u14_kg_h: float,
    feed_h2o_mol_h: float,
    pyro_h2o_mol_h: float,
    h2o_after_gibbs_mol_h: float,
    h2o_after_ta_mol_h: float,
    wet_species_keys: tuple[str, ...],
    tar_mass_kg_h: float = 0.0,
    tar_allocation: Optional[TarAllocation] = None,
    biomass_s_mol_h: float = 0.0,
    s_release_frac: float = 1.0,
    matched_case: Optional[str] = None,
    dbi_gas_mass_kg_h: Optional[float] = None,
    dbi_total_flow_kg_h: Optional[float] = None,
    dbi_slag_mass_kg_h: Optional[float] = None,
    dbi_h2o_wet_pct: Optional[float] = None,
) -> InciMassAudit:
    feed_stream_mass = sum(
        feed_map.get(k, 0.0)
        for k in ("Biomass", "CIN", "O2IN", "H2OIN", "N2IN", "CO2IN")
    )
    feed_element_mass = inlet_element_mass_kg_h(inlet_elem, ash_kg_h)
    gas_mass = species_flow_mass_kg_h(gas_flow_mol_h)
    char_mass = char_carbon_mol_h * ATOMIC_WEIGHT["C"] / 1000.0
    bottom_solids = ash_kg_h + char_mass
    pgi_total = gas_mass + tar_mass_kg_h
    reactor_out_total = pgi_total + bottom_solids
    denom = max(feed_element_mass, _MASS_CLOSURE_FLOOR)
    mass_closure_err = abs(reactor_out_total - feed_element_mass) / denom * 100.0

    dbi_mass_balance = load_dbi_inci_mass_balance(matched_case) if matched_case else None
    dbi_net_inlet = None
    dbi_volatiles = None
    if dbi_mass_balance:
        dbi_net_inlet = dbi_mass_balance.get("net_inlet_sum_kg_h")
        dbi_volatiles = dbi_mass_balance.get("outlet_volatiles_kg_h")

    h2o_final = max(gas_flow_mol_h.get("H2O", 0.0), 0.0)
    total_wet_mol = sum(max(gas_flow_mol_h.get(k, 0.0), 0.0) for k in wet_species_keys)
    dry_gas_mol = max(total_wet_mol - h2o_final, 0.0)
    h2o_wet_pct = 100.0 * h2o_final / total_wet_mol if total_wet_mol > 0.0 else 0.0

    return InciMassAudit(
        feed_stream_mass_kg_h=round(feed_stream_mass, 3),
        feed_element_mass_kg_h=round(feed_element_mass, 3),
        gas_mass_kg_h=round(gas_mass, 3),
        bottom_solids_kg_h=round(bottom_solids, 3),
        slag_to_u14_kg_h=round(slag_to_u14_kg_h, 3),
        char_to_pox_kg_h=round(char_to_pox_kg_h, 3),
        ash_to_pox_kg_h=round(ash_to_pox_kg_h, 3),
        reactor_out_total_kg_h=round(reactor_out_total, 3),
        mass_closure_rel_err_pct=round(mass_closure_err, 4),
        char_mass_kg_h=round(char_mass, 3),
        ash_mass_kg_h=round(ash_kg_h, 3),
        tar_kg_h=round(tar_mass_kg_h, 3),
        pgi_total_kg_h=round(pgi_total, 3),
        element_balance=build_inci_stage_element_balance(
            inlet_elem,
            gas_flow_mol_h,
            char_carbon_mol_h,
            tar_allocation=tar_allocation,
            solid_s_mol_h=max(biomass_s_mol_h, 0.0) * max(0.0, 1.0 - min(max(s_release_frac, 0.0), 1.0))
        ),
        h2o_budget=build_inci_h2o_budget(
            feed_h2o_mol_h=feed_h2o_mol_h,
            pyro_h2o_mol_h=pyro_h2o_mol_h,
            h2o_after_gibbs_mol_h=h2o_after_gibbs_mol_h,
            h2o_after_ta_mol_h=h2o_after_ta_mol_h,
            h2o_final_mol_h=h2o_final,
            dry_gas_mol_h=dry_gas_mol,
            dbi_h2o_wet_pct=dbi_h2o_wet_pct,
        ),
        stream_ledger=build_inci_stream_ledger(
            feed_map=feed_map,
            gas_mass_kg_h=gas_mass,
            tar_mass_kg_h=tar_mass_kg_h,
            ash_kg_h=ash_kg_h,
            char_after_inci_kg_h=char_mass,
            ash_to_slag_kg_h=ash_to_slag_kg_h,
            ash_to_pox_kg_h=ash_to_pox_kg_h,
            char_to_slag_kg_h=char_to_slag_kg_h,
            char_to_pox_kg_h=char_to_pox_kg_h,
            slag_to_u14_kg_h=slag_to_u14_kg_h,
            dbi_mass_balance=dbi_mass_balance,
        ),
        dbi_net_inlet_kg_h=dbi_net_inlet,
        dbi_volatiles_kg_h=dbi_volatiles,
        dbi_gas_mass_kg_h=dbi_gas_mass_kg_h,
        dbi_total_flow_kg_h=dbi_total_flow_kg_h,
        dbi_slag_mass_kg_h=dbi_slag_mass_kg_h,
        dbi_h2o_wet_pct=dbi_h2o_wet_pct,
        h2o_wet_pct_model=round(h2o_wet_pct, 3),
    )
