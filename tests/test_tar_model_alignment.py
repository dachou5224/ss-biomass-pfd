import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.tar_models import (
    TAR_SURROGATE_FORMULA,
    allocate_tar_moles_from_carbon,
    calc_tar_surrogate_fractions,
)


def test_biomass_tar_mapping_uses_c10h8_and_c16h34():
    alloc = allocate_tar_moles_from_carbon(100.0, fuel_type="biomass", target_hc_ratio=1.2)
    assert alloc.surrogate_map["TAR1"] == "C10H8"
    assert alloc.surrogate_map["TAR2"] == "C16H34"
    assert alloc.tar_mol_h["TAR1"] >= 0.0
    assert alloc.tar_mol_h["TAR2"] >= 0.0


def test_coal_tar_mapping_uses_c6h6_and_c10h8():
    alloc = allocate_tar_moles_from_carbon(100.0, fuel_type="coal")
    assert alloc.surrogate_map["TAR1"] == "C6H6"
    assert alloc.surrogate_map["TAR2"] == "C10H8"


def test_fraction_solver_rejects_unrepresentable_hc():
    with pytest.raises(ValueError):
        calc_tar_surrogate_fractions("biomass", target_hc_ratio=10.0)


def test_allocation_falls_back_to_default_when_hc_out_of_range():
    alloc = allocate_tar_moles_from_carbon(50.0, fuel_type="biomass", target_hc_ratio=10.0)
    c_atoms_1, h_atoms_1 = TAR_SURROGATE_FORMULA[alloc.surrogate_map["TAR1"]]
    c_atoms_2, h_atoms_2 = TAR_SURROGATE_FORMULA[alloc.surrogate_map["TAR2"]]
    c_calc = c_atoms_1 * alloc.tar_mol_h["TAR1"] + c_atoms_2 * alloc.tar_mol_h["TAR2"]
    h_calc = h_atoms_1 * alloc.tar_mol_h["TAR1"] + h_atoms_2 * alloc.tar_mol_h["TAR2"]
    assert alloc.carbon_mol_h == pytest.approx(c_calc, rel=0, abs=1e-10)
    assert alloc.hydrogen_mol_h == pytest.approx(h_calc, rel=0, abs=1e-10)
