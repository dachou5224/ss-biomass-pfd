from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .parameters import ATOMIC_WEIGHT

INCI_SOLID_ROUTING_FLY_ASH = "fly_ash_ratio"
INCI_SOLID_ROUTING_DBI_BOUNDARY = "dbi_boundary"
INCI_SOLID_ROUTING_LEGACY_FRAC = "legacy_frac"


def parse_inci_solid_routing_mode(value: str | None) -> str:
    """Normalize Chemistry/UI routing mode labels."""
    text = str(value or INCI_SOLID_ROUTING_FLY_ASH).strip().lower().replace("_", " ")
    if "dbi" in text and "boundary" in text:
        return INCI_SOLID_ROUTING_DBI_BOUNDARY
    if "legacy" in text or "frac" in text:
        return INCI_SOLID_ROUTING_LEGACY_FRAC
    if "fly" in text or "ratio" in text or "灰渣" in text:
        return INCI_SOLID_ROUTING_FLY_ASH
    return INCI_SOLID_ROUTING_FLY_ASH


@dataclass(frozen=True)
class InciFlyAshSlagParams:
    """INCI 流化床固相路由：飞灰(含残炭) / 底渣 灰渣比与残炭率。"""

    fly_ash_to_slag_mass_ratio: float
    fly_ash_residual_carbon_wt_pct_dry: float
    slag_residual_carbon_wt_pct_dry: float = 0.0


@dataclass(frozen=True)
class InciCarbonTarget:
    reactive_char_mol_h: float
    residual_char_mol_h: float
    effective_char_conversion: float


@dataclass(frozen=True)
class InciSolidRouting:
    reactive_char_mol_h: float
    residual_char_mol_h: float
    effective_char_conversion: float
    effective_ash_kg_h: float
    ash_to_slag_kg_h: float
    ash_to_pox_kg_h: float
    char_to_slag_kg_h: float
    char_to_pox_kg_h: float
    target_residual_c_kg_h: float
    slag_to_u14_kg_h: float

    @property
    def fly_ash_total_kg_h(self) -> float:
        return self.char_to_pox_kg_h + self.ash_to_pox_kg_h

    @property
    def fly_ash_to_slag_mass_ratio(self) -> float | None:
        if self.slag_to_u14_kg_h <= 1e-12:
            return None
        return self.fly_ash_total_kg_h / self.slag_to_u14_kg_h

    @property
    def fly_ash_residual_carbon_wt_pct_dry(self) -> float | None:
        total = self.fly_ash_total_kg_h
        if total <= 1e-12:
            return None
        return 100.0 * self.char_to_pox_kg_h / total


def resolve_inci_solid_routing_fly_ash_ratio(
    *,
    biomass_total_c_mol_h: float,
    char_pool_c_mol_h: float,
    target_conversion: float,
    fly_ash_params: InciFlyAshSlagParams,
) -> InciSolidRouting:
    """
    INCI 流化床固相路由：按灰渣比将未转化碳与灰分分到
    15PGI-1 夹带固相（fly ash + char entrained）与 13LBS-1 底渣。

    飞灰总质量 = 夹带碳 / (fly_ash C wt%)；底渣 = 飞灰 / 灰渣比。
    当底渣残炭 wt%=0 时，未转化碳全部进入夹带飞灰（DBI Case-1 口径）。
    """
    carbon_target = resolve_inci_char_for_overall_biomass_conversion(
        biomass_total_c_mol_h=biomass_total_c_mol_h,
        char_pool_c_mol_h=char_pool_c_mol_h,
        target_conversion=target_conversion,
    )
    char_pool_mol = max(float(char_pool_c_mol_h), 0.0)
    residual_char_kg_h = carbon_target.residual_char_mol_h * ATOMIC_WEIGHT["C"] / 1000.0

    ratio = max(float(fly_ash_params.fly_ash_to_slag_mass_ratio), 1e-12)
    fly_c_frac = float(np.clip(fly_ash_params.fly_ash_residual_carbon_wt_pct_dry, 0.0, 100.0)) / 100.0
    slag_c_frac = float(np.clip(fly_ash_params.slag_residual_carbon_wt_pct_dry, 0.0, 100.0)) / 100.0
    fly_c_frac = max(fly_c_frac, 1e-12)

    if residual_char_kg_h <= 1e-12:
        slag_to_u14_kg_h = 0.0
        char_to_slag_kg_h = 0.0
        char_to_pox_kg_h = 0.0
        fly_ash_total_kg_h = 0.0
        ash_to_pox_kg_h = 0.0
        ash_to_slag_kg_h = 0.0
    else:
        denominator = ratio * fly_c_frac + slag_c_frac
        slag_to_u14_kg_h = residual_char_kg_h / max(denominator, 1e-12)
        char_to_slag_kg_h = slag_to_u14_kg_h * slag_c_frac
        char_to_pox_kg_h = max(residual_char_kg_h - char_to_slag_kg_h, 0.0)
        fly_ash_total_kg_h = char_to_pox_kg_h / fly_c_frac
        ash_to_pox_kg_h = max(fly_ash_total_kg_h - char_to_pox_kg_h, 0.0)
        ash_to_slag_kg_h = max(slag_to_u14_kg_h - char_to_slag_kg_h, 0.0)

    effective_ash_kg_h = ash_to_slag_kg_h + ash_to_pox_kg_h
    target_residual_c_kg_h = char_to_slag_kg_h
    return InciSolidRouting(
        reactive_char_mol_h=carbon_target.reactive_char_mol_h,
        residual_char_mol_h=carbon_target.residual_char_mol_h,
        effective_char_conversion=carbon_target.effective_char_conversion,
        effective_ash_kg_h=effective_ash_kg_h,
        ash_to_slag_kg_h=ash_to_slag_kg_h,
        ash_to_pox_kg_h=ash_to_pox_kg_h,
        char_to_slag_kg_h=char_to_slag_kg_h,
        char_to_pox_kg_h=char_to_pox_kg_h,
        target_residual_c_kg_h=target_residual_c_kg_h,
        slag_to_u14_kg_h=slag_to_u14_kg_h,
    )


