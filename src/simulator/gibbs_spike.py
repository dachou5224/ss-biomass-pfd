"""Gibbs 迁移 spike：约化维数 (方案 B) 求解，与 scipy SLSQP 金标准对照。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from scipy.optimize import LinearConstraint, differential_evolution, lsq_linear, minimize

from .backend import _chem_map, _feed_map, _spec_map
from .data import build_chem_df, build_feed_df, build_specs_df
from .gibbs import _build_multistart_guesses, solve_gibbs_major
from .inci_conversion import resolve_inci_char_for_overall_biomass_conversion
from .parameters import EQUILIBRIUM_CFG, GIBBS_ELEMENTS, GIBBS_SOLVER_CFG, R_CONST
from .species import ATOM_COUNT, MAJOR_SPECIES
from .thermo_baseline import get_gibbs_free_energy

_G = GIBBS_SOLVER_CFG
_FLOW_FLOOR = float(_G["flow_floor"])
_MOL_FRAC_FLOOR = float(_G["mole_fraction_floor"])
_PRESSURE_RATIO_BAR = float(EQUILIBRIUM_CFG["pressure_ratio_bar"])
_BALANCE_TOL = float(_G["balance_residual_tol"])


def _chem_df_for_gibbs_spike(case_id: str):
    """Gibbs spike 对照应隔离 INCI N2 makeup（仅影响 stream-table 闭合，不改变 Gibbs 进料元素）。"""
    import pandas as pd

    chem_df = build_chem_df(case_id)
    mask = chem_df["Field"] == "INCI N2 Makeup Mode"
    if mask.any():
        chem_df = chem_df.copy()
        chem_df.loc[mask, "Value"] = "off"
    else:
        chem_df = pd.concat(
            [chem_df, pd.DataFrame([{"Field": "INCI N2 Makeup Mode", "Value": "off"}])],
            ignore_index=True,
        )
    return chem_df


@dataclass(frozen=True)
class GibbsSpikeCase:
    case_id: str
    t_k: float
    p_bar: float
    species: Tuple[str, ...]
    elements: Tuple[str, ...]
    a_matrix: np.ndarray
    b_vector: np.ndarray
    n_particular: np.ndarray
    null_basis: np.ndarray
    g0: np.ndarray


@dataclass
class GibbsSpikeResult:
    species_flow_mol_h: Dict[str, float]
    success: bool
    message: str
    objective: float
    balance_residual: float
    z_opt: Tuple[float, float, float]


def case1_inci_elemental_feed_mol_h() -> Tuple[Dict[str, float], str]:
    """复用 backend 私有路径，得到 INCI Gibbs 前元素进料 (mol/h)。"""
    from .backend import _build_inci_elemental_inlet, _inci_o2_species_kg_h, _kg_to_mol_h
    from .data import INCI_C_CONVERSION
    from .elemental import BIOMASS_SAMPLES, biomass_to_elemental_moles, biomass_vm_dry_pct
    from .parameters import DEFAULT_BIOMASS_SAMPLE_FALLBACK, DEFAULT_CHEMISTRY_SETUP
    from .pyrolysis import allocate_pyrolysis_products_elemental
    from .species import elemental_totals_from_species
    from .tar_models import parse_tar_yield_mass_kg_h

    feed_df = build_feed_df("Case-1")
    chem_df = _chem_df_for_gibbs_spike("Case-1")
    feed = _feed_map(feed_df)
    chem = _chem_map(chem_df)

    sample = chem.get("Sample", DEFAULT_BIOMASS_SAMPLE_FALLBACK)
    if sample not in BIOMASS_SAMPLES:
        sample = DEFAULT_BIOMASS_SAMPLE_FALLBACK

    tar_factor_text = chem.get("Tar Yield Factor", DEFAULT_CHEMISTRY_SETUP["Tar Yield Factor"])
    tar_yield_mass_kg_h = parse_tar_yield_mass_kg_h(feed.get("Biomass", 0.0), sample, tar_factor_text)

    inci_inlet_elem, _ash = _build_inci_elemental_inlet(feed, sample, chem)
    co2_in_kg_h = feed.get("CIN", 0.0) + feed.get("CO2IN", 0.0)
    o2_in_parts = _inci_o2_species_kg_h(feed, chem)

    biomass_elem = biomass_to_elemental_moles(sample, feed.get("Biomass", 0.0))
    vm_frac = np.clip(biomass_vm_dry_pct(chem), 0.0, 100.0) / 100.0
    biomass_vm_elem = {
        "C": biomass_elem["C"] * vm_frac,
        "H": biomass_elem["H"],
        "O": biomass_elem["O"],
        "N": biomass_elem["N"],
        "S": biomass_elem["S"],
    }
    biomass_nonvm_elem = {"C": max(biomass_elem["C"] - biomass_vm_elem["C"], 0.0), "H": 0.0, "O": 0.0, "N": 0.0, "S": 0.0}

    pyro_split = allocate_pyrolysis_products_elemental(
        nC=biomass_vm_elem["C"],
        nH=biomass_vm_elem["H"],
        nO=biomass_vm_elem["O"],
        nN=biomass_vm_elem["N"],
        nS=biomass_vm_elem["S"],
        tar_carbon_frac=float(chem.get("Pyrolysis Tar Carbon Frac", "0.0")),
        target_tar_hc_ratio=float(chem.get("Tar target H/C", DEFAULT_CHEMISTRY_SETUP["Tar target H/C"])),
        tar_fuel_type=chem.get("Tar Fuel Type", "biomass").strip().lower(),
        include_tar_internal=chem.get("Tar Internal Path", "off").strip().lower() in ("on", "true", "1", "yes"),
        scheme=chem.get("Pyrolysis Scheme", DEFAULT_CHEMISTRY_SETUP["Pyrolysis Scheme"]).strip().lower(),
        tar_outlet_mass_kg_h=tar_yield_mass_kg_h,
        nh3_frac_of_n=float(chem.get("Biomass N to NH3 Frac", DEFAULT_CHEMISTRY_SETUP["Biomass N to NH3 Frac"])),
        s_release_frac=float(chem.get("Biomass S Release Frac", DEFAULT_CHEMISTRY_SETUP["Biomass S Release Frac"])),
        h2s_split=float(chem.get("H2S/COS split to H2S", DEFAULT_CHEMISTRY_SETUP["H2S/COS split to H2S"])),
    )

    biomass_moisture_kg_h = feed.get("Biomass", 0.0) * BIOMASS_SAMPLES[sample].mad_pct / 100.0
    biomass_moisture_h2o_mol_h = _kg_to_mol_h(biomass_moisture_kg_h, 18.015)
    inci_external = {
        "C": _kg_to_mol_h(co2_in_kg_h, 44.009),
        "H": 2.0 * (_kg_to_mol_h(feed.get("H2OIN", 0.0), 18.015) + biomass_moisture_h2o_mol_h),
        "O": 2.0 * _kg_to_mol_h(o2_in_parts.get("O2", 0.0), 31.998)
        + (_kg_to_mol_h(feed.get("H2OIN", 0.0), 18.015) + biomass_moisture_h2o_mol_h)
        + 2.0 * _kg_to_mol_h(co2_in_kg_h, 44.009),
        "N": max(inci_inlet_elem["N"] - biomass_elem["N"], 0.0),
        "Ar": inci_inlet_elem["Ar"] - biomass_elem["Ar"],
    }
    inci_from_pyro = elemental_totals_from_species(pyro_split.volatile_species_mol_h, list(GIBBS_ELEMENTS))
    char_pool = pyro_split.char_carbon_mol_h + biomass_nonvm_elem["C"]
    reactive_char = resolve_inci_char_for_overall_biomass_conversion(
        biomass_total_c_mol_h=biomass_elem["C"],
        char_pool_c_mol_h=char_pool,
        target_conversion=INCI_C_CONVERSION,
    ).reactive_char_mol_h
    inci_elem = {
        "C": inci_from_pyro["C"] + reactive_char + _kg_to_mol_h(co2_in_kg_h, 44.009),
        "H": inci_from_pyro["H"] + inci_external["H"],
        "O": inci_from_pyro["O"] + inci_external["O"],
        "N": inci_from_pyro["N"] + inci_external["N"],
        "Ar": inci_from_pyro["Ar"] + inci_external["Ar"],
        "S": biomass_vm_elem["S"],
    }
    return inci_elem, sample


def _build_a_b(
    elemental_mol_h: Dict[str, float],
    species: Tuple[str, ...],
    elements: Tuple[str, ...],
) -> Tuple[np.ndarray, np.ndarray]:
    a = np.array(
        [[ATOM_COUNT.get(sp, {}).get(el, 0) for sp in species] for el in elements],
        dtype=float,
    )
    b = np.array([elemental_mol_h.get(el, 0.0) for el in elements], dtype=float)
    return a, b


def build_null_space_basis(a: np.ndarray, tol: float = 1e-10) -> np.ndarray:
    """A @ B = 0，B 为 (n_species, n_null)。"""
    _, s, vh = np.linalg.svd(a)
    rank = int(np.sum(s > tol * max(s[0], 1.0)))
    return vh[rank:].T


def particular_solution(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """最小范数特解。"""
    ata = a @ a.T
    return a.T @ np.linalg.solve(ata, b)


def _pick_particular_solution(
    a: np.ndarray,
    b: np.ndarray,
    g0: np.ndarray,
    t_k: float,
    p_bar: float,
) -> np.ndarray:
    """最小范数特解；高 O 进料且特解 O2 偏高时改用非负最小二乘特解。"""
    n_min = np.maximum(particular_solution(a, b), _FLOW_FLOOR)
    o2_i = MAJOR_SPECIES.index("O2")
    o_el = list(GIBBS_ELEMENTS).index("O")
    o_budget = max(float(b[o_el]), 1.0)
    if n_min[o2_i] <= 0.14 * o_budget:
        return n_min
    lsq = lsq_linear(a, b, bounds=(0.0, np.inf))
    if lsq.success:
        return np.maximum(lsq.x, _FLOW_FLOOR)
    return n_min


def build_spike_case(
    elemental_mol_h: Dict[str, float],
    *,
    t_k: float,
    p_bar: float,
    case_id: str = "Case-1",
) -> GibbsSpikeCase:
    species = tuple(MAJOR_SPECIES)
    elements = tuple(GIBBS_ELEMENTS)
    a, b = _build_a_b(elemental_mol_h, species, elements)
    g0 = np.array([get_gibbs_free_energy(sp, t_k) for sp in species], dtype=float)
    n_p = _pick_particular_solution(a, b, g0, t_k, p_bar)
    b_null = build_null_space_basis(a)
    return GibbsSpikeCase(
        case_id=case_id,
        t_k=t_k,
        p_bar=p_bar,
        species=species,
        elements=elements,
        a_matrix=a,
        b_vector=b,
        n_particular=n_p,
        null_basis=b_null,
        g0=g0,
    )


def _objective_n(n: np.ndarray, g0: np.ndarray, t_k: float, p_bar: float) -> float:
    n = np.maximum(n, _MOL_FRAC_FLOOR)
    n_total = float(np.sum(n))
    y = n / max(n_total, _MOL_FRAC_FLOOR)
    pressure_ratio = max(p_bar, 1e-9) / _PRESSURE_RATIO_BAR
    mu = g0 + R_CONST * t_k * np.log(np.maximum(y * pressure_ratio, _MOL_FRAC_FLOOR))
    return float(np.sum(n * mu))


def _n_from_z(z: np.ndarray, spike: GibbsSpikeCase, *, clip: bool = False) -> np.ndarray:
    n = spike.n_particular + spike.null_basis @ z
    if clip:
        return np.maximum(n, _FLOW_FLOOR)
    return n


def _z_guesses_from_x0(x0: np.ndarray, spike: GibbsSpikeCase) -> List[np.ndarray]:
    b = spike.null_basis
    guesses_n = _build_multistart_guesses(x0)
    z_list: List[np.ndarray] = []
    for n_g in guesses_n:
        dz = n_g - spike.n_particular
        z, _, _, _ = np.linalg.lstsq(b, dz, rcond=None)
        z_list.append(np.asarray(z, dtype=float).ravel())
    z_list.append(np.zeros(b.shape[1]))
    return z_list


def solve_gibbs_spike_reduced(spike: GibbsSpikeCase, x0: np.ndarray) -> GibbsSpikeResult:
    """方案 B：在 ker(A) 的 3 维 z 上最小化 Gibbs；n=n_p+Bz 自动守恒，Bz>=-n_p 保证非负。"""

    def objective(z: np.ndarray) -> float:
        return _objective_n(_n_from_z(z, spike, clip=True), spike.g0, spike.t_k, spike.p_bar)

    n_neg_bound = -spike.n_particular
    lin_nonneg = LinearConstraint(spike.null_basis, n_neg_bound, np.full(spike.null_basis.shape[0], np.inf))

    best_n: np.ndarray | None = None
    best_f = np.inf
    best_z = np.zeros(spike.null_basis.shape[1])
    best_msg = ""

    for z0 in _z_guesses_from_x0(x0, spike):
        res = minimize(
            objective,
            z0,
            method="SLSQP",
            constraints=[lin_nonneg],
            options={"ftol": float(_G["slsqp_ftol"]), "maxiter": 400},
        )
        if not res.success:
            continue
        n = _n_from_z(res.x, spike, clip=False)
        if np.any(n < -1e-9):
            continue
        n_eval = np.maximum(n, _FLOW_FLOOR)
        residual = float(np.linalg.norm(spike.a_matrix @ n - spike.b_vector))
        if residual > _BALANCE_TOL:
            continue
        f = _objective_n(n_eval, spike.g0, spike.t_k, spike.p_bar)
        if f < best_f:
            best_f = f
            best_n = n_eval
            best_z = res.x
            best_msg = res.message

    if spike.null_basis.shape[1] <= 3:
        z_scale = max(float(np.max(np.abs(spike.null_basis))), 1.0)
        z_bound = max(2.0e5, 4.0 * z_scale)
        de_bounds = [(-z_bound, z_bound)] * spike.null_basis.shape[1]
        de = differential_evolution(
            objective,
            de_bounds,
            constraints=[lin_nonneg],
            seed=0,
            maxiter=80,
            polish=True,
        )
        if de.success:
            n_de = _n_from_z(de.x, spike, clip=False)
            if np.all(n_de >= -1e-9):
                n_eval = np.maximum(n_de, _FLOW_FLOOR)
                residual = float(np.linalg.norm(spike.a_matrix @ n_eval - spike.b_vector))
                if residual <= _BALANCE_TOL:
                    f_de = _objective_n(n_eval, spike.g0, spike.t_k, spike.p_bar)
                    if f_de < best_f:
                        best_f = f_de
                        best_n = n_eval
                        best_z = de.x
                        best_msg = "differential_evolution + SLSQP polish"

    if best_n is None:
        n_fb = np.maximum(_n_from_z(np.zeros(spike.null_basis.shape[1]), spike), _FLOW_FLOOR)
        return GibbsSpikeResult(
            {sp: float(n_fb[i]) for i, sp in enumerate(spike.species)},
            False,
            "spike reduced: all multistart failed",
            _objective_n(n_fb, spike.g0, spike.t_k, spike.p_bar),
            float(np.linalg.norm(spike.a_matrix @ n_fb - spike.b_vector)),
            (0.0, 0.0, 0.0),
        )

    return GibbsSpikeResult(
        {sp: float(best_n[i]) for i, sp in enumerate(spike.species)},
        True,
        best_msg,
        best_f,
        float(np.linalg.norm(spike.a_matrix @ best_n - spike.b_vector)),
        tuple(float(v) for v in best_z),
    )


def case1_rgpox_elemental_feed_mol_h() -> Tuple[Dict[str, float], str]:
    """Case-1 全链至 RGPOX Gibbs 前的元素进料 (mol/h)。"""
    import simulator.backend as backend_mod
    import simulator.rgpox as rgpox_mod

    from .backend import run_fixed_temperature_simulation
    from .rgpox import RgpoxInletBundle

    captured: Dict[str, float] = {}
    original = rgpox_mod.solve_rgpox_gibbs_equilibrium

    def _capture(inlet, *args, **kwargs):
        if isinstance(inlet, RgpoxInletBundle):
            captured.update(dict(inlet.elemental_feed_mol_h))
        elif isinstance(inlet, dict):
            captured.update(dict(inlet))
        return original(inlet, *args, **kwargs)

    rgpox_mod.solve_rgpox_gibbs_equilibrium = _capture
    backend_mod.solve_rgpox_gibbs_equilibrium = _capture
    try:
        feed_df = build_feed_df("Case-1")
        chem_df = _chem_df_for_gibbs_spike("Case-1")
        run_fixed_temperature_simulation(feed_df, build_specs_df(), chem_df)
        sample = _chem_map(chem_df).get("Sample", "Case-1")
    finally:
        rgpox_mod.solve_rgpox_gibbs_equilibrium = original
        backend_mod.solve_rgpox_gibbs_equilibrium = original

    if not captured:
        raise RuntimeError("RGPOX Gibbs 元素进料未捕获（solve_rgpox_gibbs_equilibrium 未调用）")
    return captured, str(sample)


def run_case1_rgpox_spike_comparison() -> Dict[str, object]:
    """Case-1 RGPOX Gibbs @1400°C：scipy 金标准 vs 约化维数 spike。"""
    from scipy.optimize import lsq_linear

    from .parameters import RGPOX_T_C

    elem, _sample = case1_rgpox_elemental_feed_mol_h()
    specs = _spec_map(build_specs_df())
    t_k = float(RGPOX_T_C) + 273.15
    p_bar = float(specs.get("SYSTEM_P_BAR", 15.0))

    spike_case = build_spike_case(elem, t_k=t_k, p_bar=p_bar, case_id="Case-1-RGPOX")
    gold = solve_gibbs_major(elem, MAJOR_SPECIES, t_k, p_bar)

    lsq = lsq_linear(spike_case.a_matrix, spike_case.b_vector, bounds=(0.0, np.inf))
    x0 = np.maximum(lsq.x, _FLOW_FLOOR)
    reduced = solve_gibbs_spike_reduced(spike_case, x0)

    deltas = {}
    rel_errors: List[float] = []
    for sp in spike_case.species:
        g = gold.species_flow_mol_h.get(sp, 0.0)
        r = reduced.species_flow_mol_h.get(sp, 0.0)
        denom = max(abs(g), 1e-3)
        deltas[sp] = abs(r - g) / denom
        if abs(g) >= 1e-3:
            rel_errors.append(deltas[sp])

    return {
        "spike_case": spike_case,
        "gold": gold,
        "reduced": reduced,
        "max_rel_err": max(rel_errors) if rel_errors else 0.0,
        "deltas": deltas,
        "x0": x0,
        "elemental_feed": elem,
    }


def run_case1_spike_comparison() -> Dict[str, object]:
    """Case-1 INCI Gibbs：scipy 金标准 vs 约化维数 spike。"""
    from scipy.optimize import lsq_linear

    elem, _sample = case1_inci_elemental_feed_mol_h()
    specs = _spec_map(build_specs_df())
    t_k = float(specs.get("INCI_T_C", 900.0)) + 273.15
    p_bar = float(specs.get("SYSTEM_P_BAR", 15.0))

    spike_case = build_spike_case(elem, t_k=t_k, p_bar=p_bar)
    gold = solve_gibbs_major(elem, MAJOR_SPECIES, t_k, p_bar)

    lsq = lsq_linear(spike_case.a_matrix, spike_case.b_vector, bounds=(0.0, np.inf))
    x0 = np.maximum(lsq.x, _FLOW_FLOOR)
    reduced = solve_gibbs_spike_reduced(spike_case, x0)

    deltas = {}
    rel_errors: List[float] = []
    for sp in spike_case.species:
        g = gold.species_flow_mol_h.get(sp, 0.0)
        r = reduced.species_flow_mol_h.get(sp, 0.0)
        denom = max(abs(g), 1e-3)
        deltas[sp] = abs(r - g) / denom
        if abs(g) >= 1e-3:
            rel_errors.append(deltas[sp])

    return {
        "spike_case": spike_case,
        "gold": gold,
        "reduced": reduced,
        "max_rel_err": max(rel_errors) if rel_errors else 0.0,
        "deltas": deltas,
        "x0": x0,
    }
