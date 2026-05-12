const LOCAL_AGENT_BASE = "http://127.0.0.1:8765";
const LOCAL_AGENT_FALLBACK_BASE = "http://127.0.0.1:8000";
const DEFAULT_LOCAL_BACKEND_BASE = "http://127.0.0.1:8000";
const API_MODE_KEY = "aiLabApiMode";
const SERVER_API_BASE_KEY = "aiLabServerApiBase";

function inferServerApiBase() {
  const params = new URLSearchParams(window.location.search);
  const configured = params.get("apiBase") || window.localStorage.getItem(SERVER_API_BASE_KEY) || window.SERVER_API_BASE;
  if (configured) return configured.replace(/\/$/, "");
  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return DEFAULT_LOCAL_BACKEND_BASE;
}

const serverApiBase = inferServerApiBase();
let apiMode = window.localStorage.getItem(API_MODE_KEY) || "server";
let apiBase = apiMode === "local" ? LOCAL_AGENT_BASE : serverApiBase;

const fileInput = document.querySelector("#fileInput");
const fileLabel = document.querySelector("#fileLabel");
const dropZone = document.querySelector(".drop-zone");
const result = document.querySelector("#result");
const progressRing = document.querySelector("#progressRing");
const progressValue = document.querySelector("#progressValue");
const progressStep = document.querySelector("#progressStep");
const messages = document.querySelector("#messages");
const chatInput = document.querySelector("#chatInput");
const browserHint = document.querySelector("#browserHint");
const detectedBrowser = document.querySelector("#detectedBrowser");
const cdpUrl = document.querySelector("#cdpUrl");
const browserConnected = document.querySelector("#browserConnected");
const browserProfile = document.querySelector("#browserProfile");
const browserExtension = document.querySelector("#browserExtension");
const modelMenuButton = document.querySelector("#modelMenuButton");
const modelMenuList = document.querySelector("#modelMenuList");
const aiNameInput = document.querySelector("#aiNameInput");
const aiNameToast = document.querySelector("#aiNameToast");
const stopRefreshButton = document.querySelector("#stopRefreshButton");
const serverModeButton = document.querySelector("#serverModeButton");
const localModeButton = document.querySelector("#localModeButton");
const agentCheckButton = document.querySelector("#agentCheckButton");
const agentDownloadLink = document.querySelector("#agentDownloadLink");
const agentStartLink = document.querySelector("#agentStartLink");
const agentStatus = document.querySelector("#agentStatus");

const buttons = {
  refresh: document.querySelector("#refreshButton"),
  browserStatus: document.querySelector("#browserStatusButton"),
  upload: document.querySelector("#uploadButton"),
  startBrowser: document.querySelector("#startBrowserButton"),
  chatgpt: document.querySelector("#chatgptButton"),
  validate: document.querySelector("#validateButton"),
  train: document.querySelector("#trainButton"),
  send: document.querySelector("#sendButton"),
};

let pipelineRunning = false;
let aiNameToastTimer = null;
let pipelineAbortController = null;
let pipelineCancelled = false;

