from __future__ import annotations

from typing import Dict, Tuple

import numpy as np


TarSurrogate = str

TAR_SURROGATE_FORMULA: Dict[TarSurrogate, Tuple[int, int]] = {
    "C10H8": (10, 8),
    "C16H34": (16, 34),
}

TAR_SURROGATE_HC_RATIO: Dict[TarSurrogate, float] = {
    name: h / c for name, (c, h) in TAR_SURROGATE_FORMULA.items()
}


def calc_tar_surrogate_fractions(target_hc_ratio: float = 1.20) -> Dict[TarSurrogate, float]:
    """Hamel-style two-surrogate linear blend for biomass tar."""
    r_a = TAR_SURROGATE_HC_RATIO["C10H8"]
    r_b = TAR_SURROGATE_HC_RATIO["C16H34"]
    if np.isclose(r_a, r_b):
        raise ValueError("Tar surrogate H/C ratios are degenerate.")
    x_a = (target_hc_ratio - r_b) / (r_a - r_b)
    x_a = float(np.clip(x_a, 0.0, 1.0))
    return {"C10H8": x_a, "C16H34": 1.0 - x_a}


def allocate_tar_moles_from_carbon(
    carbon_mol_h: float,
    target_hc_ratio: float = 1.20,
) -> Dict[str, float]:
    fractions = calc_tar_surrogate_fractions(target_hc_ratio=target_hc_ratio)
    c_avg = (
        fractions["C10H8"] * TAR_SURROGATE_FORMULA["C10H8"][0]
        + fractions["C16H34"] * TAR_SURROGATE_FORMULA["C16H34"][0]
    )
    n_tar_total = max(carbon_mol_h, 0.0) / max(c_avg, 1e-12)
    return {"TAR1_C10H8": n_tar_total * fractions["C10H8"], "TAR2_C16H34": n_tar_total * fractions["C16H34"]}

