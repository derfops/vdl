const modes = {
  none: "Sem VPN",
  cyberghost: "CyberGhost",
  windscribe: "Windscribe",
};

const pageMeta = {
  library: {
    eyebrow: "VDL Studio",
    title: "Biblioteca",
    subtitle: "Arquivos baixados, artefatos e contexto gerado.",
    primary: "Novo lote",
    secondary: "Sincronizar",
  },
  batch: {
    eyebrow: "Criação",
    title: "Novo lote",
    subtitle: "Downloads por URL e transcrição de arquivos locais.",
    primary: "Validar",
    secondary: "Limpar",
  },
  queue: {
    eyebrow: "Runtime",
    title: "Fila",
    subtitle: "Servidor VDL, VPN e execução em andamento.",
    primary: "Iniciar",
    secondary: "Testar IP",
  },
  jobs: {
    eyebrow: "Histórico",
    title: "Jobs",
    subtitle: "Lotes criados, status e logs do runtime selecionado.",
    primary: "Atualizar",
    secondary: "Logs",
  },
  credentials: {
    eyebrow: "Segurança",
    title: "Credenciais",
    subtitle: "Cookies, tokens e chaves ficam fora do armazenamento da UI.",
    primary: "Novo lote",
    secondary: "Configurações",
  },
  settings: {
    eyebrow: "Preferências",
    title: "Configurações",
    subtitle: "Runtime padrão, VPN e documentação operacional.",
    primary: "Iniciar runtime",
    secondary: "HOWTO-VPN",
  },
};

const batchOperationMeta = {
  download: {
    eyebrow: "Downloads",
    title: "Downloads",
    subtitle: "Baixe vídeos por URL com cookie obrigatório e opções de processamento.",
    primary: "Validar lote",
    secondary: "Limpar",
  },
  local: {
    eyebrow: "Transcrição",
    title: "Transcrições",
    subtitle: "Transcreva arquivos que já estão no servidor e gere contexto quando necessário.",
    primary: "Validar pasta",
    secondary: "Limpar",
  },
};

const sidebarPreference = localStorage.getItem("vdl.sidebarCollapsed");

const state = {
  selectedMode: localStorage.getItem("vdl.mode") || "none",
  selectedPanel: "library",
  operationMode: localStorage.getItem("vdl.operation") || "download",
  executionMode: "sequential",
  transcriptionMode: "none",
  localProcessingMode: "transcribe",
  runtimeStatus: null,
  batches: [],
  selectedJobId: null,
  currentFilePath: "/data",
  fileDialogTarget: "destination",
  credentialValidated: false,
  credentialValue: "",
  previewUrl: "",
  sidebarCollapsed:
    sidebarPreference === null ? window.matchMedia("(max-width: 1040px)").matches : sidebarPreference === "true",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const fileDialogTargets = {
  destination: {
    eyebrow: "Download",
    title: "Escolher destino",
  },
  localSource: {
    eyebrow: "Transcrição",
    title: "Escolher pasta de entrada",
  },
  localDestination: {
    eyebrow: "Transcrição",
    title: "Escolher destino dos artefatos",
  },
};

function getToken() {
  return localStorage.getItem("vdl.token") || "";
}

function setToken(token) {
  if (token) localStorage.setItem("vdl.token", token);
  else localStorage.removeItem("vdl.token");
}

async function api(path, options = {}) {
  const token = getToken();
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) handleUnauthorized();
    const message = data.detail
      ? typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail)
      : response.statusText;
    throw new Error(message);
  }
  return data;
}

function setText(selector, value) {
  const element = $(selector);
  if (element) element.textContent = value;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => {
    return {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char];
  });
}

function setSidebarCollapsed(collapsed, persist = false) {
  state.sidebarCollapsed = Boolean(collapsed);
  $(".app-shell")?.classList.toggle("sidebar-collapsed", state.sidebarCollapsed);

  const toggle = $("#sidebarToggle");
  if (!toggle) return;

  const action = state.sidebarCollapsed ? "Expandir" : "Recolher";
  toggle.setAttribute("aria-expanded", String(!state.sidebarCollapsed));
  toggle.setAttribute("aria-label", `${action} menu lateral`);
  toggle.title = `${action} menu`;

  if (persist) {
    localStorage.setItem("vdl.sidebarCollapsed", String(state.sidebarCollapsed));
  }
}

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function allJobs() {
  return state.batches.flatMap((batch) => batch.jobs.map((job) => ({ ...job, batch })));
}

