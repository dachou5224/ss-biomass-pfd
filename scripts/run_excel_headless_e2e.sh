#!/usr/bin/env bash
# Excel WebService 无头 E2E（无需打开 Excel）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f export/Biomass_PFD_Simulator.xlsx ]]; then
  python3 scripts/build_simulator_workbook.py --case Case-1
fi

if [[ -z "${SIM_API_KEY:-}" ]]; then
  if command -v ssh >/dev/null 2>&1; then
    SIM_API_KEY="$(ssh -o BatchMode=yes -o ConnectTimeout=20 nice-ai-LZ \
      'grep SIM_API_KEY /etc/default/ss-biomass-api' 2>/dev/null | cut -d= -f2- || true)"
    export SIM_API_KEY
  fi
fi

if [[ -z "${SIM_API_KEY:-}" ]]; then
  echo "错误: 请设置 SIM_API_KEY，或在 WebService!Input_API_Key 单元格填入密钥" >&2
  exit 1
fi

echo "==> 健康检查"
python3 scripts/excel_ws_cli.py --health-only

echo "==> 完整 headless E2E（读表 → API → 写回 KPI/日志）"
python3 scripts/excel_ws_cli.py --e2e --workbook export/Biomass_PFD_Simulator.xlsx

echo "==> pytest 无头测试"
pytest tests/test_excel_ws_headless.py -v

echo "全部通过"