function show(data) {
  result.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

function setAgentStatus(text, state = "") {
  if (!agentStatus) return;
  agentStatus.textContent = text;
  agentStatus.className = `agent-status ${state}`.trim();
}

function updateApiModeUi() {
  if (serverModeButton) {
    serverModeButton.classList.toggle("active", apiMode === "server");
  }
  if (localModeButton) {
    localModeButton.classList.toggle("active", apiMode === "local");
  }
  const label = apiMode === "local" ? "本地通信" : "服务器端";
  setAgentStatus(`${label}: ${apiBase}`, apiMode === "local" ? "local" : "server");
}

function setApiMode(mode) {
  apiMode = mode === "local" ? "local" : "server";
  apiBase = apiMode === "local" ? LOCAL_AGENT_BASE : serverApiBase;
  window.localStorage.setItem(API_MODE_KEY, apiMode);
  updateApiModeUi();
}

async function probeApiBase(base) {
  const response = await fetch(`${base}/health`, {
    method: "GET",
    cache: "no-store",
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok || data.ok !== true) {
    throw new Error(data.detail || data.message || `HTTP ${response.status}`);
  }
  return data;
}

async function switchToLocalAgent() {
  setAgentStatus("正在检测本地 Local Agent...", "checking");
  const localCandidates = [LOCAL_AGENT_BASE, LOCAL_AGENT_FALLBACK_BASE];
  let lastError = null;
  for (const candidate of localCandidates) {
    try {
      const data = await probeApiBase(candidate);
      apiMode = "local";
      apiBase = candidate;
      window.localStorage.setItem(API_MODE_KEY, apiMode);
      updateApiModeUi();
      setAgentStatus(data.message || "本地通信已连接", "ok");
      await refreshStatus();
      await refreshBrowserStatus();
      await refreshModelMenu();
      return true;
    } catch (error) {
      lastError = error;
    }
  }

  setApiMode("server");
  setAgentStatus(`未检测到 Local Agent: ${lastError?.message || "连接失败"}`, "warn");
  return false;
}

async function switchToServerApi() {
  setApiMode("server");
  setAgentStatus("正在检测服务器端...", "checking");
  try {
    const data = await probeApiBase(serverApiBase);
    setAgentStatus(data.message || "服务器端已连接", "ok");
    await refreshStatus();
    await refreshBrowserStatus();
    await refreshModelMenu();
  } catch (error) {
    setAgentStatus(`服务器端检测失败: ${error.message}`, "warn");
  }
}

function resetTrainingUi() {
  pipelineCancelled = true;
  pipelineRunning = false;
  if (pipelineAbortController) {
    pipelineAbortController.abort();
    pipelineAbortController = null;
  }
  fileInput.disabled = false;
  fileInput.value = "";
  if (aiNameInput) {
    aiNameInput.value = "";
    aiNameInput.placeholder = "1.请点击这里为AI命名";
  }
  fileLabel.textContent = "2.点击这里上传txt文件";
  setProgress(0, "等待上传文件");
  show("等待操作...");
  stopOverlay();
}

function showAiNameToast() {
  if (!aiNameToast) return;
  window.clearTimeout(aiNameToastTimer);
  aiNameToast.classList.remove("show");
  void aiNameToast.offsetWidth;
  aiNameToast.classList.add("show");
  aiNameToastTimer = window.setTimeout(() => {
    aiNameToast.classList.remove("show");
  }, 2000);
}

function setProgress(percent, label) {
  const safePercent = Math.max(0, Math.min(100, percent));
  if (progressRing) {
    progressRing.style.setProperty("--progress", `${safePercent}%`);
  }
  if (progressValue) {
    progressValue.textContent = `${safePercent}%`;
  }
  if (progressStep) {
    progressStep.textContent = label;
  }
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function detectBrowser() {
  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes("edg/")) return "msedge";
  if (ua.includes("chrome/") || ua.includes("crios/")) return "chrome";
  return "msedge";
}

function browserLabel(browser) {
  if (browser === "chrome") return "Google Chrome";
  if (browser === "msedge") return "Microsoft Edge";
  return browser;
}

function parseColor(value) {
  const raw = value.trim();
  if (raw.startsWith("#") && raw.length === 7) {
    return {
      r: parseInt(raw.slice(1, 3), 16),
      g: parseInt(raw.slice(3, 5), 16),
      b: parseInt(raw.slice(5, 7), 16),
      a: 1,
    };
  }
  const match = raw.match(/rgba?\(([^)]+)\)/i);
  if (!match) return null;
  const parts = match[1].split(",").map((part) => part.trim());
  return {
    r: Number(parts[0]),
    g: Number(parts[1]),
    b: Number(parts[2]),
    a: parts[3] === undefined ? 1 : Number(parts[3]),
  };
}

function blendColor(top, bottom) {
  const alpha = Math.max(0, Math.min(1, top.a ?? 1));
  return {
    r: Math.round(top.r * alpha + bottom.r * (1 - alpha)),
    g: Math.round(top.g * alpha + bottom.g * (1 - alpha)),
    b: Math.round(top.b * alpha + bottom.b * (1 - alpha)),
    a: 1,
  };
}

function colorToHex(color) {
  const channel = (value) => Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, "0");
  return `#${channel(color.r)}${channel(color.g)}${channel(color.b)}`;
}

function interpolateColor(stops, percent) {
  const safePercent = Math.max(0, Math.min(100, percent));
  let left = stops[0];
  let right = stops[stops.length - 1];
  for (let index = 0; index < stops.length - 1; index += 1) {
    if (safePercent >= stops[index].at && safePercent <= stops[index + 1].at) {
      left = stops[index];
      right = stops[index + 1];
      break;
    }
  }
  const span = Math.max(1, right.at - left.at);
  const t = (safePercent - left.at) / span;
  return {
    r: left.r + (right.r - left.r) * t,
    g: left.g + (right.g - left.g) * t,
    b: left.b + (right.b - left.b) * t,
    a: 1,
  };
}

