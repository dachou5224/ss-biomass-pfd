# 脚本

| 脚本 | 用途 |
|------|------|
| `tune_inci_ta_wet.py` | INCI 湿基 TA 网格扫描；`--compare` 打印全湿基组成 vs DBI |
| `extract_dbi_inci_stream_table.py` | 从 PDF 提取 Case-1 INCI 物流表 → CSV |
| `audit_dbi_inci_element_balance.py` | DBI Case-1 元素衡算审计 |
| `build_simulator_workbook.py` | 生成 Excel Spread Simulator 工作簿 |
| `run_excel_webservice_demo.py` | 启动 Excel/WPS JS 联调用 HTTP 服务（路由在 `src/simulator/api/`） |
| `excel_ws_cli.py` | 无 Excel 进程 WebService 联调 CLI（openpyxl + curl） |
| `run_excel_headless_e2e.sh` | 一键 headless 健康检查 + E2E + pytest |
| `sync_vps.sh` | 本机 rsync 到 VPS 并执行 `deploy/deploy.sh` |
| `build_gibbs_spike_workbook.py` | 生成 Gibbs Spike 测试工作簿 |
| `validate_gibbs_spike_vba.py` | 校验 Gibbs Spike VBA 与 Python 参考 |

```bash
# 湿基 TA 扫描（η 默认读 config）
python3 scripts/tune_inci_ta_wet.py --case Case-1 --top 10

# 当前默认参数全湿基对比
python3 scripts/tune_inci_ta_wet.py --compare --eta1

# 轻量 WebService（纯计算 + Excel 适配）
python3 scripts/run_excel_webservice_demo.py --host 127.0.0.1 --port 8765
curl -sS http://127.0.0.1:8765/health

# Excel WebService 无头 CLI（Agent / CI）
python3 scripts/excel_ws_cli.py --health-only
python3 scripts/excel_ws_cli.py --e2e --write-back
./scripts/run_excel_headless_e2e.sh

# 本地 API curl 示例
curl -sS -X POST http://127.0.0.1:8765/v1/compute/simulate-lite \
  -H "Content-Type: application/json" \
  -d '{"case_id":"Case-1"}'
```