function parseUrls(value) {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function countUrls(value) {
  const urls = parseUrls(value);
  const unique = new Set(urls);
  return {
    total: urls.length,
    valid: urls.filter((url) => /^https?:\/\//.test(url)).length,
    duplicates: urls.length - unique.size,
  };
}

function statusLabel(status) {
  return {
    queued: "Aguardando",
    running: "Rodando",
    succeeded: "Concluído",
    failed: "Falhou",
    blocked: "Bloqueado",
  }[status] || status;
}

function statusClass(status) {
  if (status === "succeeded") return "ready";
  if (status === "running") return "ready";
  if (status === "failed" || status === "blocked") return "error";
  if (status === "queued") return "warn";
  return "off";
}

function processingLabel(mode) {
  return {
    download: "Download",
    transcribe: "Transcrição",
    context: "Transcrição + contexto",
    unified: "OpenAI",
  }[mode] || mode;
}

function jobInputLabel(job) {
  return job.job_type === "local" ? job.input_path || job.url : `${job.destination}/${job.filename}`;
}

function primaryFilePath(job) {
  if (!job) return "";
  if (job.job_type === "local") return job.input_path || job.url || "";
  const destination = String(job.destination || "/data").replace(/\/+$/, "");
  const filename = String(job.filename || "").replace(/^\/+/, "");
  return filename ? `${destination}/${filename}` : destination;
}

function filenameFromPath(path) {
  return String(path || "").split("/").filter(Boolean).pop() || "Arquivo";
}

function previewUrl(path) {
  const token = getToken();
  const auth = token ? `&token=${encodeURIComponent(token)}` : "";
  return `/api/files/preview?path=${encodeURIComponent(path)}${auth}`;
}

function previewKind(path) {
  const extension = filenameFromPath(path).split(".").pop()?.toLowerCase() || "";
  if (["mp4", "webm", "mov", "m4v"].includes(extension)) return "video";
  if (["mp3", "m4a", "wav", "ogg"].includes(extension)) return "audio";
  if (["png", "jpg", "jpeg", "webp", "gif"].includes(extension)) return "image";
  if (extension === "pdf") return "document";
  if (["txt", "srt", "vtt", "md", "json", "log", "csv"].includes(extension)) return "document";
  return "unknown";
}

function canPreviewJob(job) {
  const path = primaryFilePath(job);
  return job?.status === "succeeded" && isDataPath(path);
}

function previewButton(job, label = "Prévia") {
  const path = primaryFilePath(job);
  if (!canPreviewJob(job)) {
    return '<button class="table-action" type="button" disabled>Indisponível</button>';
  }
  return `
    <button
      class="table-action"
      type="button"
      data-preview-path="${escapeHtml(path)}"
      data-preview-title="${escapeHtml(filenameFromPath(path))}"
    >
      ${escapeHtml(label)}
    </button>
  `;
}

function updateNavState() {
  $$(".nav-item").forEach((button) => {
    const isPanelActive = button.dataset.panel === state.selectedPanel;
    const operation = button.dataset.operation;
    const active = isPanelActive && (!operation || operation === state.operationMode);
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
}

function setPanel(panel) {
  state.selectedPanel = panel;
  updateNavState();
  Object.keys(pageMeta).forEach((name) => {
    $(`#${name}Panel`)?.classList.toggle("active-panel", name === panel);
  });
  updateTopbar();
  if (panel === "jobs" || panel === "queue" || panel === "library") {
    refreshJobs();
  }
  if (panel === "queue" || panel === "settings") {
    refreshStatus();
  }
}

function setOperation(mode) {
  state.operationMode = ["download", "local"].includes(mode) ? mode : "download";
  localStorage.setItem("vdl.operation", state.operationMode);
  $$("[data-operation]").forEach((button) => {
    button.classList.toggle("active", button.dataset.operation === state.operationMode);
  });
  $$("[data-operation-panel]").forEach((panel) => {
    panel.classList.toggle("active-operation", panel.dataset.operationPanel === state.operationMode);
  });
  if (state.operationMode === "download") {
    updateDownloadValidation();
  } else {
    updateLocalValidation();
  }
  updateNavState();
  if (state.selectedPanel === "batch") updateTopbar();
}

function updateTopbar() {
  const meta =
    state.selectedPanel === "batch"
      ? batchOperationMeta[state.operationMode] || batchOperationMeta.download
      : pageMeta[state.selectedPanel] || pageMeta.library;
  setText("#pageEyebrow", meta.eyebrow);
  setText("#pageTitle", meta.title);
  setText("#pageSubtitle", meta.subtitle);
  setText("#primaryTopAction", meta.primary);
  setText("#secondaryTopAction", meta.secondary);
}

function setMode(mode) {
  state.selectedMode = mode;
  localStorage.setItem("vdl.mode", mode);
  $$("[data-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  const headerMode = $("#headerModeSelect");
  if (headerMode) headerMode.value = mode;
  setText("#runtimeTitle", modes[mode]);
  setText("#logsTitle", modes[mode]);
  setText("#ipResult", `IP ainda não testado para ${modes[mode]}.`);
  setHeaderIpResult();
  renderRuntime();
}

function setExecution(mode) {
  state.executionMode = mode;
  $$("[data-execution]").forEach((button) => {
    button.classList.toggle("active", button.dataset.execution === mode);
  });
  const concurrency = $("#concurrencyInput");
  if (!concurrency) return;
  if (mode === "sequential") {
    concurrency.value = "1";
    concurrency.disabled = true;
  } else {
    concurrency.disabled = false;
    concurrency.value = String(Math.max(2, Number(concurrency.value) || 2));
  }
  updateDownloadValidation();
}

function setTranscription(mode) {
  state.transcriptionMode = mode;
  $$("[data-transcription]").forEach((button) => {
    button.classList.toggle("active", button.dataset.transcription === mode);
  });
  applyProcessingRules();
  updateDownloadValidation();
}

function setLocalProcessing(mode) {
  state.localProcessingMode = mode;
  $$("[data-local-processing]").forEach((button) => {
    button.classList.toggle("active", button.dataset.localProcessing === mode);
  });
  setText("#localModeSummary", mode === "context" ? "Transcrever + contexto" : "Apenas transcrever");
  updateLocalValidation();
}

function setCheckbox(id, checked, disabled = false) {
  const input = $(`#${id}`);
  if (!input) return;
  input.checked = checked;
  input.disabled = disabled;
  input.closest(".check-row")?.classList.toggle("disabled", disabled);
}

function applyProcessingRules() {
  const mode = state.transcriptionMode;
  if (mode === "none") {
    setCheckbox("downloadVideo", true, true);
    setCheckbox("extractAudio", false, true);
    setCheckbox("useGpu", false, true);
    setCheckbox("generateContext", false, true);
    setCheckbox("generateSubtitles", false, true);
    setText("#processingRuleText", "Download do vídeo é obrigatório; transcrição e contexto ficam desativados neste modo.");
    return;
  }

  if (mode === "openai") {
    setCheckbox("downloadVideo", true, true);
    setCheckbox("extractAudio", true, false);
    setCheckbox("useGpu", false, true);
    setCheckbox("generateContext", true, false);
    setCheckbox("generateSubtitles", true, false);
    setText("#processingRuleText", "OpenAI usa o modo unificado do VDL; download permanece obrigatório e GPU local fica desativada.");
    return;
  }

  setCheckbox("downloadVideo", true, true);
  setCheckbox("extractAudio", true, false);
  setCheckbox("useGpu", false, false);
  setCheckbox("generateContext", false, false);
  setCheckbox("generateSubtitles", true, false);
  setText("#processingRuleText", "Transcrição local permite legendas e contexto; download permanece obrigatório.");
}

function selectedProcessingMode() {
  if (state.transcriptionMode === "openai") return "unified";
  if (state.transcriptionMode === "none") return "download";
  if ($("#generateContext")?.checked) return "context";
  return "transcribe";
}

function badge(runtime) {
  if (runtime.ready) return '<span class="badge ready">pronto</span>';
  if (runtime.running) return '<span class="badge warn">iniciando</span>';
  return '<span class="badge off">parado</span>';
}

function setApiHealth(isOnline) {
  const health = $("#apiHealth");
  const statusButton = $("#headerStatusButton");
  if (health) {
    health.textContent = isOnline ? "online" : "offline";
  }
  statusButton?.classList.toggle("offline", !isOnline);
}

function setHeaderIpResult(message = "IP não testado", tone = "") {
  const result = $("#headerIpResult");
  if (!result) return;
  result.textContent = message;
  result.classList.remove("visible", "ready", "warn", "error");
  if (tone) {
    result.classList.add("visible", tone);
  }
}

function renderRuntime() {
  const runtimes = state.runtimeStatus?.runtimes || [];
  const grid = $("#runtimeGrid");
  if (!grid) return;
  grid.innerHTML = runtimes
    .map((runtime) => {
      const worker = runtime.worker || {};
      const vpn = runtime.vpn || {};
      return `
        <article class="runtime-card ${runtime.mode === state.selectedMode ? "selected" : ""}" data-card-mode="${runtime.mode}">
          <h3>${runtime.label} ${badge(runtime)}</h3>
          <div class="kv">
            <div>Worker: <span>${worker.running ? worker.status : "off"}</span></div>
            <div>VPN: <span>${vpn.name ? vpn.health || vpn.status || "off" : "não aplicada"}</span></div>
            <div>Container: <span>${worker.name || "-"}</span></div>
          </div>
        </article>
      `;
    })
    .join("");

  $$("[data-card-mode]").forEach((card) => {
    card.addEventListener("click", () => setMode(card.dataset.cardMode));
  });
}

async function refreshStatus() {
  try {
    state.runtimeStatus = await api("/runtime/status");
    setApiHealth(true);
    renderRuntime();
  } catch (error) {
    setApiHealth(false);
    const grid = $("#runtimeGrid");
    if (grid) grid.innerHTML = `<div class="status-strip">API indisponível: ${error.message}</div>`;
  }
}

async function startRuntime(rebuild = false) {
  setText("#ipResult", rebuild ? "Reconstruindo runtime..." : "Iniciando runtime...");
  try {
    await api("/runtime/start", {
      method: "POST",
      body: JSON.stringify({ mode: state.selectedMode, rebuild }),
    });
    setText("#ipResult", `${modes[state.selectedMode]} iniciado.`);
    await refreshStatus();
  } catch (error) {
    setText("#ipResult", `Falha ao iniciar: ${error.message}`);
  }
}

async function stopRuntime() {
  setText("#ipResult", "Parando runtime...");
  try {
    await api("/runtime/stop", {
      method: "POST",
      body: JSON.stringify({ mode: state.selectedMode }),
    });
    setText("#ipResult", `${modes[state.selectedMode]} parado.`);
    await refreshStatus();
  } catch (error) {
    setText("#ipResult", `Falha ao parar: ${error.message}`);
  }
}

async function testRuntimeIp() {
  const loadingMessage = `Consultando IP de ${modes[state.selectedMode]}...`;
  setText("#ipResult", loadingMessage);
  setHeaderIpResult(loadingMessage, "warn");
  try {
    const result = await api(`/runtime/ip?mode=${state.selectedMode}`);
    const message = result.ok
      ? `${modes[state.selectedMode]}: ${result.ip}`
      : `${modes[state.selectedMode]}: ${result.error}`;
    setText(
      "#ipResult",
      message,
    );
    setHeaderIpResult(message, result.ok ? "ready" : "error");
  } catch (error) {
    const message = `Falha no teste: ${error.message}`;
    setText("#ipResult", message);
    setHeaderIpResult(message, "error");
  }
}

function colorizeLogs(text) {
  return escapeHtml(text)
    .split("\n")
    .map((line) => {
      let html = line
        .replace(/(gluetun)/g, '<span class="log-svc">$1</span>')
        .replace(/\b(vdl)\b/g, '<span class="log-vdl">$1</span>');
      if (/(Completed|Initialization Sequence|ready|success|connected)/i.test(line)) {
        html = `<span class="log-ok">${html}</span>`;
      }
      return html;
    })
    .join("\n");
}

async function loadLogs() {
  const output = $("#logsOutput");
  if (output) output.textContent = "Carregando logs...";
  setText("#logsTitle", `Runtime: ${modes[state.selectedMode]}`);
  try {
    const data = await api(`/runtime/logs?mode=${state.selectedMode}&tail=220`);
    const raw = [data.result.stdout, data.result.stderr].filter(Boolean).join("\n") || "Sem logs.";
    if (output) output.innerHTML = colorizeLogs(raw);
  } catch (error) {
    if (output) output.textContent = `Falha ao carregar logs: ${error.message}`;
  }
}

async function openStartupLogs() {
  setPanel("jobs");
  await loadLogs();
}

function closePreview() {
  const dialog = $("#previewDialog");
  const body = $("#previewBody");
  if (body) body.innerHTML = "";
  state.previewUrl = "";
  if (dialog?.open) dialog.close();
}

function openPreview(path, title = "") {
  const cleanPath = String(path || "").trim();
  if (!isDataPath(cleanPath)) return;

  const url = previewUrl(cleanPath);
  const safeTitle = title || filenameFromPath(cleanPath);
  const kind = previewKind(cleanPath);
  state.previewUrl = url;
  setText("#previewTitle", safeTitle);
  setText("#previewPath", cleanPath);

  const body = $("#previewBody");
  if (!body) return;

  if (kind === "video") {
    body.innerHTML = `<video class="preview-video" controls preload="metadata" src="${escapeHtml(url)}"></video>`;
  } else if (kind === "audio") {
    body.innerHTML = `<audio class="preview-audio" controls preload="metadata" src="${escapeHtml(url)}"></audio>`;
  } else if (kind === "image") {
    body.innerHTML = `<img class="preview-image" src="${escapeHtml(url)}" alt="${escapeHtml(safeTitle)}" />`;
  } else if (kind === "document") {
    body.innerHTML = `<iframe class="preview-frame" src="${escapeHtml(url)}" title="${escapeHtml(safeTitle)}" sandbox></iframe>`;
  } else {
    body.innerHTML = `
      <div class="empty-folder">
        <strong>Prévia indisponível</strong>
        <span>Este tipo de arquivo não é renderizado no navegador. Use “Abrir em nova aba” para tentar visualizar.</span>
      </div>
    `;
  }

  $("#previewDialog")?.showModal();
}

function updateUrlCounter() {
  const counts = countUrls($("#urlsInput")?.value || "");
  const duplicateText = counts.duplicates ? `, ${counts.duplicates} duplicada(s)` : "";
  setText("#urlCount", `${counts.valid} válidas${duplicateText}`);
  const counter = $("#urlCount");
  if (counter) {
    counter.classList.toggle("ready", counts.valid > 0 && counts.valid === counts.total);
    counter.classList.toggle("warn", counts.valid === 0 || counts.valid !== counts.total);
  }
}

function setMessage(selector, message, tone = "") {
  const element = $(selector);
  if (!element) return;
  element.textContent = message;
  element.classList.remove("ready", "warn", "error");
  if (tone) element.classList.add(tone);
}

function setFieldValidity(selector, isValid) {
  const element = $(selector);
  if (!element) return;
  element.classList.toggle("is-invalid", !isValid);
}

function isDataPath(value) {
  const clean = (value || "").trim();
  return clean === "/data" || clean.startsWith("/data/");
}

function detectCookie(value) {
  const clean = (value || "").trim();
  if (!clean) {
    return { valid: false, label: "Nenhum token informado", message: "Token/cookie obrigatório para downloads." };
  }
  const compact = clean.replace(/\s+/g, "");
  const looksHeader = /(^|;\s*)[^=;\s]+=[^;]+/.test(clean) && !clean.includes("[");
  const looksBase64 = /^[A-Za-z0-9+/]+={0,2}$/.test(compact) && compact.length % 4 === 0;
  if (clean.startsWith("[") && clean.endsWith("]")) {
    try {
      const parsed = JSON.parse(clean);
      if (Array.isArray(parsed) && parsed.length) {
        return { valid: true, label: "JSON de cookies", message: "Token JSON detectado." };
      }
      return { valid: false, label: "JSON vazio", message: "JSON de cookies vazio." };
    } catch {
      return { valid: false, label: "JSON inválido", message: "JSON de cookies inválido." };
    }
  }
  if (looksHeader) {
    return { valid: true, label: "Header Cookie", message: "Header Cookie detectado." };
  }
  if (looksBase64) {
    try {
      const decoded = atob(compact);
      if (decoded.trim()) {
        return { valid: true, label: "Base64", message: "Token em base64 detectado." };
      }
    } catch {
      return { valid: false, label: "Base64 inválido", message: "Base64 inválido ou incompleto." };
    }
  }
  return { valid: false, label: "Formato não reconhecido", message: "Use base64, JSON exportado ou header Cookie." };
}

function downloadValidation() {
  const urls = parseUrls($("#urlsInput")?.value || "");
  const invalidUrls = urls.filter((url) => !/^https?:\/\//.test(url));
  const destination = $("#destinationInput")?.value.trim() || "";
  const cookie = detectCookie($("#cookieInput")?.value || "");
  const issues = [];
  const warnings = [];

  if (!cookie.valid) issues.push(cookie.message);
  if (!urls.length) issues.push("Informe ao menos uma URL.");
  if (invalidUrls.length) issues.push(`URL inválida: ${invalidUrls[0]}`);
  if (!isDataPath(destination)) issues.push("Destino deve ficar dentro de /data.");

  const counts = countUrls($("#urlsInput")?.value || "");
  if (counts.duplicates) warnings.push(`${counts.duplicates} URL(s) duplicada(s).`);
  if (selectedProcessingMode() === "context" || selectedProcessingMode() === "unified") {
    warnings.push("Contexto/OpenAI requer OPENAI_API_KEY configurada no worker.");
  }

  return { valid: issues.length === 0, issues, warnings, cookie };
}

function updateDownloadValidation(showDetails = false) {
  updateUrlCounter();
  const currentCredentialValue = ($("#cookieInput")?.value || "").trim();
  if (currentCredentialValue !== state.credentialValue) {
    state.credentialValidated = false;
    state.credentialValue = currentCredentialValue;
  }
  const result = downloadValidation();
  const createButton = $("#createBatchButton");
  const credentialSummary = $("#credentialSummary");
  const validateButton = $("#validateCredentialButton");
  if (credentialSummary) credentialSummary.value = result.cookie.label;
  setText("#cookieHint", result.cookie.message);
  $("#cookieHint")?.classList.toggle("ready", result.cookie.valid);
  $("#cookieHint")?.classList.toggle("error", !result.cookie.valid);
  if (validateButton) {
    validateButton.textContent = state.credentialValidated && result.cookie.valid ? "Validado" : "Validar token";
  }
  if (!result.cookie.valid) {
    setMessage("#credentialFeedback", result.cookie.message, "error");
  } else if (state.credentialValidated) {
    setMessage("#credentialFeedback", `Token validado como ${result.cookie.label}.`, "ready");
  } else {
    setMessage("#credentialFeedback", `Token detectado como ${result.cookie.label}. Clique em Validar token.`, "warn");
  }
  setFieldValidity("#destinationInput", isDataPath($("#destinationInput")?.value || ""));
  setFieldValidity("#cookieInput", result.cookie.valid);

  if (createButton) {
    createButton.disabled = !result.valid;
    createButton.textContent = result.valid ? "Criar download" : "Corrija o download";
  }

  if (!result.valid) {
    setMessage("#formMessage", result.issues[0], "error");
  } else if (result.warnings.length) {
    setMessage("#formMessage", result.warnings.join(" "), "warn");
  } else if (showDetails) {
    setMessage("#formMessage", "Download pronto para criar jobs.", "ready");
  } else {
    setMessage("#formMessage", "Download pronto.", "ready");
  }
  return result;
}

function localValidation() {
  const sourcePath = $("#localSourceInput")?.value.trim() || "";
  const destination = $("#localDestinationInput")?.value.trim() || "";
  const issues = [];
  const warnings = [];
  if (!isDataPath(sourcePath)) issues.push("Pasta de entrada deve ficar dentro de /data.");
  if (!isDataPath(destination)) issues.push("Destino deve ficar dentro de /data.");
  if (state.localProcessingMode === "context") {
    warnings.push("Contexto requer OPENAI_API_KEY configurada no worker.");
  }
  return { valid: issues.length === 0, issues, warnings };
}

function updateLocalValidation(showDetails = false) {
  const result = localValidation();
  const createButton = $("#createLocalBatchButton");
  setFieldValidity("#localSourceInput", isDataPath($("#localSourceInput")?.value || ""));
  setFieldValidity("#localDestinationInput", isDataPath($("#localDestinationInput")?.value || ""));
  if (createButton) createButton.disabled = !result.valid;

  if (!result.valid) {
    setMessage("#localFormMessage", result.issues[0], "error");
  } else if (result.warnings.length) {
    setMessage("#localFormMessage", result.warnings.join(" "), "warn");
  } else if (showDetails) {
    setMessage("#localFormMessage", "Transcrição pronta para criar jobs.", "ready");
  } else {
    setMessage("#localFormMessage", "Pronto para criar jobs locais.", "ready");
  }
  return result;
}

function validateActiveOperation() {
  const result = state.operationMode === "download" ? updateDownloadValidation(true) : updateLocalValidation(true);
  if (!result.valid) {
    const selector = state.operationMode === "download" ? "#downloadForm" : "#localTranscriptionForm";
    $(selector)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  return result.valid;
}

function buildPayload() {
  const urls = parseUrls($("#urlsInput").value);
  const concurrency =
    state.executionMode === "sequential" ? 1 : Math.max(1, Math.min(4, Number($("#concurrencyInput").value) || 1));
  return {
    mode: state.selectedMode,
    urls,
    destination: $("#destinationInput").value.trim() || "/data/downloads",
    cookie: $("#cookieInput").value.trim() || null,
    concurrency,
    processing_mode: selectedProcessingMode(),
  };
}

async function createBatch(event) {
  event?.preventDefault();
  const validation = updateDownloadValidation(true);
  if (!validation.valid) return;
  const payload = buildPayload();
  setMessage("#formMessage", "Criando lote...", "warn");
  try {
    const batch = await api("/jobs/download-batch", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setMessage("#formMessage", `Lote ${batch.batch_id} · ${batch.jobs.length} job(s) criados.`, "ready");
    toast(`Lote <strong>${escapeHtml(batch.batch_id)}</strong> criado · ${batch.jobs.length} job(s)`, "ok");
    state.selectedJobId = batch.jobs[0]?.job_id || null;
    setPanel("jobs");
    await refreshJobs();
  } catch (error) {
    setMessage("#formMessage", error.message, "error");
  }
}

function buildLocalPayload() {
  const sourcePath = $("#localSourceInput").value.trim() || "/data/downloads";
  const destination = $("#localDestinationInput").value.trim() || sourcePath;
  const concurrency = Math.max(1, Math.min(2, Number($("#localConcurrencyInput").value) || 1));
  return {
    mode: state.selectedMode,
    source_path: sourcePath,
    destination,
    concurrency,
    processing_mode: state.localProcessingMode,
    use_gpu: $("#localUseGpu").checked,
    whisper_model: $("#localWhisperModel").value,
  };
}

async function createLocalTranscriptionBatch(event) {
  event?.preventDefault();
  const validation = updateLocalValidation(true);
  if (!validation.valid) return;
  const payload = buildLocalPayload();
  setMessage("#localFormMessage", "Criando jobs locais...", "warn");
  try {
    const batch = await api("/jobs/local-transcription-batch", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setMessage("#localFormMessage", `Lote ${batch.batch_id} · ${batch.jobs.length} job(s) locais.`, "ready");
    toast(`Lote <strong>${escapeHtml(batch.batch_id)}</strong> criado · ${batch.jobs.length} job(s) locais`, "ok");
    state.selectedJobId = batch.jobs[0]?.job_id || null;
    setPanel("jobs");
    await refreshJobs();
  } catch (error) {
    setMessage("#localFormMessage", error.message, "error");
  }
}

function renderMetrics() {
  const jobs = allJobs();
  const active = jobs.filter((job) => job.status === "running").length;
  const queued = jobs.filter((job) => job.status === "queued").length;
  const succeeded = jobs.filter((job) => job.status === "succeeded").length;
  const failed = jobs.filter((job) => job.status === "failed" || job.status === "blocked").length;
  setText("#metricActive", String(active));
  setText("#metricQueued", String(queued));
  setText("#metricSucceeded", String(succeeded));
  setText("#metricFailed", String(failed));
  setText("#sidebarJobSummary", `${active} jobs ativos / ${queued} aguardando`);
}

function renderLibrary() {
  const table = $("#libraryTable");
  if (!table) return;
  const search = ($("#librarySearch")?.value || "").trim().toLowerCase();
  const jobs = allJobs().filter((job) => {
    const text = [job.filename, job.destination, job.status, job.processing_mode, job.mode, job.url, job.input_path, job.job_type]
      .join(" ")
      .toLowerCase();
    return !search || text.includes(search);
  });
  if (!jobs.length) {
    table.innerHTML = '<div class="table-empty">Nenhum arquivo encontrado.</div>';
    renderInspector(null);
    return;
  }
  if (!state.selectedJobId || !jobs.some((job) => job.job_id === state.selectedJobId)) {
    state.selectedJobId = jobs[0].job_id;
  }
  table.innerHTML = `
    <div class="library-header">
      <span>Arquivo</span><span>Destino</span><span>Status</span><span>Artefatos</span><span>Ação</span>
    </div>
    ${jobs
      .map((job) => {
        const artifacts = artifactTags(job);
        return `
          <button class="library-row ${job.job_id === state.selectedJobId ? "selected" : ""}" data-job-id="${job.job_id}" title="${job.error || job.url}">
            <span class="file-name">
              <strong>${job.filename}</strong>
              <span>${job.job_type === "local" ? "Local" : processingLabel(job.processing_mode)} · ${modes[job.mode]}</span>
            </span>
            <span class="truncate">${job.job_type === "local" ? job.input_path || job.url : job.destination}</span>
            <span><span class="badge ${statusClass(job.status)}">${statusLabel(job.status)}</span></span>
            <span class="artifact-tags">${artifacts}</span>
            <span class="artifact-tag">Abrir</span>
          </button>
        `;
      })
      .join("")}
  `;
  $$(".library-row").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedJobId = row.dataset.jobId;
      renderLibrary();
    });
  });
  renderInspector(jobs.find((job) => job.job_id === state.selectedJobId));
}

function artifactTags(job) {
  const tags = [];
  if (job.status === "succeeded" && job.job_type !== "local") tags.push("mp4");
  if (job.processing_mode === "transcribe" || job.processing_mode === "context" || job.processing_mode === "unified") tags.push("txt");
  if (job.processing_mode === "context" || job.processing_mode === "unified") tags.push("md");
  if (!tags.length) tags.push("pendente");
  return tags.map((tag) => `<span class="artifact-tag">${tag}</span>`).join("");
}

function renderInspector(job) {
  if (!job) {
    setText("#inspectorTitle", "Nenhum artefato");
    setText("#inspectorPath", "Crie um lote ou selecione um job.");
    $("#artifactList").innerHTML = "";
    return;
  }
  setText("#inspectorTitle", job.filename);
  setText("#inspectorPath", jobInputLabel(job));
  const items = [
    ["Status", statusLabel(job.status)],
    ["Modo", processingLabel(job.processing_mode)],
    ["Tipo", job.job_type === "local" ? "Local" : "Download"],
    ["Runtime", modes[job.mode]],
    ["Atualizado", formatTime(job.updated_at)],
  ];
  $("#artifactList").innerHTML = items
    .map(([label, value]) => `<div class="artifact-item"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  if (canPreviewJob(job)) {
    $("#artifactList").insertAdjacentHTML(
      "beforeend",
      `<div class="inspector-preview">${previewButton(job, "Pré-visualizar arquivo")}</div>`,
    );
  }
}

function renderJobs() {
  renderMetrics();
  renderLibrary();
  renderJobsHistory("#jobsTable", state.batches);
  renderQueue(
    "#queueTable",
    allJobs().filter((job) => ["queued", "running", "blocked"].includes(job.status)),
  );
  setText("#libraryUpdatedAt", `sync ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`);
}

function jobRowHtml(job) {
  return `
    <div class="job-row" title="${escapeHtml(job.error || job.url)}">
      <span>${escapeHtml(job.job_id)}</span>
      <span><span class="badge ${statusClass(job.status)}">${statusLabel(job.status)}</span></span>
      <span class="truncate">${escapeHtml(jobInputLabel(job))}</span>
      <span class="job-meta">${escapeHtml(modes[job.mode])}</span>
      <span class="job-meta">${escapeHtml(processingLabel(job.processing_mode))}</span>
      <span class="job-meta">${escapeHtml(formatTime(job.updated_at))}</span>
      <span class="job-actions">${previewButton(job)}</span>
    </div>
  `;
}

const jobsHeaderHtml = `
  <div class="job-header">
    <span>Job</span><span>Status</span><span>Arquivo</span><span class="job-meta">Runtime</span><span class="job-meta">Modo</span><span class="job-meta">Atualizado</span><span>Ação</span>
  </div>
`;

function renderJobsHistory(selector, batches) {
  const table = $(selector);
  if (!table) return;
  if (!batches.length) {
    table.innerHTML = '<div class="table-empty">Nenhum lote criado ainda.</div>';
    return;
  }
  const sorted = [...batches].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  table.innerHTML = sorted
    .map((batch) => {
      const jobs = batch.jobs || [];
      const meta = `${escapeHtml(modes[batch.mode] || batch.mode)} · ${escapeHtml(processingLabel(batch.processing_mode))} · ${jobs.length} job(s) · ${escapeHtml(formatTime(batch.created_at))}`;
      const head = `
        <div class="batch-group-head">
          <span class="chip cyan" style="width:28px;height:28px;font-size:13px;border-radius:8px">▦</span>
          <span class="batch-id">${escapeHtml(batch.batch_id)}</span>
          <span class="batch-meta">${meta}</span>
        </div>`;
      return head + jobsHeaderHtml + jobs.map(jobRowHtml).join("");
    })
    .join("");
}

function jobProgress(job) {
  if (job.status === "succeeded") return 1;
  if (job.status === "failed" || job.status === "blocked") return 1;
  if (job.status === "running") return 0.6;
  return 0;
}

function progressHtml(job) {
  const pct = Math.round(jobProgress(job) * 100);
  const color = job.status === "failed" || job.status === "blocked" ? "var(--red)" : "var(--cyan)";
  const label = job.status === "queued" ? "—" : `${pct}%`;
  return `<div class="progress-cell"><div class="progress-track"><i style="width:${pct}%;background:${color}"></i></div><span>${label}</span></div>`;
}

function renderQueue(selector, jobs) {
  const table = $(selector);
  if (!table) return;
  if (!jobs.length) {
    table.innerHTML = '<div class="table-empty">Nenhum job em andamento.</div>';
    return;
  }
  table.innerHTML = `
    <div class="job-header">
      <span>Job</span><span>Status</span><span>Arquivo</span><span class="job-meta">Runtime</span><span class="job-meta">Progresso</span><span class="job-meta">Atualizado</span><span>Ação</span>
    </div>
    ${jobs
      .map(
        (job) => `
          <div class="job-row" title="${escapeHtml(job.error || job.url)}">
            <span>${escapeHtml(job.job_id)}</span>
            <span><span class="badge ${statusClass(job.status)}">${statusLabel(job.status)}</span></span>
            <span class="truncate">${escapeHtml(jobInputLabel(job))}</span>
            <span class="job-meta">${escapeHtml(modes[job.mode])}</span>
            <span class="job-meta">${progressHtml(job)}</span>
            <span class="job-meta">${escapeHtml(formatTime(job.updated_at))}</span>
            <span class="job-actions">${previewButton(job)}</span>
          </div>
        `,
      )
      .join("")}
  `;
}

async function refreshJobs() {
  try {
    const data = await api("/jobs");
    state.batches = data.batches || [];
    renderJobs();
  } catch (error) {
    const message = `<div class="table-empty error">Falha ao carregar jobs: ${escapeHtml(error.message)}</div>`;
    ["#jobsTable", "#queueTable", "#libraryTable"].forEach((sel) => {
      if ($(sel)) $(sel).innerHTML = message;
    });
  }
}

async function openFileDialog(path = "/data", target = "destination") {
  state.currentFilePath = path;
  state.fileDialogTarget = target;
  const meta = fileDialogTargets[target] || fileDialogTargets.destination;
  setText("#fileDialogContext", meta.eyebrow);
  setText("#fileDialogTitle", meta.title);
  $("#fileDialog").showModal();
  await loadFilePath(path);
}

async function loadFilePath(path) {
  try {
    const data = await api(`/files?path=${encodeURIComponent(path)}`);
    state.currentFilePath = data.path;
    setText("#dialogPath", data.path);
    setText("#dialogSelectedPath", data.path);
    renderBreadcrumbs(data.path);
    const directories = data.entries.filter((entry) => entry.type === "directory");
    $("#fileList").innerHTML =
      directories
        .map(
          (entry) => `
          <button class="file-entry" data-path="${entry.path}" type="button" aria-label="Abrir ${entry.path}">
            <span class="file-entry-icon">/</span>
            <span class="file-entry-main">
              <strong>${entry.name}</strong>
              <small>${entry.path}</small>
            </span>
            <span class="artifact-tag">Abrir</span>
          </button>
        `,
        )
        .join("") ||
      `<div class="empty-folder">
        <strong>Sem subpastas</strong>
        <span>Use a pasta atual ou volte para a pasta acima.</span>
      </div>`;
    $$(".file-entry").forEach((entry) => {
      entry.addEventListener("click", () => loadFilePath(entry.dataset.path));
    });
  } catch (error) {
    $("#fileList").innerHTML = `<div class="empty-folder error"><strong>Não foi possível abrir</strong><span>${error.message}</span></div>`;
  }
}

function renderBreadcrumbs(path) {
  const breadcrumbs = $("#dialogBreadcrumbs");
  if (!breadcrumbs) return;
  const parts = path.split("/").filter(Boolean);
  const crumbs = [{ label: "/data", path: "/data" }];
  let current = "";
  parts.forEach((part, index) => {
    current += `/${part}`;
    if (index > 0) {
      crumbs.push({ label: part, path: current });
    }
  });
  breadcrumbs.innerHTML = crumbs
    .map(
      (crumb, index) => `
      <button class="breadcrumb-chip ${crumb.path === path ? "active" : ""}" data-path="${crumb.path}" type="button">
        ${index === 0 ? crumb.label : crumb.label}
      </button>
    `,
    )
    .join("");
  $$(".breadcrumb-chip").forEach((button) => {
    button.addEventListener("click", () => loadFilePath(button.dataset.path));
  });
}

function parentPath(path) {
  if (path === "/data") return "/data";
  const parts = path.split("/").filter(Boolean);
  parts.pop();
  return parts.length <= 1 ? "/data" : `/${parts.join("/")}`;
}

function syncDestination(path) {
  $("#destinationInput").value = path;
  setText("#currentDestinationLabel", path);
  updateDownloadValidation();
}

function syncLocalSource(path) {
  $("#localSourceInput").value = path;
  if (!$("#localDestinationInput").value.trim()) {
    $("#localDestinationInput").value = path;
  }
  updateLocalValidation();
}

function syncLocalDestination(path) {
  $("#localDestinationInput").value = path;
  updateLocalValidation();
}

async function createDirectory() {
  const name = window.prompt("Nome da nova pasta");
  if (!name) return;
  const clean = name.trim().replace(/^\/+|\/+$/g, "");
  if (!clean) return;
  const base = ($("#currentDestinationLabel")?.textContent || "/data").trim() || "/data";
  const path = `${base === "/data" ? "/data" : base}/${clean}`;
  try {
    const result = await api("/files/directory", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    syncDestination(result.path);
    await loadFilePath(parentPath(result.path));
  } catch (error) {
    setText("#libraryUpdatedAt", `falha: ${error.message}`);
  }
}

function clearActiveOperation() {
  if (state.operationMode === "download") {
    $("#urlsInput").value = "";
    $("#cookieInput").value = "";
    state.credentialValidated = false;
    state.credentialValue = "";
    $("#destinationInput").value = $("#currentDestinationLabel")?.textContent || "/data/downloads";
    setExecution("sequential");
    setTranscription("none");
    updateDownloadValidation(true);
  } else {
    $("#localSourceInput").value = $("#currentDestinationLabel")?.textContent || "/data/downloads";
    $("#localDestinationInput").value = $("#localSourceInput").value;
    $("#localWhisperModel").value = "base";
    $("#localConcurrencyInput").value = "1";
    $("#localUseGpu").checked = false;
    setLocalProcessing("transcribe");
    updateLocalValidation(true);
  }
}

function validateCredential() {
  const result = updateDownloadValidation(true);
  if (result.cookie.valid) {
    state.credentialValidated = true;
    state.credentialValue = ($("#cookieInput")?.value || "").trim();
    $("#validateCredentialButton").textContent = "Validado";
    setMessage("#credentialFeedback", `Token validado como ${result.cookie.label}.`, "ready");
    setMessage("#formMessage", "Token validado. Continue com URLs e destino.", "ready");
  } else {
    $("#validateCredentialButton").textContent = "Validar token";
    setMessage("#credentialFeedback", result.cookie.message, "error");
    setMessage("#formMessage", result.cookie.message, "error");
  }
}

function handleTopAction(kind) {
  const panel = state.selectedPanel;
  if (kind === "primary") {
    if (panel === "library" || panel === "credentials") return setPanel("batch");
    if (panel === "batch") return validateActiveOperation();
    if (panel === "queue" || panel === "settings") return startRuntime(false);
    if (panel === "jobs") return refreshJobs();
  }
  if (kind === "secondary") {
    if (panel === "library") return refreshJobs();
    if (panel === "batch") return clearActiveOperation();
    if (panel === "queue") return testRuntimeIp();
    if (panel === "jobs") return loadLogs();
    if (panel === "credentials") return setPanel("settings");
    if (panel === "settings") return window.open("/HOWTO-VPN.md", "_blank");
  }
  return null;
}

function bindEvents() {
  $("#sidebarToggle")?.addEventListener("click", () => setSidebarCollapsed(!state.sidebarCollapsed, true));
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-preview-path]");
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    openPreview(button.dataset.previewPath, button.dataset.previewTitle);
  });
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => setPanel(button.dataset.panel)));
  $$("[data-panel-jump]").forEach((button) => {
    button.addEventListener("click", () => setPanel(button.dataset.panelJump));
  });
  $$("[data-operation-jump]").forEach((button) => {
    button.addEventListener("click", () => {
      setPanel("batch");
      setOperation(button.dataset.operationJump);
    });
  });
  $$("[data-operation]").forEach((button) => {
    button.addEventListener("click", () => setOperation(button.dataset.operation));
  });
  $$("[data-mode]").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
  $$("[data-execution]").forEach((button) => {
    button.addEventListener("click", () => setExecution(button.dataset.execution));
  });
  $$("[data-transcription]").forEach((button) => {
    button.addEventListener("click", () => setTranscription(button.dataset.transcription));
  });
  $$("[data-local-processing]").forEach((button) => {
    button.addEventListener("click", () => setLocalProcessing(button.dataset.localProcessing));
  });

  $("#primaryTopAction").addEventListener("click", () => handleTopAction("primary"));
  $("#secondaryTopAction").addEventListener("click", () => handleTopAction("secondary"));
  $("#headerModeSelect").addEventListener("change", (event) => setMode(event.target.value));
  $("#headerTestIpButton").addEventListener("click", testRuntimeIp);
  $("#headerLogsButton").addEventListener("click", openStartupLogs);
  $("#startRuntime").addEventListener("click", () => startRuntime(false));
  $("#rebuildRuntime").addEventListener("click", () => startRuntime(true));
  $("#stopRuntime").addEventListener("click", stopRuntime);
  $("#testIp").addEventListener("click", testRuntimeIp);
  $("#loadLogs").addEventListener("click", loadLogs);
  $("#refreshJobs").addEventListener("click", refreshJobs);
  $("#refreshQueue").addEventListener("click", refreshJobs);
  $("#downloadForm").addEventListener("submit", createBatch);
  $("#localTranscriptionForm").addEventListener("submit", createLocalTranscriptionBatch);
  $("#urlsInput").addEventListener("input", () => updateDownloadValidation());
  $("#destinationInput").addEventListener("input", () => updateDownloadValidation());
  $("#cookieInput").addEventListener("input", () => updateDownloadValidation());
  $("#localSourceInput").addEventListener("input", () => updateLocalValidation());
  $("#localDestinationInput").addEventListener("input", () => updateLocalValidation());
  $("#localWhisperModel").addEventListener("change", () => updateLocalValidation());
  $("#localUseGpu").addEventListener("change", () => updateLocalValidation());
  $("#librarySearch").addEventListener("input", renderLibrary);
  $("#validateCredentialButton").addEventListener("click", validateCredential);
  $("#browseButton").addEventListener("click", () => openFileDialog($("#currentDestinationLabel").textContent || "/data", "destination"));
  $("#browseButtonBatch").addEventListener("click", () => openFileDialog($("#destinationInput").value || "/data", "destination"));
  $("#browseLocalSource").addEventListener("click", () => openFileDialog($("#localSourceInput").value || "/data", "localSource"));
  $("#browseLocalDestination").addEventListener("click", () => openFileDialog($("#localDestinationInput").value || "/data", "localDestination"));
  $("#newFolderButton").addEventListener("click", createDirectory);
  $("#closeDialog").addEventListener("click", () => $("#fileDialog").close());
  $("#closePreviewDialog").addEventListener("click", closePreview);
  $("#previewDialog").addEventListener("cancel", () => closePreview());
  $("#previewDialog").addEventListener("click", (event) => {
    if (event.target === $("#previewDialog")) closePreview();
  });
  $("#fileDialog").addEventListener("click", (event) => {
    if (event.target === $("#fileDialog")) $("#fileDialog").close();
  });
  $("#openPreviewNewTab").addEventListener("click", () => {
    if (state.previewUrl) window.open(state.previewUrl, "_blank", "noopener");
  });
  $("#upDirectory").addEventListener("click", () => loadFilePath(parentPath(state.currentFilePath)));
  $("#useDirectory").addEventListener("click", () => {
    if (state.fileDialogTarget === "localSource") {
      syncLocalSource(state.currentFilePath);
    } else if (state.fileDialogTarget === "localDestination") {
      syncLocalDestination(state.currentFilePath);
    } else {
      syncDestination(state.currentFilePath);
    }
    $("#fileDialog").close();
  });
  $("#helpButton").addEventListener("click", () => window.open("/HOWTO-VPN.md", "_blank"));
  $("#concurrencyInput").addEventListener("input", () => {
    const input = $("#concurrencyInput");
    input.value = String(Math.max(1, Math.min(4, Number(input.value) || 1)));
    updateDownloadValidation();
  });
  $("#localConcurrencyInput").addEventListener("input", () => {
    const input = $("#localConcurrencyInput");
    input.value = String(Math.max(1, Math.min(2, Number(input.value) || 1)));
    updateLocalValidation();
  });
}

/* ============ AUTH + TOAST ============ */
let appStarted = false;
let cpForced = false;
let refreshTimers = [];

function showView(name) {
  $("#loginView")?.classList.toggle("hidden", name !== "login");
  $("#changePasswordView")?.classList.toggle("hidden", name !== "change");
  $("#appShell")?.classList.toggle("hidden", name !== "app");
}

function handleUnauthorized() {
  setToken("");
  appStarted = false;
  refreshTimers.forEach(clearInterval);
  refreshTimers = [];
  showView("login");
}

function updatePasswordBadge(me) {
  const badge = $("#passwordStatusBadge");
  if (!badge) return;
  badge.textContent = me.must_change ? "senha padrão" : "senha definida";
  badge.classList.toggle("amber", Boolean(me.must_change));
  badge.classList.toggle("ready", !me.must_change);
}

function applyUser(me) {
  setText("#sidebarUser", me.username);
  setText("#credentialsUser", me.username);
  updatePasswordBadge(me);
}

async function bootstrapAuth() {
  if (!getToken()) {
    showView("login");
    return;
  }
  try {
    const me = await api("/auth/me");
    applyUser(me);
    if (me.must_change) showChangePassword(true);
    else enterApp();
  } catch {
    handleUnauthorized();
  }
}

async function enterApp() {
  showView("app");
  if (!appStarted) {
    appStarted = true;
    await startApp();
  }
}

function showChangePassword(forced) {
  cpForced = Boolean(forced);
  const cancel = $("#cpCancel");
  if (cancel) cancel.style.display = forced ? "none" : "";
  const err = $("#cpError");
  if (err) err.hidden = true;
  showView("change");
}

async function handleLogin(event) {
  event?.preventDefault();
  const username = ($("#loginUser")?.value || "").trim();
  const password = $("#loginPassword")?.value || "";
  const err = $("#loginError");
  if (err) err.hidden = true;
  try {
    const result = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setToken(result.token);
    if ($("#loginPassword")) $("#loginPassword").value = "";
    applyUser(result);
    if (result.must_change) showChangePassword(true);
    else enterApp();
  } catch (error) {
    if (err) {
      err.textContent = error.message;
      err.hidden = false;
    }
  }
}

async function handleLogout() {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch {
    /* ignora falhas de logout */
  }
  setToken("");
  location.reload();
}

function passwordScore(value) {
  let score = 0;
  if (value.length >= 8) score += 1;
  if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1;
  if (/\d/.test(value)) score += 1;
  if (/[^A-Za-z0-9]/.test(value)) score += 1;
  return score;
}

function updateStrength() {
  const value = $("#cpNew")?.value || "";
  const score = passwordScore(value);
  $$("#cpStrength i").forEach((bar, index) => {
    bar.className = index < score ? (score <= 1 ? "weak" : "on") : "";
  });
  const text = $("#cpStrengthText");
  if (text) {
    text.textContent =
      value.length < 8
        ? "Mínimo 8 caracteres."
        : `${["Fraca", "Fraca", "Média", "Forte", "Forte"][score]} · ${value.length} caracteres`;
  }
}

async function handleChangePassword(event) {
  event?.preventDefault();
  const current = $("#cpCurrent")?.value || "";
  const next = $("#cpNew")?.value || "";
  const confirm = $("#cpConfirm")?.value || "";
  const err = $("#cpError");
  if (err) err.hidden = true;
  if (next.length < 8) {
    if (err) {
      err.textContent = "A nova senha deve ter ao menos 8 caracteres.";
      err.hidden = false;
    }
    return;
  }
  if (next !== confirm) {
    if (err) {
      err.textContent = "As senhas não conferem.";
      err.hidden = false;
    }
    return;
  }
  try {
    await api("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current, new: next }),
    });
    ["#cpCurrent", "#cpNew", "#cpConfirm"].forEach((sel) => {
      if ($(sel)) $(sel).value = "";
    });
    updateStrength();
    toast("Senha atualizada com sucesso.", "ok");
    const me = await api("/auth/me");
    applyUser(me);
    enterApp();
  } catch (error) {
    if (err) {
      err.textContent = error.message;
      err.hidden = false;
    }
  }
}

let toastTimer;
function toast(message, tone = "") {
  const el = $("#toast");
  if (!el) return;
  el.className = `toast ${tone}`.trim();
  el.innerHTML = message;
  el.classList.remove("hidden");
  requestAnimationFrame(() => el.classList.add("show"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.classList.add("hidden"), 250);
  }, 4200);
}

function bindAuthEvents() {
  $("#loginForm")?.addEventListener("submit", handleLogin);
  $("#logoutButton")?.addEventListener("click", handleLogout);
  $("#openChangePassword")?.addEventListener("click", () => showChangePassword(false));
  $("#changePasswordForm")?.addEventListener("submit", handleChangePassword);
  $("#cpCancel")?.addEventListener("click", () => {
    if (!cpForced) enterApp();
  });
  $("#cpNew")?.addEventListener("input", updateStrength);
}

async function startApp() {
  setSidebarCollapsed(state.sidebarCollapsed);
  updateTopbar();
  setMode(state.selectedMode);
  setExecution(state.executionMode);
  setTranscription(state.transcriptionMode);
  setLocalProcessing(state.localProcessingMode);
  syncDestination($("#destinationInput").value);
  syncLocalSource($("#localSourceInput").value);
  syncLocalDestination($("#localDestinationInput").value);
  setOperation(state.operationMode);
  updateDownloadValidation();
  updateLocalValidation();
  const loading = '<div class="loading-row"><span class="spinner"></span> Carregando…</div>';
  ["#libraryTable", "#jobsTable", "#queueTable", "#runtimeGrid"].forEach((sel) => {
    if ($(sel)) $(sel).innerHTML = loading;
  });
  await refreshStatus();
  await refreshJobs();
  refreshTimers.push(setInterval(refreshStatus, 6000));
  refreshTimers.push(setInterval(refreshJobs, 4000));
}

function init() {
  bindEvents();
  bindAuthEvents();
  bootstrapAuth();
}

init();
