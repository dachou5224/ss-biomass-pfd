from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

import numpy as np
from scipy.optimize import lsq_linear, minimize

from .parameters import EQUILIBRIUM_CFG, GIBBS_ELEMENTS, GIBBS_SOLVER_CFG
from .species import ATOM_COUNT
from .thermo_baseline import R_CONST, get_gibbs_free_energy


@dataclass
class GibbsSolveResult:
    species_flow_mol_h: Dict[str, float]
    success: bool
    message: str


_G = GIBBS_SOLVER_CFG
_FLOW_FLOOR = float(_G["flow_floor"])
_MOL_FRAC_FLOOR = float(_G["mole_fraction_floor"])
_PRESSURE_RATIO_BAR = float(EQUILIBRIUM_CFG["pressure_ratio_bar"])


def _constraint_residual(a: np.ndarray, b: np.ndarray, n: np.ndarray) -> float:
    return float(np.linalg.norm(a @ n - b, ord=2))


def _build_multistart_guesses(x0: np.ndarray) -> List[np.ndarray]:
    guesses = [np.maximum(x0, _FLOW_FLOOR)]
    if x0.size >= 8:
        i_co, i_h2, i_co2, i_ch4 = 0, 1, 2, 3
        g2 = x0.copy()
        shift = float(_G["multistart_ch4_shift_frac"]) * g2[i_ch4]
        g2[i_ch4] = max(g2[i_ch4] - shift, _FLOW_FLOOR)
        g2[i_co2] += float(_G["multistart_ch4_to_co2_frac"]) * shift
        g2[i_h2] += float(_G["multistart_ch4_to_h2_frac"]) * shift
        guesses.append(np.maximum(g2, _FLOW_FLOOR))

        g3 = x0.copy()
        shift2 = float(_G["multistart_co_shift_frac"]) * g3[i_co]
        g3[i_co] = max(g3[i_co] - shift2, _FLOW_FLOOR)
        g3[i_co2] += shift2
        guesses.append(np.maximum(g3, _FLOW_FLOOR))
    return guesses


def standard_gibbs(species: str, t_k: float) -> float:
    return get_gibbs_free_energy(species, t_k)


def solve_gibbs_major(
    elemental_mol_h: Dict[str, float],
    species: Iterable[str],
    t_k: float,
    p_bar: float,
) -> GibbsSolveResult:
    species_list: List[str] = list(species)
    elements = list(GIBBS_ELEMENTS)
    a = np.array([[ATOM_COUNT.get(sp, {}).get(el, 0) for sp in species_list] for el in elements], dtype=float)
    b = np.array([elemental_mol_h.get(el, 0.0) for el in elements], dtype=float)

    if b.sum() <= 0.0:
        return GibbsSolveResult({sp: 0.0 for sp in species_list}, True, "No elemental feed.")

    g0 = np.array([standard_gibbs(sp, t_k) for sp in species_list], dtype=float)
    lsq = lsq_linear(a, b, bounds=(0.0, np.inf), lsmr_tol="auto", verbose=0)
    x0 = np.maximum(lsq.x, _FLOW_FLOOR)

    constraints = [{"type": "eq", "fun": lambda n, row=row, rhs=rhs: float(np.dot(row, n) - rhs)} for row, rhs in zip(a, b)]
    bounds = [(0.0, None) for _ in species_list]

    def objective(n: np.ndarray) -> float:
        n = np.maximum(n, _MOL_FRAC_FLOOR)
        n_total = np.sum(n)
        y = n / max(n_total, _MOL_FRAC_FLOOR)
        pressure_ratio = max(p_bar, 1e-9) / _PRESSURE_RATIO_BAR
        mu = g0 + R_CONST * t_k * np.log(np.maximum(y * pressure_ratio, _MOL_FRAC_FLOOR))
        return float(np.sum(n * mu))

    best = None
    best_f = np.inf
    best_msg = ""
    for guess in _build_multistart_guesses(x0):
        res = minimize(
            objective,
            guess,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": int(_G["slsqp_maxiter"]), "ftol": float(_G["slsqp_ftol"])},
        )
        if not res.success:
            continue
        n = np.maximum(res.x, 0.0)
        residual = _constraint_residual(a, b, n)
        if residual > float(_G["balance_residual_tol"]):
            continue
        f = objective(n)
        if f < best_f:
            best_f = f
            best = n
            best_msg = res.message

    if best is not None:
        out = {sp: max(float(v), 0.0) for sp, v in zip(species_list, best)}
        return GibbsSolveResult(out, True, best_msg)

    residual = _constraint_residual(a, b, x0)
    if residual < float(_G["lsq_fallback_residual_tol"]):
        out_lsq = {sp: max(float(v), 0.0) for sp, v in zip(species_list, x0)}
        return GibbsSolveResult(out_lsq, False, "SLSQP multistart failed; fallback=lsq_linear")
    return GibbsSolveResult({sp: 0.0 for sp in species_list}, False, "SLSQP multistart failed")