function treeBackgroundColorAt(viewportY) {
  const percentFromBottom = 100 - (Math.max(0, Math.min(window.innerHeight, viewportY)) / window.innerHeight) * 100;
  return interpolateColor([
    { at: 0, r: 49, g: 84, b: 58 },
    { at: 25, r: 82, g: 116, b: 81 },
    { at: 52, r: 129, g: 148, b: 109 },
    { at: 77, r: 195, g: 205, b: 177 },
    { at: 100, r: 238, g: 244, b: 234 },
  ], percentFromBottom);
}

function overlayColorForRect(rect) {
  const panelColor = parseColor(getComputedStyle(document.body).getPropertyValue("--panel")) || { r: 215, g: 223, b: 205, a: 1 };
  return colorToHex(panelColor);
}

function browserWindowParams(browser) {
  const screenLeft = window.screen.availLeft || 0;
  const screenTop = window.screen.availTop || 0;
  const screenWidth = window.screen.availWidth || window.screen.width;
  const screenHeight = window.screen.availHeight || window.screen.height;
  const previewRect = document.querySelector(".browser-preview")?.getBoundingClientRect();
  const panelRect = document.querySelector("#trainingView .panel")?.getBoundingClientRect();
  const viewportLeft = window.screenX + Math.max(0, window.outerWidth - window.innerWidth);
  const viewportTop = window.screenY + Math.max(0, window.outerHeight - window.innerHeight);
  const fallbackWidth = Math.round(screenWidth * 3 / 5);
  const fallbackHeight = Math.round(screenHeight * 4 / 5);
  const scale = 0.9;
  const baseWidth = previewRect?.width || fallbackWidth;
  const width = Math.round(baseWidth * scale);
  const top = panelRect?.top ?? previewRect?.top ?? 0;
  const bottom = previewRect?.bottom ?? top + fallbackHeight;
  const baseHeight = bottom - top;
  const height = Math.round(baseHeight * scale);
  const rawX = previewRect ? viewportLeft + previewRect.left + (baseWidth - width) / 2 : screenLeft + screenWidth - width;
  const rawY = previewRect ? viewportTop + top + (baseHeight - height) / 2 : screenTop;
  const x = Math.round(Math.max(screenLeft, Math.min(rawX, screenLeft + screenWidth - width)));
  const y = Math.round(Math.max(screenTop, Math.min(rawY, screenTop + screenHeight - height)));
  return new URLSearchParams({
    browser,
    width: String(width),
    height: String(height),
    x: String(x),
    y: String(y),
    bg: overlayColorForRect(previewRect),
  });
}

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, options);
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (error) {
    throw new Error(`接口返回不是 JSON: ${text.slice(0, 120)}`);
  }
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data;
}

function stopOverlay() {
  const url = `${apiBase}/browser/overlay/stop`;
  if (navigator.sendBeacon) {
    navigator.sendBeacon(url, new Blob([], { type: "text/plain" }));
    return;
  }
  fetch(url, { method: "POST", keepalive: true }).catch(() => {});
}

async function updateOverlayText(text) {
  const params = browserWindowParams(detectBrowser());
  params.set("text", text);
  return request(`/browser/overlay/update?${params.toString()}`, { method: "POST" });
}

async function refreshStatus() {
  try {
    return await request("/status");
  } catch (error) {
    return null;
  }
}

async function refreshBrowserStatus() {
  const browser = detectBrowser();
  if (!detectedBrowser || !cdpUrl || !browserConnected || !browserProfile || !browserExtension || !browserHint) {
    return null;
  }
  detectedBrowser.textContent = browserLabel(browser);

  try {
    const data = await request(`/browser/status?browser=${encodeURIComponent(browser)}`);
    cdpUrl.textContent = data.cdp_url;
    browserConnected.textContent = data.connected ? "已连接" : "未连接";
    browserConnected.className = data.connected ? "ok" : "warn";
    browserProfile.textContent = data.profile_path;
    browserExtension.textContent = data.extension_path || "-";
    browserHint.textContent = data.message;
    return data;
  } catch (error) {
    browserConnected.textContent = "检查失败";
    browserConnected.className = "warn";
    browserHint.textContent = error.message;
    return null;
  }
}