def resolve_inci_char_for_overall_biomass_conversion(
    *,
    biomass_total_c_mol_h: float,
    char_pool_c_mol_h: float,
    target_conversion: float,
) -> InciCarbonTarget:
    """Map an overall biomass carbon conversion target onto the remaining INCI char pool."""
    biomass_total = max(float(biomass_total_c_mol_h), 0.0)
    char_pool = max(float(char_pool_c_mol_h), 0.0)
    target = float(np.clip(target_conversion, 0.0, 1.0))

    target_residual = biomass_total * (1.0 - target)
    residual_char = min(max(target_residual, 0.0), char_pool)
    reactive_char = max(char_pool - residual_char, 0.0)
    effective_char_conversion = reactive_char / char_pool if char_pool > 0.0 else 0.0
    return InciCarbonTarget(
        reactive_char_mol_h=reactive_char,
        residual_char_mol_h=residual_char,
        effective_char_conversion=effective_char_conversion,
    )


def resolve_inci_solid_routing(
    *,
    biomass_total_c_mol_h: float,
    char_pool_c_mol_h: float,
    ash_kg_h: float,
    target_conversion: float,
    ash_to_slag_frac: float,
    char_to_slag_frac: float,
    slag_residual_c_ash_mass_ratio: float,
    dbi_boundary_basis: dict[str, float] | None = None,
    solid_routing_mode: str = INCI_SOLID_ROUTING_FLY_ASH,
    fly_ash_params: InciFlyAshSlagParams | None = None,
) -> InciSolidRouting:
    """Resolve INCI residual solid routing for FBR fly ash / bottom slag split."""
    mode = parse_inci_solid_routing_mode(solid_routing_mode)
    if mode == INCI_SOLID_ROUTING_FLY_ASH:
        params = fly_ash_params or InciFlyAshSlagParams(
            fly_ash_to_slag_mass_ratio=2.5027,
            fly_ash_residual_carbon_wt_pct_dry=73.37,
            slag_residual_carbon_wt_pct_dry=0.0,
        )
        return resolve_inci_solid_routing_fly_ash_ratio(
            biomass_total_c_mol_h=biomass_total_c_mol_h,
            char_pool_c_mol_h=char_pool_c_mol_h,
            target_conversion=target_conversion,
            fly_ash_params=params,
        )

    char_pool_mol = max(float(char_pool_c_mol_h), 0.0)

    if mode == INCI_SOLID_ROUTING_DBI_BOUNDARY and dbi_boundary_basis:
        char_pool_kg_h = char_pool_mol * ATOMIC_WEIGHT["C"] / 1000.0
        bottom_slag_carbon_kg_h = max(float(dbi_boundary_basis.get("bottom_slag_carbon_kg_h", 0.0)), 0.0)
        entrained_solid_carbon_kg_h = max(float(dbi_boundary_basis.get("entrained_solid_carbon_kg_h", 0.0)), 0.0)
        target_residual_char_kg_h = bottom_slag_carbon_kg_h + entrained_solid_carbon_kg_h
        residual_char_kg_h = min(target_residual_char_kg_h, char_pool_kg_h)
        scale = residual_char_kg_h / target_residual_char_kg_h if target_residual_char_kg_h > 1e-12 else 0.0
        char_to_slag_kg_h = bottom_slag_carbon_kg_h * scale
        char_to_pox_kg_h = entrained_solid_carbon_kg_h * scale
        bottom_slag_total_kg_h = max(float(dbi_boundary_basis.get("bottom_slag_total_kg_h", 0.0)), 0.0)
        entrained_solid_total_kg_h = max(float(dbi_boundary_basis.get("entrained_solid_total_kg_h", 0.0)), 0.0)
        ash_to_slag_kg_h = max(bottom_slag_total_kg_h - bottom_slag_carbon_kg_h, 0.0)
        ash_to_pox_kg_h = max(entrained_solid_total_kg_h - entrained_solid_carbon_kg_h, 0.0)
        effective_ash_kg_h = ash_to_slag_kg_h + ash_to_pox_kg_h
        target_residual_c_kg_h = char_to_slag_kg_h
        slag_to_u14_kg_h = ash_to_slag_kg_h + target_residual_c_kg_h
        residual_char_mol_h = residual_char_kg_h * 1000.0 / ATOMIC_WEIGHT["C"]
        reactive_char_mol_h = max(char_pool_mol - residual_char_mol_h, 0.0)
        effective_char_conversion = reactive_char_mol_h / char_pool_mol if char_pool_mol > 0.0 else 0.0
        return InciSolidRouting(
            reactive_char_mol_h=reactive_char_mol_h,
            residual_char_mol_h=residual_char_mol_h,
            effective_char_conversion=effective_char_conversion,
            effective_ash_kg_h=effective_ash_kg_h,
            ash_to_slag_kg_h=ash_to_slag_kg_h,
            ash_to_pox_kg_h=ash_to_pox_kg_h,
            char_to_slag_kg_h=char_to_slag_kg_h,
            char_to_pox_kg_h=char_to_pox_kg_h,
            target_residual_c_kg_h=target_residual_c_kg_h,
            slag_to_u14_kg_h=slag_to_u14_kg_h,
        )

    carbon_target = resolve_inci_char_for_overall_biomass_conversion(
        biomass_total_c_mol_h=biomass_total_c_mol_h,
        char_pool_c_mol_h=char_pool_c_mol_h,
        target_conversion=target_conversion,
    )
    residual_char_kg_h = carbon_target.residual_char_mol_h * ATOMIC_WEIGHT["C"] / 1000.0
    char_to_slag_kg_h = residual_char_kg_h * float(np.clip(char_to_slag_frac, 0.0, 1.0))
    char_to_pox_kg_h = max(residual_char_kg_h - char_to_slag_kg_h, 0.0)
    effective_ash_kg_h = max(float(ash_kg_h), 0.0)
    ash_to_slag_kg_h = effective_ash_kg_h * float(np.clip(ash_to_slag_frac, 0.0, 1.0))
    ash_to_pox_kg_h = max(effective_ash_kg_h - ash_to_slag_kg_h, 0.0)
    ratio = max(float(slag_residual_c_ash_mass_ratio), 1e-12)
    target_residual_c_kg_h = min(ash_to_slag_kg_h / ratio, char_to_slag_kg_h)
    slag_to_u14_kg_h = ash_to_slag_kg_h + target_residual_c_kg_h
    return InciSolidRouting(
        reactive_char_mol_h=carbon_target.reactive_char_mol_h,
        residual_char_mol_h=carbon_target.residual_char_mol_h,
        effective_char_conversion=carbon_target.effective_char_conversion,
        effective_ash_kg_h=effective_ash_kg_h,
        ash_to_slag_kg_h=ash_to_slag_kg_h,
        ash_to_pox_kg_h=ash_to_pox_kg_h,
        char_to_slag_kg_h=char_to_slag_kg_h,
        char_to_pox_kg_h=char_to_pox_kg_h,
        target_residual_c_kg_h=target_residual_c_kg_h,
        slag_to_u14_kg_h=slag_to_u14_kg_h,
    )
