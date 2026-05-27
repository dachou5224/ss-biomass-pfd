#!/usr/bin/env python3
"""从 WPS 另存的最小 xlsm 提取 JDEData.bin 与 OOXML 类型，更新 packaging.json。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "export" / "template" / "wps_jsa"
PACKAGING_JSON = TEMPLATE_DIR / "packaging.json"

RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从含 JS 宏的 WPS xlsm 提取 JDEData.bin 与关系类型"
    )
    parser.add_argument(
        "xlsm",
        type=Path,
        help="在 WPS 中新建 JS 宏（任意一行代码）后另存为 xlsm 的路径",
    )
    args = parser.parse_args()
    path = args.xlsm.resolve()
    if not path.is_file():
        print(f"文件不存在: {path}", file=sys.stderr)
        sys.exit(1)

    with zipfile.ZipFile(path, "r") as zf:
        if "xl/JDEData.bin" not in zf.namelist():
            print(
                "未找到 xl/JDEData.bin。请确认已在 WPS「开发工具 → JS 宏」中保存过代码。",
                file=sys.stderr,
            )
            sys.exit(1)
        jde = zf.read("xl/JDEData.bin")
        rels = zf.read("xl/_rels/workbook.xml.rels")
        ct = zf.read("[Content_Types].xml")

    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    (TEMPLATE_DIR / "JDEData.sample.bin").write_bytes(jde)

    root_rels = ET.fromstring(rels)
    rel_type = None
    for el in root_rels.findall(f"{{{RELS_NS}}}Relationship"):
        if el.get("Target", "").endswith("JDEData.bin"):
            rel_type = el.get("Type")
            break

    ct_root = ET.fromstring(ct)
    content_type = None
    for el in ct_root.findall(f"{{{CT_NS}}}Override"):
        if "JDEData.bin" in (el.get("PartName") or ""):
            content_type = el.get("ContentType")
            break

    cfg = {
        "jde_filename": "JDEData.bin",
        "jde_relationship_type": rel_type or "",
        "jde_content_type": content_type or "",
        "note": f"从 {path.name} 捕获；供 seal_workbook_for_wps 使用",
    }
    PACKAGING_JSON.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(path, TEMPLATE_DIR / "reference_minimal.xlsm")
    print(f"已更新 {PACKAGING_JSON}")
    print(f"已保存 JDEData 样本 → {TEMPLATE_DIR / 'JDEData.sample.bin'}")
    if rel_type:
        print(f"  relationship Type = {rel_type}")
    if content_type:
        print(f"  ContentType = {content_type}")


if __name__ == "__main__":
    main()