function renderModelMenu(models) {
  modelMenuList.innerHTML = "";
  if (!models.length) {
    const emptyButton = document.createElement("button");
    emptyButton.type = "button";
    emptyButton.disabled = true;
    emptyButton.textContent = "无";
    modelMenuList.appendChild(emptyButton);
    return;
  }

  models.forEach((model) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.aiName = model.name;
    button.textContent = model.name;
    modelMenuList.appendChild(button);
  });
}

async function refreshModelMenu() {
  try {
    const data = await request("/models");
    renderModelMenu(data.models || []);
  } catch (error) {
    modelMenuList.innerHTML = "";
    const errorButton = document.createElement("button");
    errorButton.type = "button";
    errorButton.disabled = true;
    errorButton.textContent = "无法读取模型";
    modelMenuList.appendChild(errorButton);
  }
}

async function runStep(label, fn) {
  show(`${label} 正在执行...`);
  try {
    const data = await fn();
    show(data);
    await refreshStatus();
  } catch (error) {
    show(`${label} 失败: ${error.message}`);
    await refreshStatus();
  }
}

async function runTrainingPipeline(file) {
  if (pipelineRunning) return;
  const aiName = aiNameInput?.value.trim() || "";
  if (!aiName) {
    showAiNameToast();
    fileInput.value = "";
    return;
  }
  pipelineRunning = true;
  pipelineCancelled = false;
  pipelineAbortController = new AbortController();
  const requestOptions = (options = {}) => ({ ...options, signal: pipelineAbortController.signal });
  fileInput.disabled = true;

  const browser = detectBrowser();
  const encodedAiName = encodeURIComponent(aiName);
  const formData = new FormData();
  formData.append("file", file);
  formData.append("ai_name", aiName);

  try {
    setProgress(5, "正在上传 txt 文件");
    show("正在上传文件并生成 prompt...");
    const uploadData = await request("/upload", requestOptions({ method: "POST", body: formData }));
    if (pipelineCancelled) return;
    const datasetFilename = uploadData.dataset_path ? uploadData.dataset_path.split(/[\\/]/).pop() : `${aiName}.jsonl`;
    show(uploadData);

    setProgress(20, "正在启动调试浏览器");
    const params = browserWindowParams(browser);
    const browserData = await request(`/browser/start?${params.toString()}`, requestOptions({ method: "POST" }));
    if (pipelineCancelled) return;
    show(browserData);

    setProgress(35, `等待 ChatGPT 登录完成并生成 ${datasetFilename}`);
    show(`请在新打开的 ChatGPT 浏览器窗口完成登录和个人信息登录。完成后脚本会继续生成 ${datasetFilename}。`);
    await updateOverlayText("正在处理，请稍候");
    if (pipelineCancelled) return;
    const chatgptData = await request(`/chatgpt?browser=${encodeURIComponent(browser)}&ai_name=${encodedAiName}`, requestOptions({ method: "POST" }));
    if (pipelineCancelled) return;
    show(chatgptData);

    setProgress(65, `正在校验 ${datasetFilename} 并生成 preview`);
    const validateData = await request(`/validate?ai_name=${encodedAiName}`, requestOptions({ method: "POST" }));
    if (pipelineCancelled) return;
    show(validateData);

    setProgress(82, "正在启动 LoRA 微调");
    const trainData = await request(`/train?ai_name=${encodedAiName}`, requestOptions({ method: "POST" }));
    if (pipelineCancelled) return;
    show(trainData);

    setProgress(95, "正在加载训练后的模型");
    const loadData = await request(`/load?ai_name=${encodedAiName}`, requestOptions({ method: "POST" }));
    if (pipelineCancelled) return;
    show(loadData);
    await refreshModelMenu();

    setProgress(100, "流水线完成，可以开始对话");
    await updateOverlayText("已完成");
    window.setTimeout(stopOverlay, 1500);
  } catch (error) {
    if (pipelineCancelled || error.name === "AbortError") {
      return;
    }
    setProgress(0, "流水线失败，请查看下方终端");
    show(`流水线失败: ${error.message}`);
    stopOverlay();
  } finally {
    if (!pipelineCancelled) {
      pipelineRunning = false;
      fileInput.disabled = false;
      pipelineAbortController = null;
      await refreshStatus();
    }
  }
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tab;
    document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab));
    document.querySelector("#chatView").classList.toggle("active", target === "chat");
    document.querySelector("#trainingView").classList.toggle("active", target === "training");
  });
});

