#!/usr/bin/env python3
"""打包 Excel 邮件分发 zip：xlsx + WebServiceDemo.js + 用户手册。"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "export" / "Biomass_PFD_Simulator_Excel分发.zip"
FILES = (
    ROOT / "export" / "Biomass_PFD_Simulator.xlsx",
    ROOT / "export" / "js" / "WebServiceDemo.js",
    ROOT / "doc" / "excel_用户操作手册.md",
)


def main() -> None:
    missing = [p for p in FILES if not p.is_file()]
    if missing:
        raise SystemExit(
            "缺少文件，请先运行 build_simulator_workbook.py：\n"
            + "\n".join(f"  - {p}" for p in missing)
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in FILES:
            zf.write(path, arcname=path.name)
    print(f"已写入 {OUT}")


if __name__ == "__main__":
    main()
