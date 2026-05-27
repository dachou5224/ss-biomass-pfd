#!/usr/bin/env python3
"""生成与 Streamlit 页签对应的 Excel 工作簿。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from simulator.excel_export import (
    DEFAULT_EXPORT_PATH,
    DEFAULT_WPS_EXPORT_PATH,
    write_simulator_workbook,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 Biomass PFD Simulator Excel")
    parser.add_argument("--case", default="Case-1", help="参考工况")
    parser.add_argument("--out", type=Path, default=DEFAULT_EXPORT_PATH, help="输出 xlsx 路径")
    parser.add_argument(
        "--wps-out",
        type=Path,
        default=DEFAULT_WPS_EXPORT_PATH,
        help="WPS 开箱即用 xlsm 输出路径",
    )
    parser.add_argument(
        "--no-wps",
        action="store_true",
        help="不生成内嵌 JS 宏的 WPS 版 xlsm",
    )
    parser.add_argument("--no-run", action="store_true", help="不运行仿真，仅导出输入表")
    args = parser.parse_args()
    path = write_simulator_workbook(
        args.out,
        case_id=args.case,
        run_simulation=not args.no_run,
        wps_ready=not args.no_wps,
        wps_path=args.wps_out,
    )
    print(f"已写入 {path}")
    if not args.no_wps:
        print(f"WPS 分发版（内嵌宏）: {args.wps_out}")
    print("VBA 内部参数: export/vba/ModelInternals.bas")
    print("流程图: export/assets/流程示意图.png → Excel PFD 页")


if __name__ == "__main__":
    main()