modelMenuButton.addEventListener("click", () => {
  refreshModelMenu();
  modelMenuList.classList.toggle("open");
});

modelMenuList.querySelectorAll("button").forEach((button) => {
  button.addEventListener("click", () => {
    const modelType = button.dataset.model;
    modelMenuButton.textContent = button.textContent;
    modelMenuList.classList.remove("open");
    const aiName = aiNameInput?.value.trim() || "";
    const query = aiName ? `?ai_name=${encodeURIComponent(aiName)}` : "";
    runStep(modelType === "personal" ? "加载个性化AI" : "加载毛泽东AI", () => request(`/load${query}`, { method: "POST" }));
  });
});

modelMenuList.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button || button.disabled) return;
  const aiName = button.dataset.aiName;
  if (!aiName) return;
  modelMenuButton.textContent = button.textContent;
  modelMenuList.classList.remove("open");
  const query = `?ai_name=${encodeURIComponent(aiName)}`;
  runStep(`加载 ${button.textContent}`, () => request(`/load${query}`, { method: "POST" }));
});

if (aiNameInput) {
  aiNameInput.addEventListener("focus", () => {
    aiNameInput.placeholder = "";
  });
  aiNameInput.addEventListener("blur", () => {
    if (!aiNameInput.value.trim()) {
      aiNameInput.placeholder = "1.请点击这里为AI命名";
    }
  });
}

document.addEventListener("click", (event) => {
  if (!event.target.closest(".model-menu")) {
    modelMenuList.classList.remove("open");
  }
});

window.addEventListener("pagehide", stopOverlay);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    stopOverlay();
  }
});

if (dropZone) {
  dropZone.addEventListener("click", (event) => {
    if (!aiNameInput?.value.trim()) {
      event.preventDefault();
      event.stopPropagation();
      showAiNameToast();
    }
  });
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) {
    fileLabel.textContent = "2.点击这里上传txt文件";
    setProgress(0, "等待上传文件");
    show("等待操作...");
    return;
  }
  fileLabel.textContent = `${file.name} (${formatBytes(file.size)})`;
  show(`已选择文件:
名称: ${file.name}
大小: ${formatBytes(file.size)}
类型: ${file.type || "未知"}`);
  runTrainingPipeline(file);
});

if (buttons.refresh) {
  buttons.refresh.addEventListener("click", refreshStatus);
}
if (buttons.browserStatus) {
  buttons.browserStatus.addEventListener("click", refreshBrowserStatus);
}

if (stopRefreshButton) {
  stopRefreshButton.addEventListener("click", () => {
    resetTrainingUi();
  });
}

if (serverModeButton) {
  serverModeButton.addEventListener("click", switchToServerApi);
}

if (localModeButton) {
  localModeButton.addEventListener("click", switchToLocalAgent);
}

if (agentCheckButton) {
  agentCheckButton.addEventListener("click", () => {
    if (apiMode === "local") {
      switchToLocalAgent();
    } else {
      switchToServerApi();
    }
  });
}

if (agentDownloadLink && window.location.protocol === "file:") {
  agentDownloadLink.title = "把前端放到 HTTP 服务后，这个链接会下载 downloads/LocalAgentSetup.exe";
}

if (agentStartLink) {
  agentStartLink.addEventListener("click", () => {
    setAgentStatus("已请求启动 Local Agent，请确认浏览器弹窗。", "checking");
    window.setTimeout(switchToLocalAgent, 1800);
  });
}

function addMessage(role, text) {
  const item = document.createElement("div");
  item.className = `message ${role}`;
  item.textContent = text;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
}

buttons.send.addEventListener("click", async () => {
  const message = chatInput.value.trim();
  if (!message) return;
  chatInput.value = "";
  addMessage("user", message);
  try {
    const data = await request("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    addMessage("assistant", data.reply);
  } catch (error) {
    addMessage("assistant", `失败: ${error.message}`);
  }
});

chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    buttons.send.click();
  }
});

updateApiModeUi();
if (apiMode === "local") {
  switchToLocalAgent();
} else {
  switchToServerApi();
}
