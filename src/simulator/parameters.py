"""从 config/*.json 加载模型参数（含 _comment 说明键，加载时剔除）。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


def _strip_comments(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _strip_comments(v)
            for k, v in obj.items()
            if k not in ("_comment", "_meta")
        }
    if isinstance(obj, list):
        return [_strip_comments(v) for v in obj]
    return obj


@lru_cache(maxsize=16)
def load_json_config(stem: str) -> Dict[str, Any]:
    path = CONFIG_DIR / f"{stem}.json"
    if not path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with path.open(encoding="utf-8") as fh:
        return _strip_comments(json.load(fh))


def reload_config() -> None:
    """测试或热重载时清空缓存。"""
    load_json_config.cache_clear()


def feeds_to_tuples(feeds: Mapping[str, List[float]]) -> Dict[str, Tuple[float, float, float]]:
    return {k: (float(v[0]), float(v[1]), float(v[2])) for k, v in feeds.items()}


def _section(key: str) -> Dict[str, Any]:
    return dict(model_parameters().get(key, {}))


def model_parameters() -> Dict[str, Any]:
    return load_json_config("model_parameters")


INCI_C_CONVERSION: float = model_parameters()["model_fixed"]["inci_c_conversion"]
DEFAULT_REACTOR_SPECS: Dict[str, float] = dict(model_parameters()["reactor_specs"])
DEFAULT_CHEMISTRY_SETUP: Dict[str, Any] = dict(model_parameters()["chemistry_setup"])
DEFAULT_CASE_ID: str = model_parameters()["defaults"]["case_id"]
DEFAULT_BIOMASS_SAMPLE_FALLBACK: str = model_parameters()["defaults"]["biomass_sample_fallback"]

PHYSICAL_CONSTANTS: Dict[str, Any] = dict(model_parameters()["physical_constants"])
ATOMIC_WEIGHT: Dict[str, float] = dict(PHYSICAL_CONSTANTS["atomic_weight"])
MOLECULAR_WEIGHT: Dict[str, float] = dict(PHYSICAL_CONSTANTS["molecular_weight"])
CELSIUS_TO_KELVIN_OFFSET: float = float(PHYSICAL_CONSTANTS["celsius_to_kelvin_offset"])

SPECIES_CFG: Dict[str, Any] = dict(model_parameters()["species"])
MAJOR_SPECIES: Tuple[str, ...] = tuple(SPECIES_CFG["major"])
MINOR_SPECIES: Tuple[str, ...] = tuple(SPECIES_CFG["minor"])
INCI_MAJOR_KEYS: Tuple[str, ...] = tuple(SPECIES_CFG["inci_major"])
INCI_WET_MAJOR_KEYS: Tuple[str, ...] = tuple(SPECIES_CFG.get("inci_wet_major", ("CO", "H2", "CO2", "CH4", "H2O")))
INCI_UNMODELLED_WET_SPECIES: Tuple[str, ...] = tuple(SPECIES_CFG["unmodelled_wet"])
GIBBS_ELEMENTS: Tuple[str, ...] = tuple(SPECIES_CFG["gibbs_elements"])
INCI_DRY_SPECIES: Tuple[str, ...] = INCI_MAJOR_KEYS + ("N2", "Ar") + MINOR_SPECIES
INCI_WET_SPECIES: Tuple[str, ...] = INCI_DRY_SPECIES + ("H2O",)

ATOM_COUNT: Dict[str, Dict[str, int]] = {
    k: dict(v) for k, v in model_parameters()["atom_count"].items()
}

TAR_MODELS_CFG: Dict[str, Any] = dict(model_parameters()["tar_models"])
PYROLYSIS_CFG: Dict[str, Any] = dict(model_parameters()["pyrolysis"])
EQUILIBRIUM_CFG: Dict[str, Any] = dict(model_parameters()["equilibrium"])
GIBBS_SOLVER_CFG: Dict[str, Any] = dict(model_parameters()["gibbs_solver"])
SLAG_CFG: Dict[str, Any] = dict(model_parameters()["slag"])
RGPOX_CFG: Dict[str, Any] = dict(model_parameters()["rgpox"])
NUMERICAL_CFG: Dict[str, Any] = dict(model_parameters()["numerical"])
AUDIT_CFG: Dict[str, Any] = dict(model_parameters()["audit"])
PATHS_CFG: Dict[str, str] = dict(model_parameters()["paths"])

DBI_O2IN_MOL_PCT: Dict[str, float] = {
    "O2": float(DEFAULT_CHEMISTRY_SETUP["O2IN O2 mol%"]),
    "N2": float(DEFAULT_CHEMISTRY_SETUP["O2IN N2 mol%"]),
    "Ar": float(DEFAULT_CHEMISTRY_SETUP["O2IN Ar mol%"]),
}


def dbi_inlet_config() -> Dict[str, Any]:
    return load_json_config("dbi_inlet")


def dbi_case1_inlet() -> Dict[str, Any]:
    return dict(dbi_inlet_config()["Case-1"])


INCI_INLET_STREAMS: Tuple[str, ...] = tuple(dbi_inlet_config()["inci_inlet_streams"])
COMPARE_SPECIES: Tuple[str, ...] = tuple(dbi_inlet_config()["compare_species"])
INLET_COMPARE_MIN_KG_H: float = float(NUMERICAL_CFG.get("inlet_compare_min_kg_h", 0.05))


def thermo_config() -> Dict[str, Any]:
    return load_json_config("thermo_shomate")


THERMO_BASELINE_VERSION: str = thermo_config()["baseline_version"]
R_CONST: float = float(thermo_config()["gas_constant_j_mol_k"])
SHOMATE_DB: Dict[str, Any] = dict(thermo_config()["shomate_db"])
SOLID_CARBON_THERMO: Dict[str, float] = dict(thermo_config()["solid_carbon"])
