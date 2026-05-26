/*
 * WPS JS / Office JS 轻量联调脚本
 *
 * 1) 读命名区域输入  2) POST /v1/compute/simulate-lite  3) 写 Output_KPI_Table
 * 4) 重要步骤写入 Output_WS_Log_Table（WebService 页，一般用户无需打开 JS 控制台）
 */

const DEMO_BASE_URL =
  (typeof window !== "undefined" && window.DEMO_BASE_URL) ||
  "https://simapi.nice-ai.dev";
const DEMO_LOG_PREFIX = "[WebServiceDemo]";
const LOG_TABLE_NAME = "Output_WS_Log_Table";
const HEALTH_TABLE_NAME = "Output_API_Health_Table";
const LOG_MAX_ROWS = 12;
const LOG_DETAIL_MAX = 220;
const HEALTH_MS_GREEN = 3000;
const HEALTH_MS_YELLOW = 8000;

const HEALTH_PALETTE = {
  green: { bg: "#DCFCE7", fg: "#166534", label: "正常" },
  yellow: { bg: "#FEF9C3", fg: "#854D0E", label: "偏慢" },
  red: { bg: "#FEE2E2", fg: "#991B1B", label: "异常" },
  gray: { bg: "#F1F5F9", fg: "#64748B", label: "待检查" },
};

const HEALTH_ROW = { OVERALL: 0, GET: 1, POST: 2 };

const TEMPLATE_REBUILD_CMD =
  "python3 scripts/build_simulator_workbook.py --case Case-1";

/** 与 src/simulator/workbook_template.py 同步 */
const TEMPLATE_NAMED_RANGE_SPECS = [
  { name: "Input_CaseID", tier: "required", sheet: "Model_Input", hint: "工况标识" },
  { name: "Input_Feed_Table", tier: "required", sheet: "Model_Input", hint: "进料流股表" },
  { name: "Input_Chem_Table", tier: "required", sheet: "Model_Input", hint: "化学参数表" },
  { name: "Output_KPI_Table", tier: "required", sheet: "Model_Output", hint: "KPI 写回表" },
  { name: "Input_API_Key", tier: "recommended", sheet: "WebService", hint: "API 密钥黄格" },
  { name: "Output_WS_Log_Table", tier: "recommended", sheet: "WebService", hint: "运行日志" },
  { name: "Output_API_Health_Table", tier: "recommended", sheet: "WebService", hint: "健康监控" },
];

let _uiBridge = null;
let _uiLogRows = [];

function _nowLocal() {
  try {
    return new Date().toLocaleString();
  } catch (_) {
    return new Date().toISOString();
  }
}

function _fmtDetail(detail) {
  if (detail === undefined || detail === null) return "";
  let msg =
    typeof detail === "object" ? JSON.stringify(detail) : String(detail);
  if (msg.length > LOG_DETAIL_MAX) msg = msg.slice(0, LOG_DETAIL_MAX) + "…";
  return msg;
}

function logStep(step, detail) {
  const row = [_nowLocal(), String(step), _fmtDetail(detail)];
  _uiLogRows.push(row);
  if (detail === undefined) console.log(`${DEMO_LOG_PREFIX} ${step}`);
  else console.log(`${DEMO_LOG_PREFIX} ${step}`, detail);
}

async function beginUiLog(bridge, title) {
  _uiBridge = bridge;
  _uiLogRows = [[_nowLocal(), "—", title || "运行中…"]];
  await flushUiLog();
}

async function flushUiLog() {
  if (!_uiBridge || !_uiLogRows.length) return;
  const rows = _uiLogRows.slice(-LOG_MAX_ROWS);
  while (rows.length < LOG_MAX_ROWS) rows.push(["", "", ""]);
  try {
    await _uiBridge.writeNamedTable(LOG_TABLE_NAME, rows);
  } catch (e) {
    console.log(`${DEMO_LOG_PREFIX} 无法写入 ${LOG_TABLE_NAME}`, e);
  }
}

