from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .parameters import NUMERICAL_CFG

_ELEMENT_BALANCE_FLOOR = float(NUMERICAL_CFG["element_balance_denom_floor"])


@dataclass
class Stream:
    name: str
    mass_flow_kg_h: float
    temperature_c: float
    pressure_bar: float
    composition: Dict[str, float] = field(default_factory=dict)


@dataclass
class UnitResult:
    unit_name: str
    status: str
    notes: str
    inlet_total_kg_h: float
    outlet_total_kg_h: float


@dataclass
class ElementBalance:
    element: str
    inlet_mol_h: float
    outlet_mol_h: float

    @property
    def rel_error_pct(self) -> float:
        denom = max(abs(self.inlet_mol_h), _ELEMENT_BALANCE_FLOOR)
        return abs(self.outlet_mol_h - self.inlet_mol_h) / denom * 100.0


@dataclass
class MassStreamRow:
    """INCI 边界物流台账（对标 PFD stream ID）。"""

    stream_id: str
    direction: str
    description: str
    mass_kg_h: float
    note: str = ""


@dataclass
class InciMassAudit:
    feed_stream_mass_kg_h: float
    feed_element_mass_kg_h: float
    biomass_carbon_in_kg_h: float
    gas_mass_kg_h: float
    bottom_solids_kg_h: float
    slag_to_u14_kg_h: float
    char_to_pox_kg_h: float
    ash_to_pox_kg_h: float
    reactor_out_total_kg_h: float
    mass_closure_rel_err_pct: float
    char_mass_kg_h: float
    ash_mass_kg_h: float
    element_balance: List["StageElementBalance"]
    h2o_budget: List["H2OBudgetRow"]
    stream_ledger: List[MassStreamRow]
    tar_kg_h: float = 0.0
    pgi_total_kg_h: float = 0.0
    dbi_net_inlet_kg_h: float | None = None
    dbi_volatiles_kg_h: float | None = None
    dbi_gas_mass_kg_h: float | None = None
    dbi_total_flow_kg_h: float | None = None
    dbi_slag_mass_kg_h: float | None = None
    dbi_h2o_wet_pct: float | None = None
    h2o_wet_pct_model: float = 0.0
    overall_biomass_carbon_conversion_pct: float | None = None
    solid_routing_mode: str | None = None
    fly_ash_total_kg_h: float | None = None
    fly_ash_to_slag_ratio: float | None = None
    char_to_slag_kg_h: float = 0.0
    ash_to_slag_kg_h: float = 0.0
    n2_makeup_mol_h: float = 0.0
    n2_makeup_kg_h: float = 0.0

    @property
    def feed_mass_kg_h(self) -> float:
        """兼容旧字段：进料 stream 质量加和。"""
        return self.feed_stream_mass_kg_h


@dataclass
class StageElementBalance:
    stage: str
    element: str
    inlet_mol_h: float
    outlet_gas_mol_h: float
    outlet_solid_mol_h: float

    @property
    def outlet_mol_h(self) -> float:
        return self.outlet_gas_mol_h + self.outlet_solid_mol_h

    @property
    def rel_error_pct(self) -> float:
        denom = max(abs(self.inlet_mol_h), _ELEMENT_BALANCE_FLOOR)
        return abs(self.outlet_mol_h - self.inlet_mol_h) / denom * 100.0


@dataclass
class H2OBudgetRow:
    step: str
    h2o_mol_h: float
    note: str = ""


@dataclass
class SimulationResult:
    inci_top_kg_h: float
    inci_tar_kg_h: float
    inci_pgi_total_kg_h: float
    inci_slag_kg_h: float
    pox_gas_kg_h: float
    pox_gas_ante_kg_h: float
    pox_ash_kg_h: float
    inci_comp_dry_vol_pct: Dict[str, float]
    pox_comp_dry_vol_pct: Dict[str, float]
    inci_comp_wet_vol_pct: Dict[str, float]
    pox_comp_wet_vol_pct: Dict[str, float]
    pox_comp_wet_ante_vol_pct: Dict[str, float]
    quench_t_out_c: float | None
    quench_h2o_added_kg_h: float | None
    inci_comp_dry_full_vol_pct: Dict[str, float]
    pox_comp_dry_full_vol_pct: Dict[str, float]
    inci_comp_wet_full_vol_pct: Dict[str, float]
    pox_comp_wet_full_vol_pct: Dict[str, float]
    inci_minor_vol_pct: Dict[str, float]
    inci_inert_dry_vol_pct: Dict[str, float]
    pox_minor_vol_pct: Dict[str, float]
    rmsd_inci_pct: float | None
    rmsd_pox_pct: float | None
    rmsd_inci_wet_pct: float | None
    rmsd_pox_wet_pct: float | None
    rmsd_pox_wet_ante_pct: float | None
    rmsd_inci_dry_full_pct: float | None
    rmsd_inci_wet_full_pct: float | None
    rmsd_inci_primary_pct: float | None  # 湿基主组分 + H2O；无湿基参考时回退干基四主
    rmsd_pox_primary_pct: float | None  # 湿基主组分；Gibbs 阶段优先 pox_comp_wet_ante (15PGR-1)
    unit_trace: List[UnitResult]
    thermo_trace: List[Dict[str, str]]
    element_balance: List[ElementBalance]
    inci_mass_audit: InciMassAudit | None
    rgpox_inlet_audit: "RgpoxInletAudit | None"
    matched_case: str | None
    inci_n2_makeup_mol_h: float = 0.0
