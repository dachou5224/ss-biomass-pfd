from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .parameters import ATOMIC_WEIGHT, load_json_config


@dataclass(frozen=True)
class BiomassSample:
    sample_id: str
    mad_pct: float
    ad_pct: float
    cd_pct_dry: float
    hd_pct_dry: float
    nd_pct_dry: float
    sd_pct_dry: float
    od_pct_dry: float


def _build_biomass_samples() -> Dict[str, BiomassSample]:
    raw = load_json_config("biomass_samples")
    return {
        sid: BiomassSample(sample_id=sid, **row)
        for sid, row in raw.items()
        if not sid.startswith("_")
    }


BIOMASS_SAMPLES: Dict[str, BiomassSample] = _build_biomass_samples()


def _kgph_to_molph(mass_kg_h: float, mw_g_mol: float) -> float:
    return max(mass_kg_h, 0.0) * 1000.0 / mw_g_mol


def biomass_to_elemental_moles(sample_id: str, biomass_kg_h: float) -> Dict[str, float]:
    sample = BIOMASS_SAMPLES[sample_id]
    dry_mass = biomass_kg_h * (1.0 - sample.mad_pct / 100.0)
    carbon_kg_h = dry_mass * sample.cd_pct_dry / 100.0
    hydrogen_kg_h = dry_mass * sample.hd_pct_dry / 100.0
    oxygen_kg_h = dry_mass * sample.od_pct_dry / 100.0
    nitrogen_kg_h = dry_mass * sample.nd_pct_dry / 100.0
    sulfur_kg_h = dry_mass * sample.sd_pct_dry / 100.0
    ash_kg_h = dry_mass * sample.ad_pct / 100.0

    return {
        "C": _kgph_to_molph(carbon_kg_h, ATOMIC_WEIGHT["C"]),
        "H": _kgph_to_molph(hydrogen_kg_h, ATOMIC_WEIGHT["H"]),
        "O": _kgph_to_molph(oxygen_kg_h, ATOMIC_WEIGHT["O"]),
        "N": _kgph_to_molph(nitrogen_kg_h, ATOMIC_WEIGHT["N"]),
        "S": _kgph_to_molph(sulfur_kg_h, ATOMIC_WEIGHT["S"]),
        "Ar": 0.0,
        "Ash_kg_h": ash_kg_h,
    }
