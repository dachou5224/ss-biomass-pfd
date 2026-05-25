// 复制为 WebServiceDemo.config.local.js（已 gitignore），在加载 WebServiceDemo.js 之前引入。
// 勿将含真实密钥的文件提交到 Git。

window.DEMO_BASE_URL = "https://simapi.nice-ai.dev";
window.DEMO_API_KEY = "从 VPS 获取: ssh nice-ai-LZ 'grep SIM_API_KEY /etc/default/ss-biomass-api'";
