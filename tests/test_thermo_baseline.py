import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.thermo_baseline import SHOMATE_DB, get_gibbs_free_energy


def test_o2_coefficients_aligned_with_reference():
    assert SHOMATE_DB["O2"]["Low"][0] == pytest.approx(29.65900, rel=0, abs=1e-8)
    assert SHOMATE_DB["O2"]["High"][0] == pytest.approx(29.52620, rel=0, abs=1e-8)


def test_minor_species_and_char_supported_in_thermo_baseline():
    for species in ("H2S", "COS", "C"):
        g = get_gibbs_free_energy(species, 1400.0)
        assert isinstance(g, float)


def test_shomate_range_validation():
    with pytest.raises(ValueError):
        get_gibbs_free_energy("CO", 100.0)
