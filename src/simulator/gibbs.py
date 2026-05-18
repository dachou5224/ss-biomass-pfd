from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

import numpy as np
from scipy.optimize import minimize

from .species import ATOM_COUNT

R_CONST = 8.314462618


# Shomate coefficients [A, B, C, D, E, F, G, H]
SHOMATE_DB = {
    "CO": {"T_cut": 1300.0, "Low": [25.56759, 6.096130, 4.054656, -2.671301, 0.131021, -118.0089, 227.3665, -110.5271], "High": [35.15070, 1.300095, -0.205921, 0.013550, -3.282780, -127.8375, 231.7120, -110.5271]},
    "CO2": {"T_cut": 1200.0, "Low": [24.99735, 55.18696, -33.69137, 7.948387, -0.136638, -403.6075, 228.2431, -393.5224], "High": [58.16639, 2.720074, -0.492289, 0.038844, -6.447293, -425.9186, 263.6125, -393.5224]},
    "H2": {"T_cut": 1000.0, "Low": [33.066178, -11.363417, 11.432816, -2.772874, -0.158558, -9.980797, 172.707974, 0.0], "High": [18.563083, 12.257357, -2.859786, 0.268238, 1.977990, -1.147438, 156.288133, 0.0]},
    "H2O": {"T_cut": 1000.0, "Low": [30.09200, 6.832514, 6.793435, -2.534480, 0.082139, -250.8810, 223.3967, -241.8264], "High": [41.96426, 8.622053, -1.499780, 0.098119, -11.15764, -272.1797, 219.7809, -241.8264]},
    "CH4": {"T_cut": 1300.0, "Low": [-0.703029, 108.4773, -42.52157, 5.862788, 0.678565, -76.84376, 158.7163, -74.87310], "High": [85.81217, 11.26467, -2.114146, 0.138190, -26.42221, -153.5327, 224.4143, -74.87310]},
    "N2": {"T_cut": 1000.0, "Low": [28.98641, 1.853978, -9.647459, 16.63537, 0.000117, -8.671914, 212.0238, 0.0], "High": [19.50583, 19.88705, -8.598535, 1.369784, 0.527601, -4.935202, 212.3900, 0.0]},
    "O2": {"T_cut": 1000.0, "Low": [31.32234, -20.23531, 57.86644, -36.50624, -0.007374, -8.903471, 246.7945, 0.0], "High": [30.03235, 8.772972, -3.988133, 0.788313, -0.741599, -11.32468, 236.1663, 0.0]},
    "Ar": {"T_cut": 10000.0, "Low": [20.78600, 0.0, 0.0, 0.0, 0.0, -6.19735, 179.999, 0.0], "High": [20.78600, 0.0, 0.0, 0.0, 0.0, -6.19735, 179.999, 0.0]},
}


@dataclass
class GibbsSolveResult:
    species_flow_mol_h: Dict[str, float]
    success: bool
    message: str


def _get_coeffs(species: str, T: float) -> Sequence[float]:
    data = SHOMATE_DB[species]
    return data["Low"] if T < data["T_cut"] else data["High"]


def _shomate_h_s(species: str, t_k: float) -> tuple[float, float]:
    a, b, c, d, e, f, g, _ = _get_coeffs(species, t_k)
    x = t_k / 1000.0
    h_kj_mol = a * x + b * x**2 / 2 + c * x**3 / 3 + d * x**4 / 4 - e / x + f
    s_j_mol_k = a * np.log(x) + b * x + c * x**2 / 2 + d * x**3 / 3 - e / (2 * x**2) + g
    return h_kj_mol * 1000.0, s_j_mol_k


def standard_gibbs(species: str, t_k: float) -> float:
    h, s = _shomate_h_s(species, t_k)
    return h - t_k * s


def solve_gibbs_major(
    elemental_mol_h: Dict[str, float],
    species: Iterable[str],
    t_k: float,
    p_bar: float,
) -> GibbsSolveResult:
    species_list: List[str] = list(species)
    elements = ["C", "H", "O", "N", "Ar"]
    a = np.array([[ATOM_COUNT.get(sp, {}).get(el, 0) for sp in species_list] for el in elements], dtype=float)
    b = np.array([elemental_mol_h.get(el, 0.0) for el in elements], dtype=float)

    if b.sum() <= 0.0:
        return GibbsSolveResult({sp: 0.0 for sp in species_list}, True, "No elemental feed.")

    g0 = np.array([standard_gibbs(sp, t_k) for sp in species_list], dtype=float)
    x0 = np.full(len(species_list), max(b.sum() / max(len(species_list), 1), 1.0))

    constraints = [{"type": "eq", "fun": lambda n, row=row, rhs=rhs: float(np.dot(row, n) - rhs)} for row, rhs in zip(a, b)]
    bounds = [(0.0, None) for _ in species_list]

    def objective(n: np.ndarray) -> float:
        n = np.maximum(n, 1e-18)
        nt = np.sum(n)
        y = n / max(nt, 1e-18)
        mu = g0 + R_CONST * t_k * np.log(np.maximum(y * max(p_bar, 1e-6), 1e-18))
        return float(np.sum(n * mu))

    res = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints, options={"maxiter": 600, "ftol": 1e-9})
    if not res.success:
        return GibbsSolveResult({sp: 0.0 for sp in species_list}, False, res.message)

    out = {sp: max(float(v), 0.0) for sp, v in zip(species_list, res.x)}
    return GibbsSolveResult(out, True, res.message)
