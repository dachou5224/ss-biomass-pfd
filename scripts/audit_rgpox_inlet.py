#!/usr/bin/env python3
"""打印 RGPOX 边界进料 vs DBI Unit 15 物流表；TA 调参前门禁检查。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df


def main() -> None:
    parser = argparse.ArgumentParser(description="RGPOX 进料对标 DBI Unit 15")
    parser.add_argument("--case", default="Case-1")
    args = parser.parse_args()

    res = run_fixed_temperature_simulation(
        build_feed_df(args.case),
        build_specs_df(),
        build_chem_df(args.case),
    )
    audit = res.rgpox_inlet_audit
    if audit is None:
        print(f"{args.case}: 无 RGPOX 进料审计（非参考工况或未配置 dbi_rgpox_inlet.json）")
        return

    print(f"=== {args.case} RGPOX 进料 vs DBI (Unit 15 p2) ===")
    print(f"15PGI-1 湿基 RMSD: {audit.gas_wet_rmsd_pct:.3f}%" if audit.gas_wet_rmsd_pct else "组成 RMSD: N/A")
    print(f"TA 调参门禁: {'通过' if audit.ready_for_ta_tuning else '未通过'}")
    if audit.blockers:
        print("\n阻塞项:")
        for b in audit.blockers:
            print(f"  - {b}")

    print("\n--- 质量流量 (kg/h) ---")
    print(f"{'Stream':<10} {'Line':<14} {'DBI':>10} {'Model':>10} {'Delta':>10}")
    for row in audit.mass_rows:
        print(f"{row.stream_id:<10} {row.component:<14} {row.dbi_kg_h:10.2f} {row.model_kg_h:10.2f} {row.delta_kg_h:+10.2f}")

    print("\n--- 15PGI-1 气相湿基 mol% ---")
    print(f"{'Species':<6} {'DBI':>10} {'Model':>10} {'Delta pp':>10}")
    for row in audit.composition_rows:
        print(f"{row.component:<6} {row.dbi_kg_h:10.4f} {row.model_kg_h:10.4f} {row.delta_kg_h:+10.4f}")


if __name__ == "__main__":
    main()