function classifyHealth(httpStatus, latencyMs, bodyOk) {
  if (!httpStatus || httpStatus === 0) return "red";
  if (httpStatus >= 500) return "red";
  if (httpStatus === 401 || httpStatus === 403) return "yellow";
  if (!bodyOk || httpStatus >= 400) return "red";
  if (latencyMs > HEALTH_MS_YELLOW) return "yellow";
  if (latencyMs > HEALTH_MS_GREEN) return "yellow";
  return "green";
}

function worstHealthLevel(a, b) {
  const rank = { red: 3, yellow: 2, green: 1, gray: 0 };
  return (rank[a] || 0) >= (rank[b] || 0) ? a : b;
}

function healthStatusText(level, extra) {
  const base = HEALTH_PALETTE[level]?.label || "未知";
  return extra ? `${base} · ${extra}` : base;
}

async function updateHealthMonitor(bridge, patch) {
  // patch: { get?: {level, status, reading}, post?: {...}, overall?: {...} }
  if (!bridge || !bridge.writeNamedTable) return;
  let rows;
  try {
    rows = await bridge.getNamedTable(HEALTH_TABLE_NAME);
  } catch (e) {
    console.log(`${DEMO_LOG_PREFIX} 无 ${HEALTH_TABLE_NAME}，跳过健康灯`, e);
    return;
  }
  while (rows.length < 3) rows.push(["", "●", "待检查", "—", ""]);
  const applyRow = (idx, item) => {
    if (!item) return;
    const level = item.level || "gray";
    const pal = HEALTH_PALETTE[level] || HEALTH_PALETTE.gray;
    rows[idx] = [
      rows[idx][0] || "",
      "●",
      item.status || healthStatusText(level, ""),
      item.reading !== undefined ? String(item.reading) : rows[idx][3] || "—",
      item.note !== undefined ? item.note : rows[idx][4] || "",
    ];
    rows[idx]._level = level;
    rows[idx]._pal = pal;
  };
  applyRow(HEALTH_ROW.GET, patch.get);
  applyRow(HEALTH_ROW.POST, patch.post);
  if (patch.overall) {
    applyRow(HEALTH_ROW.OVERALL, patch.overall);
  } else {
    const lv = [rows[HEALTH_ROW.GET], rows[HEALTH_ROW.POST], rows[HEALTH_ROW.OVERALL]]
      .map((r) => r._level)
      .filter(Boolean)
      .reduce((acc, x) => worstHealthLevel(acc, x), "gray");
    applyRow(HEALTH_ROW.OVERALL, {
      level: lv,
      status: healthStatusText(lv),
      reading: patch.get?.reading || rows[HEALTH_ROW.GET][3] || "—",
      note: "联调前先看此灯 · 异常时查下方日志",
    });
  }
  const levels = rows.slice(0, 3).map((r) => r._level || "gray");
  const out = rows.map((r) => r.slice(0, 5));
  try {
    await bridge.writeNamedTable(HEALTH_TABLE_NAME, out);
    if (bridge.paintHealthLamps) {
      await bridge.paintHealthLamps(HEALTH_TABLE_NAME, levels);
    }
  } catch (e) {
    console.log(`${DEMO_LOG_PREFIX} 无法更新健康监控`, e);
  }
}

function formatTemplateFixMessage(result) {
  const lines = [];
  if (result.missingRequired.length) {
    lines.push(
      "缺少必需命名区域：" +
        result.missingRequired.map((s) => s.name).join("、")
    );
    result.missingRequired.slice(0, 4).forEach((s) => {
      lines.push("  · " + s.name + "（" + s.sheet + " · " + s.hint + "）");
    });
  }
  if (result.missingRecommended.length) {
    lines.push(
      "缺少推荐命名区域：" +
        result.missingRecommended.map((s) => s.name).join("、")
    );
  }
  lines.push("修复：运行 " + TEMPLATE_REBUILD_CMD);
  lines.push("重新打开 xlsx 并粘贴最新 export/js/WebServiceDemo.js");
  return lines.join("\n");
}

