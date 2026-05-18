from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


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
        denom = max(abs(self.inlet_mol_h), 1e-12)
        return abs(self.outlet_mol_h - self.inlet_mol_h) / denom * 100.0


@dataclass
class SimulationResult:
    inci_top_kg_h: float
    inci_slag_kg_h: float
    pox_gas_kg_h: float
    pox_ash_kg_h: float
    inci_comp_dry_vol_pct: Dict[str, float]
    pox_comp_dry_vol_pct: Dict[str, float]
    inci_minor_vol_pct: Dict[str, float]
    pox_minor_vol_pct: Dict[str, float]
    rmsd_inci_pct: float | None
    rmsd_pox_pct: float | None
    unit_trace: List[UnitResult]
    thermo_trace: List[Dict[str, str]]
    element_balance: List[ElementBalance]
    matched_case: str | None
