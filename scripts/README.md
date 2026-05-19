# 脚本

| 脚本 | 用途 |
|------|------|
| `tune_inci_ta_wet.py` | INCI 湿基 TA 网格扫描；`--compare` 打印全湿基组成 vs DBI |
| `extract_dbi_inci_stream_table.py` | 从 PDF 提取 Case-1 INCI 物流表 → CSV |
| `audit_dbi_inci_element_balance.py` | DBI Case-1 元素衡算审计 |
| `build_simulator_workbook.py` | 生成 Excel Spread Simulator 工作簿 |

```bash
# 湿基 TA 扫描（η 默认读 config）
python3 scripts/tune_inci_ta_wet.py --case Case-1 --top 10

# 当前默认参数全湿基对比
python3 scripts/tune_inci_ta_wet.py --compare --eta1
```