async function checkWorkbookTemplate(bridge) {
  const missingRequired = [];
  const missingRecommended = [];
  for (const spec of TEMPLATE_NAMED_RANGE_SPECS) {
    const exists = await bridge.hasNamedRange(spec.name);
    if (!exists) {
      if (spec.tier === "required") missingRequired.push(spec);
      else missingRecommended.push(spec);
    }
  }
  return {
    ok: missingRequired.length === 0,
    missingRequired,
    missingRecommended,
  };
}

async function reportTemplateValidation(bridge, result, opts) {
  const options = opts || {};
  const strict = options.strict !== false;
  const summary = result.ok
    ? result.missingRecommended.length
      ? "必需齐全；缺 " + result.missingRecommended.length + " 个推荐区域"
      : "模板检查通过"
    : "缺少 " + result.missingRequired.length + " 个必需命名区域";

  const canLog = await bridge.hasNamedRange(LOG_TABLE_NAME);
  if (options.beginLog && canLog) {
    if (!_uiBridge) await beginUiLog(bridge, "模板检查…");
    logStep("TEMPLATE", summary);
    if (!result.ok || result.missingRecommended.length) {
      logStep("修复", TEMPLATE_REBUILD_CMD);
      if (result.missingRequired.length) {
        logStep("缺少", result.missingRequired.map((s) => s.name).join(", "));
      }
    }
    await flushUiLog();
  }

  if (await bridge.hasNamedRange(HEALTH_TABLE_NAME)) {
    let level = "green";
    if (!result.ok) level = "red";
    else if (result.missingRecommended.length) level = "yellow";
    await updateHealthMonitor(bridge, {
      overall: {
        level,
        status: healthStatusText(level, result.ok ? "模板" : "模板异常"),
        reading: "—",
        note: summary.slice(0, LOG_DETAIL_MAX),
      },
    });
  }

  if (strict && !result.ok) {
    throw new Error(formatTemplateFixMessage(result));
  }
  return result;
}

/** 检查命名区域并写入日志/健康灯（联调前建议先运行） */
async function validateWorkbookTemplate(existingBridge) {
  const bridge = existingBridge || (await resolveExcelBridge());
  const result = await checkWorkbookTemplate(bridge);
  await reportTemplateValidation(bridge, result, { beginLog: true, strict: false });
  if (!result.ok) {
    await bridge.alert("模板检查未通过：见运行日志 TEMPLATE/修复 行");
  } else if (result.missingRecommended.length) {
    await bridge.alert("模板可用但缺少推荐区域：见运行日志");
  } else {
    await bridge.alert("模板检查通过");
  }
  return result;
}

/** 仅刷新健康灯（GET /health，无需 API Key） */
async function refreshApiHealthMonitor(existingBridge) {
  const bridge = existingBridge || (await resolveExcelBridge());
  const url = `${DEMO_BASE_URL}/health`;
  const t0 = Date.now();
  let httpStatus = 0;
  let bodyOk = false;
  let detail = "";
  try {
    const res = await fetch(url);
    httpStatus = res.status;
    const text = await res.text();
    bodyOk = httpStatus === 200 && /"status"\s*:\s*"ok"/i.test(text);
    detail = bodyOk ? "service ok" : text.slice(0, 80);
  } catch (err) {
    detail = err && err.message ? err.message : String(err);
  }
  const ms = Date.now() - t0;
  const level = classifyHealth(httpStatus, ms, bodyOk);
  await updateHealthMonitor(bridge, {
    get: {
      level,
      status: healthStatusText(level, httpStatus ? `HTTP ${httpStatus}` : "网络错误"),
      reading: `${ms} ms`,
      note: detail || "GET /health",
    },
    overall: {
      level,
      status: healthStatusText(level),
      reading: `${ms} ms`,
      note: level === "green" ? "可运行联调命令" : "请先排查网络/服务后再联调",
    },
  });
  return { level, httpStatus, latencyMs: ms, bodyOk };
}

