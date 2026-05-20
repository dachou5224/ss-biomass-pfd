# 本地参考数据（勿提交 Git）

本目录存放**从 DBI / 附录 PDF 提取**的参考物流、组分与 stream table 等数据。  
这些文件**不得**加入 Git 或 push 到远程仓库（已在仓库根 `.gitignore` 中排除）。

## 源文件

将 PDF 放在 `doc/`（该目录下的 `*.pdf` 同样不纳入 Git），例如：

- `doc/TR5_APPENDIX 02_PFD & Stream Table_Unit 13_INCI Gasifier_DBI.pdf`

## 本地生成

```bash
# Case-1 全流股 stream table（p2–p3）
python3 scripts/extract_dbi_inci_stream_table.py

# 其它 CSV（inci_streams、质量衡算、进料组分）需从 PDF 整理或沿用既有提取流程后写入本目录
```

## 常见文件名

| 文件 | 说明 |
|------|------|
| `dbi_inci_stream_table_case1.csv` | 全量 stream table 长表 |
| `inci_streams.csv` | 13PGI-1 湿基 mol/mol 全组分 |
| `dbi_inci_mass_balance_case1.csv` | INCI 边界质量衡算 |
| `dbi_inci_inlet_composition_case1.csv` | 边界进料组分 |
| `dbi_rgpox_mass_balance_case1.csv` | RGPOX 边界质量衡算（15PGI-1/15OG1） |
| `rgpox_streams.csv` | 15PGR-2 湿基 mol/mol 全组分 |

克隆仓库后若缺少上述文件，对标相关测试会自动跳过；本地有 PDF 时按上表生成即可。

RGPOX 进料门禁：`python3 scripts/audit_rgpox_inlet.py --case Case-1`（TA 调参前须通过）。
