/*
 * WPS JS / Office JS 轻量联调脚本
 *
 * 目标：
 * 1) 从命名区域读取输入（Input_CaseID / Input_Feed_Table / Input_Chem_Table）
 * 2) 调用 Python WebService: /v1/compute/simulate-lite（纯计算）
 * 3) 回填 Output_KPI_Table（metric, value, unit）
 *
 * Python 服务启动：
 *   python3 scripts/run_excel_webservice_demo.py --host 127.0.0.1 --port 8765
 */

const DEMO_BASE_URL =
  (typeof window !== "undefined" && window.DEMO_BASE_URL) ||
  "http://127.0.0.1:8765";
const DEMO_LOG_PREFIX = "[WebServiceDemo]";

function logStep(step, detail) {
  const t = new Date().toISOString();
  if (detail === undefined) console.log(`${DEMO_LOG_PREFIX} ${t} ${step}`);
  else console.log(`${DEMO_LOG_PREFIX} ${t} ${step}`, detail);
}

async function runWebServiceLiteDemo() {
  try {
    logStep("START");
    const bridge = await resolveExcelBridge();
    logStep("Bridge ready");

    const payload = await buildLitePayload(bridge);
    logStep("Payload built", {
      case_id: payload.case_id,
      feed_count: Object.keys(payload.pfd_feeds || {}).length,
      o2in: payload.o2in_composition,
    });

    const url = `${DEMO_BASE_URL}/v1/compute/simulate-lite`;
    logStep("POST request", url);
    const data = await postJson(url, payload);
    logStep("Response received", {
      status: data.status,
      kpi_count: (data.kpi_rows || []).length,
    });

    await writeKpiTable(bridge, data.kpi_rows || []);
    logStep("Output_KPI_Table updated");

    await bridge.alert(`WebService 联调成功，status=${data.status || "unknown"}`);
    logStep("DONE");
    return data;
  } catch (err) {
    logStep("ERROR", err && err.message ? err.message : err);
    throw err;
  }
}

async function buildLitePayload(bridge) {
  const caseId = (await bridge.getNamedScalar("Input_CaseID")) || "Case-1";
  const feedRows = await bridge.getNamedTable("Input_Feed_Table");
  const chemRows = await bridge.getNamedTable("Input_Chem_Table");
  logStep("Named ranges loaded", {
    case_id: caseId,
    feed_rows: (feedRows || []).length,
    chem_rows: (chemRows || []).length,
  });

  const pfdFeeds = {};
  for (const row of feedRows) {
    const streamId = str(row[0]);
    if (!streamId) continue;
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
  logStep("KPI rows written", rows.length);
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  logStep("HTTP status", res.status);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
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
      const out = target.map(() => [null, null, null]);
      for (let i = 0; i < out.length; i += 1) {
        if (i < rows.length) out[i] = [rows[i][0], rows[i][1], rows[i][2]];
      }
      rng.Value = out;
    },
    async alert(msg) {
      Application.StatusBar = msg;
    },
  };
}

function createOfficeJsBridge() {
  return {
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
          if (r < rows.length) out.push([rows[r][0], rows[r][1], rows[r][2]]);
          else out.push(["", "", ""]);
        }
        rng.values = out;
        await ctx.sync();
      });
    },
    async alert(msg) {
      return Excel.run(async (ctx) => {
        const sheet = ctx.workbook.worksheets.getActiveWorksheet();
        const cell = sheet.getRange("A1");
        cell.load("address");
        await ctx.sync();
        // Office JS 无同步 MsgBox；写入状态提示到 A1 注释场景可按需扩展
        console.log(msg, cell.address);
      });
    },
  };
}

// 便于控制台直接调用
if (typeof window !== "undefined") {
  window.runWebServiceLiteDemo = runWebServiceLiteDemo;
  window.runWebServiceLiteDemoVerbose = runWebServiceLiteDemo;
}