async function runWebServiceLiteDemo() {
  let bridge;
  try {
    bridge = await resolveExcelBridge();
    await beginUiLog(bridge, "开始联调 calculate…");
    logStep("START", DEMO_BASE_URL);

    await reportTemplateValidation(bridge, await checkWorkbookTemplate(bridge), {
      beginLog: true,
      strict: true,
    });
    logStep("TEMPLATE", "必需命名区域齐全");
    await flushUiLog();

    const health = await refreshApiHealthMonitor(bridge).catch(() => null);
    if (health && health.level === "red") {
      logStep("WARN", "API 健康灯为红，仍尝试联调…");
      await flushUiLog();
    }

    const apiKey = await resolveApiKey(bridge);
    if (!apiKey) {
      await updateHealthMonitor(bridge, {
        post: {
          level: "yellow",
          status: healthStatusText("yellow", "缺少密钥"),
          reading: "—",
          note: "填写 Input_API_Key",
        },
      });
      throw new Error("缺少 API Key：请在 WebService 页黄色格填写 Input_API_Key");
    }
    logStep("API Key", "已读取（长度 " + apiKey.length + "）");

    const payload = await buildLitePayload(bridge);
    logStep("读取输入", {
      case_id: payload.case_id,
      feeds: Object.keys(payload.pfd_feeds || {}).length,
    });

    const url = `${DEMO_BASE_URL}/v1/compute/simulate-lite`;
    logStep("POST", url);
    await flushUiLog();

    const t0 = Date.now();
    let data;
    try {
      data = await postJson(url, payload, apiKey, { skipHealthPaint: true });
    } catch (postErr) {
      const msg = postErr && postErr.message ? postErr.message : String(postErr);
      const m = /HTTP (\d+)/.exec(msg);
      const httpStatus = m ? Number(m[1]) : 0;
      const ms = Date.now() - t0;
      const level = classifyHealth(httpStatus, ms, false);
      await updateHealthMonitor(bridge, {
        post: {
          level,
          status: healthStatusText(level, httpStatus ? `HTTP ${httpStatus}` : "失败"),
          reading: `${ms} ms`,
          note: msg.slice(0, LOG_DETAIL_MAX),
        },
      });
      throw postErr;
    }
    const ms = Date.now() - t0;
    const postLevel = classifyHealth(200, ms, data.status === "ok");
    await updateHealthMonitor(bridge, {
      post: {
        level: postLevel,
        status: healthStatusText(postLevel, `status=${data.status || "?"}`),
        reading: `${ms} ms`,
        note: `KPI ${(data.kpi_rows || []).length} 行`,
      },
    });
    logStep("响应", {
      status: data.status,
      kpi_rows: (data.kpi_rows || []).length,
    });

    await writeKpiTable(bridge, data.kpi_rows || []);
    logStep("已写回", "Model_Output · Output_KPI_Table");

    logStep("DONE", "联调成功 status=" + (data.status || "ok"));
    await flushUiLog();
    await bridge.alert("联调成功，请查看本页「运行日志」与 Model_Output KPI");
    return data;
  } catch (err) {
    const msg = err && err.message ? err.message : String(err);
    logStep("ERROR", msg);
    await flushUiLog();
    if (bridge) {
      try {
        await bridge.alert("联调失败：见 WebService 页「运行日志」ERROR 行");
      } catch (_) {}
    }
    throw err;
  }
}

