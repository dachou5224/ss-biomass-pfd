/**
 * WPS 内嵌启动器（随 xlsm 分发，勿删）
 * 完整联调脚本在隐藏工作表 __MacroSrc__ 的 A1，由构建脚本写入。
 */
function __ssReadMacroSource() {
  var ws = Application.Worksheets.Item("__MacroSrc__");
  var v = ws.Range("A1").Value2;
  if (v == null || v === "") {
    throw new Error(
      "工作簿缺少联调脚本，请向管理员索取最新 Biomass_PFD_Simulator_WPS.xlsm"
    );
  }
  return String(v);
}

function __ssEnsureLoaded() {
  if (globalThis.__ss_macro_loaded__) return;
  var src = __ssReadMacroSource();
  eval(src);
  if (!globalThis.__ss_exports__) {
    throw new Error("联调脚本未正确安装（无 __ss_exports__），请联系管理员");
  }
  globalThis.__ss_macro_loaded__ = true;
}

async function validateWorkbookTemplate(existingBridge) {
  __ssEnsureLoaded();
  return await globalThis.__ss_exports__.validateWorkbookTemplate(existingBridge);
}

async function refreshApiHealthMonitor(existingBridge) {
  __ssEnsureLoaded();
  return await globalThis.__ss_exports__.refreshApiHealthMonitor(existingBridge);
}

async function runWebServiceHealthCheck() {
  __ssEnsureLoaded();
  return await globalThis.__ss_exports__.runWebServiceHealthCheck();
}

async function runWebServiceLiteDemo() {
  __ssEnsureLoaded();
  return await globalThis.__ss_exports__.runWebServiceLiteDemo();
}
