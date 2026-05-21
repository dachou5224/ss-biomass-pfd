# Excel WebService API Contract (v1)

本文档用于冻结当前 Excel 联调 API 字段约定，并明确前后端边界：

- `/v1/compute/*`：**纯计算契约**（与 Excel 布局无关）
- `/v1/demo/*`：**Excel 适配契约**（仅兼容层，允许命名区域映射）

## 1. Health

### `GET /health`

Response:

```json
{
  "status": "ok",
  "service": "excel-webservice-demo"
}
```

## 2. Pure Compute Contract (UI-agnostic)

### `POST /v1/compute/simulate-lite`

Request (minimal example):

```json
{
  "case_id": "Case-1",
  "pfd_feeds": {
    "Biomass": { "mass_kg_h": 4000, "temp_c": 20, "pressure_bar": 16.5 },
    "O2IN": { "mass_kg_h": 1343, "temp_c": 20, "pressure_bar": 16.5 }
  },
  "o2in_composition": { "O2": 95, "N2": 1.75, "Ar": 3.25 }
}
```

Response:

```json
{
  "status": "ok",
  "kpi_rows": [
    { "metric": "TOTAL_FEED_KG_H", "value": 8293.5, "unit": "kg/h" }
  ],
  "checks": {
    "total_feed_kg_h": 8293.5,
    "o2in_sum_mol_pct": 100.0,
    "o2in_is_100_pct": true,
    "negative_feed_count": 0
  }
}
```

约束：

1. 不返回任何命名区域、单元格地址、工作表名称等 UI 信息。
2. 字段语义稳定；`/v1` 下只做向后兼容扩展。

## 3. Excel Adapter Contract (Compatibility Layer)

### `POST /v1/demo/simulate-lite`

Response 在纯计算结果基础上增加 Excel 映射结构：

```json
{
  "mode": "output-pack",
  "status": "ok",
  "kpi_rows": [{ "metric": "TOTAL_FEED_KG_H", "value": 8293.5, "unit": "kg/h" }],
  "named_ranges": {
    "Output_Demo_KPI": [["TOTAL_FEED_KG_H", 8293.5, "kg/h"]]
  },
  "checks": {
    "o2in_is_100_pct": true,
    "negative_feed_count": 0
  }
}
```

### `POST /v1/demo/input-read`

用途：返回输入表/规格表/化学表，便于 Excel 端做输入审阅。

### `POST /v1/demo/output-pack.tsv`

用途：返回 TSV 文本，兼容需要纯文本粘贴/解析的场景。

## 4. Frontend/Backend Boundary

1. 后端只关心输入语义与计算结果，不关心 Excel 布局。
2. Excel 命名区域映射由 JS 客户端负责（`export/js/WebServiceDemo.js`）。
3. 未来 UI 布局调整不应触发后端计算接口变更。

## 5. Security & Runtime Config (Phase C)

1. 可选 API Key：设置 `SIM_API_KEY`（或启动参数 `--api-key`）后，`POST` 请求必须携带 Header `X-API-Key`。
2. CORS 白名单：设置 `SIM_API_ALLOWED_ORIGINS`（逗号分隔）或 `--allowed-origins`，例如：
   - `SIM_API_ALLOWED_ORIGINS=https://nice-ai.dev,https://app.nice-ai.dev`
3. 请求日志：服务按请求输出结构化日志字段（`method/path/status/latency_ms/request_id`）。
