"""Gibbs 迁移 spike：约化维数 vs scipy SLSQP。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.gibbs_spike import run_case1_rgpox_spike_comparison, run_case1_spike_comparison


def test_reduced_b_spike_matches_gold_within_tolerance():
    cmp = run_case1_spike_comparison()
    assert cmp["gold"].success
    assert cmp["reduced"].success, cmp["reduced"].message
    assert cmp["reduced"].balance_residual < 1e-4
    assert cmp["max_rel_err"] < 0.05, f"max rel err {cmp['max_rel_err']:.4%}"


def test_rgpox_reduced_b_spike_matches_gold_within_tolerance():
    cmp = run_case1_rgpox_spike_comparison()
    assert cmp["gold"].success
    assert cmp["reduced"].success, cmp["reduced"].message
    assert cmp["reduced"].balance_residual < 1e-4
    assert cmp["max_rel_err"] < 0.065, f"RGPOX max rel err {cmp['max_rel_err']:.4%}"


def test_vba_nelder_mead_logic_matches_gold_with_z_seed():
    import subprocess

    script = os.path.join(os.path.dirname(__file__), "..", "scripts", "validate_gibbs_spike_vba.py")
    if not os.path.isfile(script):
        pytest.skip("validate script missing")
    xlsx = os.path.join(os.path.dirname(__file__), "..", "export", "Gibbs_Spike_Test.xlsx")
    if not os.path.isfile(xlsx):
        pytest.skip("run build_gibbs_spike_workbook.py first")
    proc = subprocess.run([sys.executable, script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_gibbs_spike_workbook_exists():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "export" / "Gibbs_Spike_Test.xlsx"
    if not path.is_file():
        pytest.skip("运行 scripts/build_gibbs_spike_workbook.py 后生成")
    assert path.stat().st_size > 2000
