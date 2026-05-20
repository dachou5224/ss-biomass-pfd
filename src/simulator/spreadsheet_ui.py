"""Spread Simulator 前端：用户可调字段 vs VBA 内部常数。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, List

import pandas as pd

from .parameters import DEFAULT_REACTOR_SPECS, PROJECT_ROOT, load_json_config

# 与 Streamlit Operating / 工况设定一致，出现在 Model_Input
USER_OPERATING_SPECS: tuple[str, ...] = (
    "INCI_T_C",
    "SLAG_T_C",
    "SYSTEM_P_BAR",
)

# 与 Streamlit Chemistry 表一致的可调项（不含固定 Tar 分子式、平衡模式标签等）
USER_CHEMISTRY_FIELDS: tuple[str, ...] = (
    "Sample",
    "Tar Fuel Type",
    "Tar Internal Path",
    "Pyrolysis Tar Carbon Frac",
    "Tar Yield Factor",
    "Tar target H/C",
    "Pyrolysis Scheme",
    "Biomass VM Dry wt%",
    "TA DeltaT WGS (C)",
    "TA DeltaT Meth (C)",
    "WGS Equilibrium Approach Eta",
    "Meth Equilibrium Approach Eta",
    "TA DeltaT OxCO (C)",
    "TA DeltaT OxH2 (C)",
    "TA DeltaT OxCH4 (C)",
    "RGPOX TA DeltaT WGS (C)",
    "RGPOX TA DeltaT Meth (C)",
    "RGPOX WGS Equilibrium Approach Eta",
    "RGPOX Meth Equilibrium Approach Eta",
    "RGPOX TA DeltaT OxCO (C)",
    "RGPOX TA DeltaT OxH2 (C)",
    "RGPOX TA DeltaT OxCH4 (C)",
    "O2 Purity vol%",
    "O2IN O2 mol%",
    "O2IN N2 mol%",
    "O2IN Ar mol%",
    "H2S/COS split to H2S",
    "Biomass N to NH3 Frac",
    "Biomass S Release Frac",
)

# 留在 VBA「ModelInternals」块，不出现在前端 Sheet
INTERNAL_REACTOR_SPECS: tuple[str, ...] = tuple(
    k for k in DEFAULT_REACTOR_SPECS if k not in USER_OPERATING_SPECS
)

INTERNAL_CHEMISTRY_FIELDS: tuple[str, ...] = (
    "Tar Formula",
    "Constraint Mode",
)

VBA_EXPORT_DIR = PROJECT_ROOT / "export" / "vba"


def filter_user_specs_df(specs_df: pd.DataFrame) -> pd.DataFrame:
    allowed = set(USER_OPERATING_SPECS)
    return specs_df[specs_df["Parameter"].isin(allowed)].reset_index(drop=True)


def filter_user_chem_df(chem_df: pd.DataFrame) -> pd.DataFrame:
    allowed = set(USER_CHEMISTRY_FIELDS)
    return chem_df[chem_df["Field"].isin(allowed)].reset_index(drop=True)


def _vba_const_name(key: str) -> str:
    return (
        key.replace(" ", "_")
        .replace("/", "_")
        .replace("%", "Pct")
        .replace("@", "At")
        .replace("(", "")
        .replace(")", "")
        .replace("-", "_")
        .replace(".", "_")
    )


def _vba_value(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    if value is None:
        return '""'
    escaped = str(value).replace('"', '""')
    return f'"{escaped}"'


def _emit_vba_const(lines: List[str], key: str, val: Any) -> None:
    name = _vba_const_name(key)
    if isinstance(val, bool):
        lines.append(f"Public Const {name} As Boolean = {'True' if val else 'False'}")
    elif isinstance(val, (int, float)):
        lines.append(f"Public Const {name} As Double = {val!r}")
    else:
        lines.append(f"Public Const {name} As String = {_vba_value(val)}")


def _emit_vba_block(lines: List[str], title: str, pairs: Iterable[tuple[str, Any]]) -> None:
    lines.append(f"' ===== {title} =====")
    for key, val in pairs:
        _emit_vba_const(lines, key, val)
    lines.append("")


def build_vba_internals_source() -> str:
    """从 config/model_parameters.json 生成 VBA 常量模块源码。"""
    cfg = load_json_config("model_parameters")
    lines: List[str] = [
        "Attribute VB_Name = \"ModelInternals\"",
        "' 自动生成：scripts/build_simulator_workbook.py",
        "' 内部模型常数 — 勿放入 Model_Input / Model_Output 前端表。",
        "' Python 侧同源：config/model_parameters.json",
        "",
    ]

    fixed = cfg.get("model_fixed", {})
    _emit_vba_block(
        lines,
        "MODEL_FIXED",
        ((k, v) for k, v in fixed.items() if not str(k).startswith("_")),
    )

    reactor = cfg.get("reactor_specs", {})
    _emit_vba_block(
        lines,
        "REACTOR_INTERNALS",
        ((k, v) for k, v in reactor.items() if k in INTERNAL_REACTOR_SPECS and not str(k).startswith("_")),
    )

    chem = cfg.get("chemistry_setup", {})
    _emit_vba_block(
        lines,
        "CHEMISTRY_INTERNALS",
        ((k, v) for k, v in chem.items() if k in INTERNAL_CHEMISTRY_FIELDS and not str(k).startswith("_")),
    )

    for section in ("physical_constants", "gibbs_solver", "tar_model", "species_lists"):
        block = cfg.get(section)
        if not isinstance(block, dict):
            continue
        flat: List[tuple[str, Any]] = []

        def walk(prefix: str, obj: Any) -> None:
            if isinstance(obj, dict):
                for sk, sv in obj.items():
                    if str(sk).startswith("_"):
                        continue
                    walk(f"{prefix}_{sk}" if prefix else sk, sv)
            else:
                flat.append((prefix, obj))

        walk("", block)
        if flat:
            _emit_vba_block(lines, section.upper(), flat)

    return "\n".join(lines) + "\n"


def write_vba_internals_module(out_dir: Path | None = None) -> Path:
    out_dir = out_dir or VBA_EXPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "ModelInternals.bas"
    path.write_text(build_vba_internals_source(), encoding="utf-8")
    readme = out_dir / "README.md"
    readme.write_text(
        "# VBA 模块（Spread Simulator 内部参数）\n\n"
        "将 `ModelInternals.bas` 导入 Excel **VBE**（Alt+F11 → 文件 → 导入）。\n\n"
        "- **ModelInternals**：固定反应器分配、Tar 分子式、Gibbs/物种/热力学常数等。\n"
        "- 用户可调项仅出现在工作簿 **Model_Input**（进料、操作温度/压力、化学调参）。\n\n"
        "重新生成：`python3 scripts/build_simulator_workbook.py`\n",
        encoding="utf-8",
    )
    return path