/** 仅测连通性（GET /health，无需 API Key） */
async function runWebServiceHealthCheck() {
  let bridge;
  try {
    bridge = await resolveExcelBridge();
    await beginUiLog(bridge, "健康检查…");
    await reportTemplateValidation(
      bridge,
      await checkWorkbookTemplate(bridge),
      { beginLog: false, strict: false }
    );
    const url = `${DEMO_BASE_URL}/health`;
    logStep("GET", url);
    await flushUiLog();

    const t0 = Date.now();
    const res = await fetch(url);
    const text = await res.text();
    const ms = Date.now() - t0;
    logStep("HTTP", res.status);
    const bodyOk = res.ok && /"status"\s*:\s*"ok"/i.test(text);
    const level = classifyHealth(res.status, ms, bodyOk);
    await updateHealthMonitor(bridge, {
      get: {
        level,
        status: healthStatusText(level, `HTTP ${res.status}`),
        reading: `${ms} ms`,
        note: bodyOk ? "GET /health OK" : text.slice(0, 80),
      },
      overall: {
        level,
        status: healthStatusText(level),
        reading: `${ms} ms`,
        note: level === "green" ? "可运行联调命令" : "排查网络或服务",
      },
    });
    if (!res.ok) {
      logStep("ERROR", text.slice(0, LOG_DETAIL_MAX));
      await flushUiLog();
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    logStep("DONE", `health OK · ${ms} ms · 灯=${level}`);
    await flushUiLog();
    return JSON.parse(text);
  } catch (err) {
    const msg = err && err.message ? err.message : String(err);
    logStep("ERROR", msg);
    await flushUiLog();
    throw err;
  }
}

async function resolveApiKey(bridge) {
  if (typeof window !== "undefined" && window.DEMO_API_KEY) {
    return String(window.DEMO_API_KEY).trim();
  }
  try {
    const v = await bridge.getNamedScalar("Input_API_Key");
    if (v !== null && v !== undefined && String(v).trim()) {
      return String(v).trim();
    }
  } catch (_) {}
  return "";
}

async function buildLitePayload(bridge) {
  const caseId = (await bridge.getNamedScalar("Input_CaseID")) || "Case-1";
  const feedRows = await bridge.getNamedTable("Input_Feed_Table");
  const chemRows = await bridge.getNamedTable("Input_Chem_Table");

  const pfdFeeds = {};
  for (const row of feedRows) {
    const streamId = str(row[0]);
    if (!streamId || streamId.startsWith("Stream")) continue;
    pfdFeeds[streamId] = {
      mass_kg_h: num(row[1]),
      temp_c: num(row[2]),
      pressure_bar: num(row[3]),
    };
  }

  const o2in = { O2: 95.0, N2: 1.75, Ar: 3.25 };
  for (const row of chemRows) {
    const field = str(row[0]);
    const value = num(row[1]);
    if (field === "O2IN O2 mol%") o2in.O2 = value;
    if (field === "O2IN N2 mol%") o2in.N2 = value;
    if (field === "O2IN Ar mol%") o2in.Ar = value;
  }

  return {
    case_id: caseId,
    pfd_feeds: pfdFeeds,
    o2in_composition: o2in,
  };
}

async function writeKpiTable(bridge, kpiRows) {
  const rows = kpiRows.map((r) => [str(r.metric), Number(r.value), str(r.unit)]);
  await bridge.writeNamedTable("Output_KPI_Table", rows);
}

async function postJson(url, payload, apiKey, opts) {
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["X-API-Key"] = apiKey;

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  logStep("HTTP", res.status);
  await flushUiLog();
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

function hexToBgr(hex) {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return r + g * 256 + b * 65536;
}

function paintWpsHealthLamps(tableName, levels) {
  const rng = Application.Range(tableName);
  const target = to2D(rng.Value);
  const lampCol = 1;
  const statusCol = 2;
  for (let r = 0; r < Math.min(levels.length, target.length); r += 1) {
    const pal = HEALTH_PALETTE[levels[r]] || HEALTH_PALETTE.gray;
    const lamp = rng.Offset(r, lampCol);
    const status = rng.Offset(r, statusCol);
    try {
      lamp.Interior.Color = hexToBgr(pal.bg);
      lamp.Font.Color = hexToBgr(pal.fg);
      lamp.Font.Bold = true;
      status.Interior.Color = hexToBgr(pal.bg);
      status.Font.Color = hexToBgr(pal.fg);
      status.Font.Bold = true;
    } catch (_) {}
  }
}

function str(v) {
  if (v === null || v === undefined) return "";
  return String(v).trim();
}

function num(v) {
  const x = Number(v);
  return Number.isFinite(x) ? x : 0;
}

function to2D(value) {
  if (Array.isArray(value)) {
    if (!Array.isArray(value[0])) return [value];
    return value;
  }
  return [[value]];
}

async function resolveExcelBridge() {
  if (typeof Excel !== "undefined" && Excel.run) {
    return createOfficeJsBridge();
  }
  if (typeof Application !== "undefined") {
    return createWpsJsBridge();
  }
  throw new Error("未识别到 WPS JS 或 Office JS 运行时。");
}

function createWpsJsBridge() {
  function getRange(name) {
    return Application.Range(name);
  }

  return {
    async hasNamedRange(name) {
      try {
        getRange(name);
        return true;
      } catch (_) {
        return false;
      }
    },
    async getNamedScalar(name) {
      const v = getRange(name).Value;
      if (Array.isArray(v)) {
        const arr = to2D(v);
        return arr[0] && arr[0][0];
      }
      return v;
    },
    async getNamedTable(name) {
      const v = getRange(name).Value;
      return to2D(v);
    },
    async writeNamedTable(name, rows) {
      const rng = getRange(name);
      const target = to2D(rng.Value);
      const ncol = target[0] ? target[0].length : 3;
      const out = target.map(() => Array(ncol).fill(null));
      for (let i = 0; i < out.length; i += 1) {
        if (i < rows.length) {
          for (let j = 0; j < ncol; j += 1) {
            out[i][j] = j < rows[i].length ? rows[i][j] : null;
          }
        }
      }
      rng.Value = out;
    },
    async alert(msg) {
      Application.StatusBar = msg;
    },
    async paintHealthLamps(tableName, levels) {
      paintWpsHealthLamps(tableName, levels);
    },
  };
}

function createOfficeJsBridge() {
  return {
    async hasNamedRange(name) {
      return Excel.run(async (ctx) => {
        const named = ctx.workbook.names.getItemOrNullObject(name);
        named.load("isNullObject");
        await ctx.sync();
        return !named.isNullObject;
      });
    },
    async getNamedScalar(name) {
      return Excel.run(async (ctx) => {
        const named = ctx.workbook.names.getItem(name);
        const rng = named.getRange();
        rng.load("values");
        await ctx.sync();
        return (rng.values[0] && rng.values[0][0]) || "";
      });
    },
    async getNamedTable(name) {
      return Excel.run(async (ctx) => {
        const named = ctx.workbook.names.getItem(name);
        const rng = named.getRange();
        rng.load("values");
        await ctx.sync();
        return rng.values || [];
      });
    },
    async writeNamedTable(name, rows) {
      return Excel.run(async (ctx) => {
        const named = ctx.workbook.names.getItem(name);
        const rng = named.getRange();
        rng.load(["rowCount", "columnCount"]);
        await ctx.sync();
        const out = [];
        for (let r = 0; r < rng.rowCount; r += 1) {
          const line = [];
          for (let c = 0; c < rng.columnCount; c += 1) {
            line.push(
              r < rows.length && c < rows[r].length ? rows[r][c] : ""
            );
          }
          out.push(line);
        }
        rng.values = out;
        await ctx.sync();
      });
    },
    async alert(msg) {
      return Excel.run(async (ctx) => {
        console.log(msg);
        await ctx.sync();
      });
    },
    async paintHealthLamps(tableName, levels) {
      return Excel.run(async (ctx) => {
        const named = ctx.workbook.names.getItem(tableName);
        const rng = named.getRange();
        rng.load(["rowCount", "columnCount"]);
        await ctx.sync();
        for (let r = 0; r < Math.min(levels.length, rng.rowCount); r += 1) {
          const pal = HEALTH_PALETTE[levels[r]] || HEALTH_PALETTE.gray;
          const lamp = rng.getCell(r, 1);
          const status = rng.getCell(r, 2);
          lamp.format.fill.color = pal.bg;
          lamp.format.font.color = pal.fg;
          lamp.format.font.bold = true;
          status.format.fill.color = pal.bg;
          status.format.font.color = pal.fg;
          status.format.font.bold = true;
        }
        await ctx.sync();
      });
    },
  };
}

if (typeof window !== "undefined") {
  window.runWebServiceLiteDemo = runWebServiceLiteDemo;
  window.runWebServiceHealthCheck = runWebServiceHealthCheck;
  window.refreshApiHealthMonitor = refreshApiHealthMonitor;
  window.validateWorkbookTemplate = validateWorkbookTemplate;
  window.runWebServiceLiteDemoVerbose = runWebServiceLiteDemo;
}
