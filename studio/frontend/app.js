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
    subtitle: "Downloads por URL com cookie e opções de processamento.",
    primary: "Validar",
    secondary: "Limpar",
  },
  transcribe: {
    eyebrow: "Transcrições",
    title: "Transcrições",
    subtitle: "Transcreva arquivos do servidor com Whisper local ou OpenAI.",
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
  transcribeEngine: "local",
  runtimeStatus: null,
  batches: [],
  selectedJobId: null,
  currentFilePath: "/data",
  fileDialogTarget: "destination",
  credentialValidated: false,
  credentialValue: "",
  previewUrl: "",
  libraryPath: "/data/storage",
  libraryEntries: [],
  librarySelectedPath: null,
  librarySig: "",
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
  library: {
    eyebrow: "Biblioteca",
    title: "Ir para a pasta",
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
    canceled: "Cancelado",
  }[status] || status;
}

function statusClass(status) {
  if (status === "succeeded") return "ready";
  if (status === "running") return "ready";
  if (status === "failed" || status === "blocked") return "error";
  if (status === "queued") return "warn";
  if (status === "canceled") return "";
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
  if (panel === "jobs" || panel === "queue" || panel === "library" || panel === "transcribe") {
    refreshJobs();
  }
  if (panel === "library") {
    loadLibrary(state.libraryPath);
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
  updateTranscriptionHint();
  updatePipelineSummary();
  updateDownloadValidation();
}

function updateTranscriptionHint() {
  const hints = {
    none: "Apenas baixa o vídeo, sem gerar texto.",
    local: "Transcreve no servidor com Whisper (offline). Permite legendas e contexto.",
    openai: "Transcreve via OpenAI (modo unificado). Requer OPENAI_API_KEY no worker.",
  };
  setText("#transcriptionHint", hints[state.transcriptionMode] || "");
}

function updatePipelineSummary() {
  const t = state.transcriptionMode;
  const steps = ["Baixar vídeo"];
  if (t !== "none" || $("#extractAudio")?.checked) steps.push("extrair MP3");
  if (t === "local") steps.push("transcrever (Whisper local)");
  else if (t === "openai") steps.push("transcrever (OpenAI)");
  const outputs = [];
  if ($("#generateSubtitles")?.checked) outputs.push(".srt");
  if ($("#generateContext")?.checked) outputs.push(".md");
  if (outputs.length) steps.push(`gerar ${outputs.join(" + ")}`);
  setText("#pipelineFlow", steps.join("  →  "));
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
  renderNamePreview();
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
  if (state.transcribeEngine === "openai") {
    warnings.push("OpenAI (modo unificado) requer OPENAI_API_KEY configurada no worker.");
  } else if (state.localProcessingMode === "context") {
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
    filenames: filenameLines(urls.length),
  };
}

// Nomes alinhados POSICIONALMENTE às URLs (linha vazia = automático no backend).
function filenameLines(count) {
  const raw = ($("#filenamesInput")?.value ?? "").split(/\r?\n/).map((line) => line.trim());
  return Array.from({ length: count }, (_, i) => raw[i] || "");
}

function urlBasename(url) {
  try {
    const path = new URL(url).pathname;
    const last = path.split("/").filter(Boolean).pop() || url;
    return last;
  } catch {
    return (url.split("/").filter(Boolean).pop() || url).split("?")[0];
  }
}

// Espelha sanitize_output_filename do backend (só para o preview).
function previewFilename(custom, index, width) {
  const clean = String(custom || "")
    .replace(/\\/g, "/")
    .split("/")
    .pop()
    .replace(/[<>:"|?*\x00-\x1f]/g, "")
    .replace(/\s+/g, " ")
    .replace(/^\.+|\.+$/g, "")
    .trim();
  if (!clean) return `${String(index).padStart(width, "0")}.mp4`;
  return /\.(mp4|mkv|mov|webm|m4v)$/i.test(clean) ? clean : `${clean}.mp4`;
}

function renderNamePreview() {
  const box = $("#namePreview");
  if (!box) return;
  const urls = parseUrls($("#urlsInput")?.value || "");
  const names = ($("#filenamesInput")?.value ?? "").split(/\r?\n/).map((line) => line.trim());
  if (!urls.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  const width = Math.max(2, String(urls.length).length);
  const finals = urls.map((_url, i) => previewFilename(names[i], i + 1, width));
  const seen = {};
  finals.forEach((name) => (seen[name] = (seen[name] || 0) + 1));
  const rows = urls
    .map((url, i) => {
      const dup = seen[finals[i]] > 1 ? ' <span class="name-preview-dup">duplicado</span>' : "";
      const custom = (names[i] || "").length > 0;
      return `<div class="name-preview-row">
        <span class="name-preview-idx">${String(i + 1).padStart(width, "0")}</span>
        <span class="name-preview-src truncate" title="${escapeHtml(url)}">${escapeHtml(urlBasename(url))}</span>
        <span class="name-preview-arrow">→</span>
        <span class="name-preview-dst ${custom ? "custom" : ""}"><strong>${escapeHtml(finals[i])}</strong>${dup}</span>
      </div>`;
    })
    .join("");
  box.innerHTML = `<div class="name-preview-head">Prévia · URL → nome do arquivo</div>${rows}`;
  box.hidden = false;
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
    toast(`Lote <strong>${escapeHtml(batch.batch_id)}</strong> criado · ${batch.jobs.length} job(s) · 📁 ${escapeHtml(batch.destination || "")}`, "ok");
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
  const openai = state.transcribeEngine === "openai";
  return {
    mode: state.selectedMode,
    source_path: sourcePath,
    destination,
    concurrency,
    processing_mode: openai ? "unified" : state.localProcessingMode,
    use_gpu: openai ? false : $("#localUseGpu").checked,
    whisper_model: openai ? "base" : $("#localWhisperModel").value,
  };
}

function setTranscribeEngine(engine) {
  state.transcribeEngine = engine === "openai" ? "openai" : "local";
  const openai = state.transcribeEngine === "openai";
  $$("[data-transcribe-engine]").forEach((button) => {
    button.classList.toggle("active", button.dataset.transcribeEngine === state.transcribeEngine);
  });
  // Whisper local/GPU/modo só fazem sentido no engine local
  ["localModeField", "localWhisperField", "localGpuField"].forEach((id) => $(`#${id}`)?.classList.toggle("hidden", openai));
  const hint = $("#transcribeOpenaiHint");
  if (hint) hint.hidden = !openai;
  setText(
    "#transcribeEngineHint",
    openai
      ? "Transcreve via OpenAI (modo unificado): transcrição + contexto. Requer OPENAI_API_KEY no worker."
      : "Transcreve no servidor com Whisper (offline). Permite só transcrever ou transcrever + contexto.",
  );
  setText("#localModeSummary", openai ? "OpenAI · transcrever + contexto" : state.localProcessingMode === "context" ? "Transcrever + contexto" : "Apenas transcrever");
  updateLocalValidation();
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
    toast(`Lote <strong>${escapeHtml(batch.batch_id)}</strong> criado · ${batch.jobs.length} job(s) locais · 📁 ${escapeHtml(batch.destination || "")}`, "ok");
    state.selectedJobId = batch.jobs[0]?.job_id || null;
    setPanel("transcribe");
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

const CATEGORY_LABELS = { video: "Vídeo", audio: "Áudio", legenda: "Legenda", contexto: "Contexto", imagem: "Imagem", outro: "Arquivo" };
const CATEGORY_GLYPHS = { video: "▶", audio: "♫", legenda: "❝", contexto: "≣", imagem: "▦", outro: "·" };

function fileCategory(name) {
  const ext = (String(name).split(".").pop() || "").toLowerCase();
  if (["mp4", "webm", "mov", "m4v", "mkv", "avi", "flv"].includes(ext)) return "video";
  if (["mp3", "m4a", "wav", "ogg", "aac"].includes(ext)) return "audio";
  if (["srt", "vtt"].includes(ext)) return "legenda";
  if (ext === "md") return "contexto";
  if (["png", "jpg", "jpeg", "webp", "gif"].includes(ext)) return "imagem";
  return "outro";
}

function fileGlyph(entry) {
  return entry.type === "directory" ? "▤" : CATEGORY_GLYPHS[fileCategory(entry.name)] || "·";
}

function formatSize(bytes) {
  if (bytes == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 && unit > 0 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

function canPreviewPath(path) {
  return previewKind(path) !== "unknown";
}

async function loadLibrary(path, force = true) {
  const target = path || state.libraryPath || "/data/downloads";
  try {
    const data = await api(`/files?path=${encodeURIComponent(target)}`);
    const entries = data.entries || [];
    const sig = `${data.path}|${entries.map((entry) => `${entry.name}:${entry.size}`).join("|")}`;
    state.libraryPath = data.path;
    setText("#libraryUpdatedAt", `sync ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`);
    if (!force && sig === state.librarySig) return; // nada mudou: evita re-render no auto-refresh
    state.librarySig = sig;
    state.libraryEntries = entries;
    renderLibraryBrowser();
  } catch (error) {
    if (target !== "/data") {
      // a pasta padrão pode não existir neste ambiente — cai para a raiz /data
      return loadLibrary("/data");
    }
    state.libraryEntries = [];
    renderLibraryBreadcrumbs();
    if ($("#libraryTable")) {
      $("#libraryTable").innerHTML = `<div class="table-empty error">Não foi possível abrir a pasta: ${escapeHtml(error.message)}</div>`;
    }
    renderLibraryInspector(null);
  }
}

function renderLibraryBreadcrumbs() {
  const nav = $("#libraryBreadcrumbs");
  if (!nav) return;
  const parts = String(state.libraryPath || "/data").split("/").filter(Boolean);
  const crumbs = [{ label: "/data", path: "/data" }];
  let current = "";
  parts.forEach((part, index) => {
    current += `/${part}`;
    if (index > 0) crumbs.push({ label: part, path: current });
  });
  nav.innerHTML = crumbs
    .map(
      (crumb) =>
        `<button class="breadcrumb-chip ${crumb.path === state.libraryPath ? "active" : ""}" data-lib-path="${escapeHtml(crumb.path)}" type="button">${escapeHtml(crumb.label)}</button>`,
    )
    .join('<span class="crumb-sep">›</span>');
  $$("[data-lib-path]").forEach((button) => {
    button.addEventListener("click", () => loadLibrary(button.dataset.libPath));
  });
}

function renderLibrarySummary(entries) {
  const dirs = entries.filter((entry) => entry.type === "directory").length;
  const counts = {};
  entries
    .filter((entry) => entry.type === "file")
    .forEach((entry) => {
      const cat = fileCategory(entry.name);
      counts[cat] = (counts[cat] || 0) + 1;
    });
  const parts = [`${entries.length} ${entries.length === 1 ? "item" : "itens"}`];
  if (dirs) parts.push(`${dirs} pasta${dirs > 1 ? "s" : ""}`);
  [
    ["video", "vídeo"],
    ["audio", "áudio"],
    ["legenda", "legenda"],
    ["contexto", "contexto"],
    ["imagem", "imagem"],
    ["outro", "outro"],
  ].forEach(([cat, label]) => {
    if (counts[cat]) parts.push(`${counts[cat]} ${label}${counts[cat] > 1 ? "s" : ""}`);
  });
  setText("#libraryFolderSummary", parts.join(" · "));
}

function entryRowHtml(entry) {
  const isDir = entry.type === "directory";
  const selected = !isDir && entry.path === state.librarySelectedPath;
  const ext = isDir ? "pasta" : (entry.name.split(".").pop() || "arquivo").toLowerCase();
  const action = isDir
    ? '<span class="artifact-tag">Abrir</span>'
    : canPreviewPath(entry.path)
      ? `<span class="table-action" data-preview-path="${escapeHtml(entry.path)}" data-preview-title="${escapeHtml(entry.name)}">Prévia</span>`
      : '<span class="muted-text">—</span>';
  return `
    <div class="library-row ${isDir ? "is-dir" : ""} ${selected ? "selected" : ""}" data-path="${escapeHtml(entry.path)}" data-type="${entry.type}" title="${escapeHtml(entry.name)}">
      <span class="file-name"><span class="file-ic">${fileGlyph(entry)}</span><strong>${escapeHtml(entry.name)}</strong></span>
      <span class="truncate">${escapeHtml(ext)}</span>
      <span class="truncate">${isDir ? "—" : formatSize(entry.size)}</span>
      <span class="library-row-action">${action}</span>
    </div>
  `;
}

function renderLibraryBrowser() {
  renderLibraryBreadcrumbs();
  const all = state.libraryEntries || [];
  renderLibrarySummary(all);
  const table = $("#libraryTable");
  if (!table) return;
  const search = ($("#librarySearch")?.value || "").trim().toLowerCase();
  const entries = all.filter((entry) => !search || entry.name.toLowerCase().includes(search));
  if (!entries.length) {
    table.innerHTML = `<div class="table-empty">${search ? "Nada encontrado nesta pasta." : "Pasta vazia."}</div>`;
    renderLibraryInspector(null);
    return;
  }
  table.innerHTML = `
    <div class="library-header"><span>Nome</span><span>Tipo</span><span>Tamanho</span><span>Ação</span></div>
    ${entries.map(entryRowHtml).join("")}
  `;
  $$("#libraryTable .library-row").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("[data-preview-path]")) return;
      if (row.dataset.type === "directory") {
        state.librarySelectedPath = null;
        loadLibrary(row.dataset.path);
      } else {
        state.librarySelectedPath = row.dataset.path;
        renderLibraryBrowser();
      }
    });
  });
  renderLibraryInspector(entries.find((entry) => entry.path === state.librarySelectedPath) || null);
}

function renderLibraryInspector(entry) {
  if (!entry) {
    setText("#inspectorTitle", "Nenhum item");
    setText("#inspectorPath", "Selecione um arquivo para ver detalhes.");
    $("#artifactList").innerHTML = "";
    return;
  }
  const isDir = entry.type === "directory";
  setText("#inspectorTitle", entry.name);
  setText("#inspectorPath", entry.path);
  const rows = [
    ["Tipo", isDir ? "Pasta" : CATEGORY_LABELS[fileCategory(entry.name)] || "Arquivo"],
    ["Extensão", isDir ? "—" : `.${(entry.name.split(".").pop() || "").toLowerCase()}`],
    ["Tamanho", isDir ? "—" : formatSize(entry.size)],
  ];
  $("#artifactList").innerHTML = rows
    .map(([label, value]) => `<div class="artifact-item"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`)
    .join("");
  if (!isDir && canPreviewPath(entry.path)) {
    $("#artifactList").insertAdjacentHTML(
      "beforeend",
      `<div class="inspector-preview"><span class="secondary-button full-width" data-preview-path="${escapeHtml(entry.path)}" data-preview-title="${escapeHtml(entry.name)}">Pré-visualizar</span></div>`,
    );
  }
}

async function libraryNewFolder() {
  const name = window.prompt("Nome da nova pasta");
  if (!name) return;
  const clean = name.trim().replace(/^\/+|\/+$/g, "").replace(/\/{2,}/g, "/");
  if (!clean) return;
  const base = String(state.libraryPath || "/data").replace(/\/+$/, "");
  try {
    const result = await api("/files/directory", { method: "POST", body: JSON.stringify({ path: `${base}/${clean}` }) });
    await loadLibrary(state.libraryPath);
    toast(`Pasta criada: <strong>${escapeHtml(result.path)}</strong>`, "ok");
  } catch (error) {
    toast(`Falha ao criar pasta: ${escapeHtml(error.message)}`, "error");
  }
}

function renderJobs() {
  renderMetrics();
  renderJobsHistory("#jobsTable", state.batches);
  if ($("#transcribeJobsTable")) {
    renderJobsHistory("#transcribeJobsTable", state.batches.filter((batch) => (batch.job_type || "download") === "local"));
  }
  renderQueue(
    "#queueTable",
    allJobs().filter((job) => ["queued", "running", "blocked"].includes(job.status)),
  );
  checkBatchCompletion();
  setText("#libraryUpdatedAt", `sync ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`);
}

const TERMINAL_STATUSES = ["succeeded", "failed", "blocked", "canceled"];

function checkBatchCompletion() {
  if (!state.batchDoneSeen) state.batchDoneSeen = new Set();
  const firstRun = !state.batchReportInit;
  state.batches.forEach((batch) => {
    const jobs = batch.jobs || [];
    if (!jobs.length) return;
    const done = jobs.every((job) => TERMINAL_STATUSES.includes(job.status));
    if (!done || state.batchDoneSeen.has(batch.batch_id)) return;
    state.batchDoneSeen.add(batch.batch_id);
    if (firstRun) return; // não reporta lotes já concluídos na carga inicial
    const ok = jobs.filter((job) => job.status === "succeeded").length;
    const canceled = jobs.filter((job) => job.status === "canceled").length;
    const fail = jobs.length - ok - canceled;
    const where = batch.destination ? ` · 📁 ${escapeHtml(batch.destination)}` : "";
    const extra = `${fail ? ` / ${fail} falha(s)` : ""}${canceled ? ` / ${canceled} cancelado(s)` : ""}`;
    toast(
      `Lote <strong>${escapeHtml(batch.batch_id)}</strong> concluído · ${ok} ok${extra}${where}`,
      fail ? "error" : "ok",
    );
  });
  state.batchReportInit = true;
}

function renameButton(job) {
  if (job.job_type === "local" || job.status !== "succeeded") return "";
  return `<button class="table-action" data-rename-batch="${escapeHtml(job.batch_id)}" data-rename-job="${escapeHtml(job.job_id)}" data-rename-current="${escapeHtml(job.filename || "")}" type="button">Renomear</button>`;
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
      <span class="job-actions">${renameButton(job)}${previewButton(job)}</span>
    </div>
  `;
}

const jobsHeaderHtml = `
  <div class="job-header">
    <span>Job</span><span>Status</span><span>Arquivo</span><span class="job-meta">Runtime</span><span class="job-meta">Modo</span><span class="job-meta">Atualizado</span><span>Ação</span>
  </div>
`;

function batchActionsHtml(batch) {
  const jobs = batch.jobs || [];
  const id = escapeHtml(batch.batch_id);
  const hasRunning = jobs.some((job) => job.status === "running");
  const hasPending = jobs.some((job) => job.status === "queued" || job.status === "running");
  const hasRetryable = jobs.some((job) => ["blocked", "failed", "canceled"].includes(job.status));
  const buttons = [];
  if ((batch.job_type || "download") === "download") {
    buttons.push(`<button class="batch-action" data-batch-action="import" data-batch-id="${id}" type="button" title="Carregar URLs, nomes e opções no formulário">Importar</button>`);
  }
  if (hasPending) {
    buttons.push(`<button class="batch-action" data-batch-action="cancel" data-batch-id="${id}" type="button">Cancelar</button>`);
  }
  if (hasRetryable && !hasRunning) {
    buttons.push(`<button class="batch-action" data-batch-action="retry" data-batch-id="${id}" type="button">Reprocessar</button>`);
  }
  buttons.push(
    `<button class="batch-action danger" data-batch-action="delete" data-batch-id="${id}" type="button"${hasRunning ? ' title="Cancele o lote antes de excluir"' : ""}>Excluir</button>`,
  );
  return `<span class="batch-actions">${buttons.join("")}</span>`;
}

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
      const dest = batch.destination ? ` · 📁 ${escapeHtml(batch.destination)}` : "";
      const meta = `${escapeHtml(modes[batch.mode] || batch.mode)} · ${escapeHtml(processingLabel(batch.processing_mode))} · ${jobs.length} job(s)${dest} · ${escapeHtml(formatTime(batch.created_at))}`;
      const head = `
        <div class="batch-group-head">
          <span class="chip cyan" style="width:28px;height:28px;font-size:13px;border-radius:8px">▦</span>
          <span class="batch-id">${escapeHtml(batch.batch_id)}</span>
          <span class="batch-meta">${meta}</span>
          ${batchActionsHtml(batch)}
        </div>`;
      return head + jobsHeaderHtml + jobs.map(jobRowHtml).join("");
    })
    .join("");
  table.querySelectorAll("[data-batch-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const batchId = button.dataset.batchId;
      const batch = state.batches.find((item) => item.batch_id === batchId);
      if (button.dataset.batchAction === "cancel") cancelBatch(batchId);
      else if (button.dataset.batchAction === "retry") retryBatch(batchId, batch);
      else if (button.dataset.batchAction === "delete") deleteBatch(batchId);
      else if (button.dataset.batchAction === "import") importBatch(batch);
    });
  });
}

function importBatch(batch) {
  if (!batch) return;
  const jobs = batch.jobs || [];
  setPanel("batch");
  setOperation("download");
  if (batch.mode) setMode(batch.mode);
  $("#urlsInput").value = jobs.map((job) => job.url).join("\n");
  if ($("#filenamesInput")) $("#filenamesInput").value = jobs.map((job) => job.filename || "").join("\n");
  $("#destinationInput").value = batch.destination || "/data/downloads";

  const pm = batch.processing_mode || "download";
  setTranscription(pm === "unified" ? "openai" : pm === "download" ? "none" : "local");
  if (pm === "context") setCheckbox("generateContext", true, false);

  const conc = Math.max(1, Math.min(4, Number(batch.concurrency) || 1));
  setExecution(conc > 1 ? "parallel" : "sequential");
  if ($("#concurrencyInput")) $("#concurrencyInput").value = String(conc);

  $("#cookieInput").value = "";
  state.credentialValidated = false;
  state.credentialValue = "";
  renderNamePreview();
  updateDownloadValidation(true);
  toast(`Dados do lote <strong>${escapeHtml(batch.batch_id)}</strong> importados · cole o cookie e crie o novo lote.`, "ok");
}

async function renameJob(batchId, jobId, current) {
  const name = window.prompt("Novo nome do arquivo (mantém a extensão se você não informar):", current || "");
  if (name === null) return;
  const clean = name.trim();
  if (!clean || clean === current) return;
  try {
    const result = await api(`/jobs/batch/${encodeURIComponent(batchId)}/job/${encodeURIComponent(jobId)}/rename`, {
      method: "POST",
      body: JSON.stringify({ new_name: clean }),
    });
    toast(`Renomeado para <strong>${escapeHtml(result.filename)}</strong>.`, "ok");
    await refreshJobs();
    if (state.selectedPanel === "library") await loadLibrary(state.libraryPath, true);
  } catch (error) {
    toast(`Falha ao renomear: ${escapeHtml(error.message)}`, "error");
  }
}

async function cancelBatch(batchId) {
  if (!window.confirm(`Cancelar os jobs pendentes do lote ${batchId}?`)) return;
  try {
    const result = await api(`/jobs/batch/${encodeURIComponent(batchId)}/cancel`, { method: "POST" });
    toast(`Lote <strong>${escapeHtml(batchId)}</strong> cancelado · ${result.canceled} job(s).`, "ok");
    await refreshJobs();
  } catch (error) {
    toast(`Falha ao cancelar: ${escapeHtml(error.message)}`, "error");
  }
}

async function retryBatch(batchId, batch) {
  const isDownload = (batch?.job_type || "download") === "download";
  let cookie = null;
  if (isDownload) {
    cookie = window.prompt("Cole o cookie/token para reprocessar os downloads deste lote:");
    if (cookie === null) return; // cancelou o prompt
  } else if (!window.confirm(`Reprocessar os jobs pendentes do lote ${batchId}?`)) {
    return;
  }
  try {
    await api(`/jobs/batch/${encodeURIComponent(batchId)}/retry`, {
      method: "POST",
      body: JSON.stringify({ cookie }),
    });
    state.batchDoneSeen?.delete(batchId);
    toast(`Reprocessando lote <strong>${escapeHtml(batchId)}</strong>.`, "ok");
    await refreshJobs();
  } catch (error) {
    toast(`Falha ao reprocessar: ${escapeHtml(error.message)}`, "error");
  }
}

async function deleteBatch(batchId) {
  if (!window.confirm(`Excluir o lote ${batchId}? Isso remove o histórico dos jobs (não apaga arquivos já baixados).`)) return;
  try {
    await api(`/jobs/batch/${encodeURIComponent(batchId)}`, { method: "DELETE" });
    state.batchDoneSeen?.delete(batchId);
    toast(`Lote <strong>${escapeHtml(batchId)}</strong> excluído.`, "ok");
    await refreshJobs();
  } catch (error) {
    toast(`Falha ao excluir: ${escapeHtml(error.message)}`, "error");
  }
}

function jobProgress(job) {
  if (job.status === "succeeded") return 1;
  if (["failed", "blocked", "canceled"].includes(job.status)) return 1;
  if (job.status === "running") return 0.6;
  return 0;
}

function progressHtml(job) {
  const pct = Math.round(jobProgress(job) * 100);
  const color = ["failed", "blocked", "canceled"].includes(job.status) ? "var(--red)" : "var(--cyan)";
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
  closeNewFolderRow();
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

function openNewFolderRow() {
  const row = $("#newFolderRow");
  const input = $("#newFolderInput");
  if (!row || !input) return;
  row.classList.remove("hidden");
  input.value = "";
  input.focus();
}

function closeNewFolderRow() {
  $("#newFolderRow")?.classList.add("hidden");
}

async function submitNewFolder(event) {
  event?.preventDefault();
  const input = $("#newFolderInput");
  const clean = (input?.value || "").trim().replace(/^\/+|\/+$/g, "").replace(/\/{2,}/g, "/");
  if (!clean) {
    input?.focus();
    return;
  }
  const base = String(state.currentFilePath || "/data").replace(/\/+$/, "");
  const path = `${base}/${clean}`;
  try {
    const result = await api("/files/directory", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    closeNewFolderRow();
    await loadFilePath(result.path); // entra na pasta recém-criada (vira o destino)
    toast(`Pasta criada: <strong>${escapeHtml(result.path)}</strong>`, "ok");
  } catch (error) {
    const list = $("#fileList");
    if (list) {
      list.innerHTML = `<div class="empty-folder error"><strong>Não foi possível criar a pasta</strong><span>${escapeHtml(error.message)}</span></div>`;
    }
  }
}

function clearActiveOperation() {
  $("#urlsInput").value = "";
  if ($("#filenamesInput")) $("#filenamesInput").value = "";
  $("#cookieInput").value = "";
  state.credentialValidated = false;
  state.credentialValue = "";
  $("#destinationInput").value = $("#currentDestinationLabel")?.textContent || "/data/downloads";
  setExecution("sequential");
  setTranscription("none");
  renderNamePreview();
  updateDownloadValidation(true);
}

function clearLocalOperation() {
  $("#localSourceInput").value = $("#currentDestinationLabel")?.textContent || "/data/downloads";
  $("#localDestinationInput").value = $("#localSourceInput").value;
  $("#localWhisperModel").value = "base";
  $("#localConcurrencyInput").value = "1";
  $("#localUseGpu").checked = false;
  setLocalProcessing("transcribe");
  setTranscribeEngine("local");
  updateLocalValidation(true);
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
    if (panel === "transcribe") return updateLocalValidation(true);
    if (panel === "queue" || panel === "settings") return startRuntime(false);
    if (panel === "jobs") return refreshJobs();
  }
  if (kind === "secondary") {
    if (panel === "library") return refreshJobs();
    if (panel === "batch") return clearActiveOperation();
    if (panel === "transcribe") return clearLocalOperation();
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
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-rename-job]");
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    renameJob(button.dataset.renameBatch, button.dataset.renameJob, button.dataset.renameCurrent);
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
  $$("[data-transcribe-engine]").forEach((button) => {
    button.addEventListener("click", () => setTranscribeEngine(button.dataset.transcribeEngine));
  });
  $("#refreshTranscribeJobs")?.addEventListener("click", refreshJobs);

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
  $("#filenamesInput")?.addEventListener("input", renderNamePreview);
  $("#destinationInput").addEventListener("input", () => updateDownloadValidation());
  $("#cookieInput").addEventListener("input", () => updateDownloadValidation());
  ["extractAudio", "generateContext", "generateSubtitles", "useGpu"].forEach((id) => {
    $(`#${id}`)?.addEventListener("change", () => {
      updateDownloadValidation();
      updatePipelineSummary();
    });
  });
  $("#localSourceInput").addEventListener("input", () => updateLocalValidation());
  $("#localDestinationInput").addEventListener("input", () => updateLocalValidation());
  $("#localWhisperModel").addEventListener("change", () => updateLocalValidation());
  $("#localUseGpu").addEventListener("change", () => updateLocalValidation());
  $("#librarySearch").addEventListener("input", renderLibraryBrowser);
  $("#validateCredentialButton").addEventListener("click", validateCredential);
  $("#browseButton").addEventListener("click", () => openFileDialog(state.libraryPath || "/data", "library"));
  $("#libraryUpDir")?.addEventListener("click", () => loadLibrary(parentPath(state.libraryPath)));
  $("#browseButtonBatch").addEventListener("click", () => openFileDialog($("#destinationInput").value || "/data", "destination"));
  $("#browseLocalSource").addEventListener("click", () => openFileDialog($("#localSourceInput").value || "/data", "localSource"));
  $("#browseLocalDestination").addEventListener("click", () => openFileDialog($("#localDestinationInput").value || "/data", "localDestination"));
  $("#newFolderButton").addEventListener("click", libraryNewFolder);
  $("#dialogNewFolder")?.addEventListener("click", openNewFolderRow);
  $("#newFolderRow")?.addEventListener("submit", submitNewFolder);
  $("#newFolderCancel")?.addEventListener("click", closeNewFolderRow);
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
    } else if (state.fileDialogTarget === "library") {
      loadLibrary(state.currentFilePath);
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
  setTranscribeEngine(state.transcribeEngine);
  syncDestination($("#destinationInput").value);
  syncLocalSource($("#localSourceInput").value);
  syncLocalDestination($("#localDestinationInput").value);
  setOperation("download"); // painel de lote agora é só-download; transcrição tem seção própria
  updateDownloadValidation();
  updateLocalValidation();
  const loading = '<div class="loading-row"><span class="spinner"></span> Carregando…</div>';
  ["#libraryTable", "#jobsTable", "#queueTable", "#runtimeGrid"].forEach((sel) => {
    if ($(sel)) $(sel).innerHTML = loading;
  });
  await refreshStatus();
  await refreshJobs();
  await loadLibrary(state.libraryPath);
  refreshTimers.push(setInterval(refreshStatus, 6000));
  refreshTimers.push(setInterval(refreshJobs, 4000));
  refreshTimers.push(
    setInterval(() => {
      if (state.selectedPanel === "library") loadLibrary(state.libraryPath, false);
    }, 6000),
  );
}

function init() {
  bindEvents();
  bindAuthEvents();
  bootstrapAuth();
}

init();
