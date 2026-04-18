const state = {
  lastStatus: null,
  envFormDirty: false,
};

// ── Tabs ────────────────────────────────────────────────────────────
function initTabs() {
  const btns = document.querySelectorAll(".tab-btn");
  btns.forEach((btn) => {
    btn.addEventListener("click", () => {
      btns.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((t) => t.classList.remove("active"));
      btn.classList.add("active");
      const tab = document.getElementById(`tab-${btn.dataset.tab}`);
      if (tab) tab.classList.add("active");
    });
  });
}

// ── Slider sync ─────────────────────────────────────────────────────
function initSliders() {
  const slider = document.getElementById("bufferMaxExchanges");
  const val = document.getElementById("bufferMaxExchangesVal");
  if (!slider || !val) return;
  slider.addEventListener("input", () => {
    val.textContent = slider.value;
    state.envFormDirty = true;
  });
}

// ── HTTP helpers ─────────────────────────────────────────────────────
async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const json = await response.json();
  if (!response.ok) throw new Error(json.message || `HTTP ${response.status}`);
  return json;
}

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.remove("hidden", "error");
  if (isError) toast.classList.add("error");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.add("hidden"), 3000);
}

function sizeHuman(bytes) {
  if (bytes > 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  if (bytes > 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

// ── Status rendering ─────────────────────────────────────────────────
function renderStatusGrid(status) {
  const el = document.getElementById("statusGrid");
  const badge = document.getElementById("botStatusBadge");
  const flags = status.flags || {};
  const env = status.env || {};
  const bot = status.bot || {};
  const discord = status.discord || {};

  if (badge) {
    if (bot.running) {
      badge.textContent = `Działa (PID ${bot.pid || "-"})`;
      badge.className = "badge badge-on";
    } else {
      badge.textContent = "Zatrzymany";
      badge.className = "badge badge-off";
    }
  }

  const discordLabel = !env.discord_enabled
    ? "wyłączony"
    : discord.connected
      ? "połączony"
      : "włączony (niepołączony)";

  const rows = [
    ["Tryb odpowiedzi", env.response_mode || "-"],
    ["Bufor kontekstu", `${env.buffer_max_exchanges || "-"} wypowiedzi`],
    ["TTS backend", env.tts_backend || "-"],
    ["Głos TTS", env.tts_voice || "-"],
    ["SPEAK_UP", env.allow_proactive_speak_up ? "włączone" : "wyłączone"],
    ["Dodatkowi gracze", env.enable_additional_ai_players ? "włączone" : "wyłączone"],
    ["Discord", discordLabel],
    ["Postać", flags.has_character ? "OK" : "Brak"],
    ["Osobowość", flags.has_personality ? "OK" : "Brak"],
    ["OpenAI API key", env.openai_api_key_masked || "brak"],
    ["Pliki gry", String(flags.game_files_count || 0)],
    ["Sesje", String(flags.sessions_count || 0)],
  ];

  el.innerHTML = rows
    .map(
      ([k, v]) =>
        `<div class="status-item"><div class="status-key">${k}</div><div class="status-value">${v}</div></div>`,
    )
    .join("");
}

function renderGameFiles(files) {
  const list = document.getElementById("gameFilesList");
  if (!files.length) {
    list.innerHTML = `<li class="list-empty">Brak plików .pdf/.docx/.xlsx</li>`;
    return;
  }
  list.innerHTML = files
    .map(
      (f) => `
    <li>
      <span>${f.name} <small style="color:var(--text-2)">(${sizeHuman(f.size_bytes)})</small></span>
      <button class="btn btn-danger btn-sm" data-delete-file="${f.name}">Usuń</button>
    </li>`,
    )
    .join("");
}

function renderSessions(sessions) {
  const list = document.getElementById("sessionsList");
  if (!sessions.length) {
    list.innerHTML = `<li class="list-empty">Brak zapisanych sesji</li>`;
    return;
  }
  list.innerHTML = sessions
    .map(
      (s) => `
    <li>
      <span>${s.file} &mdash; ${s.character || "?"} &mdash; ${s.exchanges_count} wypowiedzi</span>
      <button class="btn btn-sm" data-session-file="${s.file}">Podgląd</button>
    </li>`,
    )
    .join("");
}

function setCommandOutput(text) {
  document.getElementById("commandOutput").textContent = text || "";
}

function setBotLogs(lines) {
  document.getElementById("botLogs").textContent = (lines || []).join("\n");
}

function setGameLog(entries, latestFile = "") {
  document.getElementById("gameLogView").textContent = JSON.stringify(
    { latest: latestFile, entries },
    null,
    2,
  );
}

function setDiscordStatus(payload) {
  document.getElementById("discordStatusView").textContent = JSON.stringify(payload || {}, null, 2);
}

// ── State refresh ────────────────────────────────────────────────────
async function refreshState() {
  const status = await requestJson("/api/state");
  state.lastStatus = status;
  renderStatusGrid(status);
  setBotLogs(status.bot?.logs || []);
  setDiscordStatus(status.discord || {});

  if (!state.envFormDirty) {
    const env = status.env || {};
    _setVal("swearingIntensity", env.swearing_intensity || "off");
    _setVal("responseMode", env.response_mode || "gm");
    _setChecked("whisperInsecureSsl", !!env.whisper_insecure_ssl);
    _setChecked("allowSpeakUp", !!env.allow_proactive_speak_up);
    _setChecked("enableExtraPlayers", !!env.enable_additional_ai_players);
    _setVal("bufferMaxExchanges", String(env.buffer_max_exchanges || 15));
    const valEl = document.getElementById("bufferMaxExchangesVal");
    if (valEl) valEl.textContent = String(env.buffer_max_exchanges || 15);
    _setVal("ttsBackend", env.tts_backend || "edge");
    _setVal("ttsVoice", env.tts_voice || "");
    _setVal("openaiTtsModel", env.openai_tts_model || "");
    _setVal("openaiTtsVoice", env.openai_tts_voice || "");
    _setVal("openaiTtsFormat", env.openai_tts_format || "mp3");
    _setChecked("discordEnabled", !!env.discord_enabled);
    _setVal("discordGuildId", env.discord_guild_id || "");
    _setVal("discordTextChannelId", env.discord_text_channel_id || "");
    _setVal("discordVoiceChannelId", env.discord_voice_channel_id || "");
  }
}

function _setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}
function _setChecked(id, checked) {
  const el = document.getElementById(id);
  if (el) el.checked = checked;
}

// ── Data loaders ─────────────────────────────────────────────────────
async function loadCharacter() {
  const res = await requestJson("/api/character");
  document.getElementById("characterJson").value = JSON.stringify(res.data || {}, null, 2);
}

async function loadPersonality() {
  const res = await requestJson("/api/personality");
  document.getElementById("personalityJson").value = JSON.stringify(res.data || {}, null, 2);
}

async function loadGameFiles() {
  const res = await requestJson("/api/game-files");
  renderGameFiles(res.files || []);
}

async function loadSessions() {
  const res = await requestJson("/api/sessions");
  renderSessions(res.sessions || []);
}

async function loadGameLog() {
  const res = await requestJson("/api/game-log");
  setGameLog(res.logs || [], res.latest || "");
}

async function loadDiscordStatus() {
  const res = await requestJson("/api/discord");
  setDiscordStatus(res || {});
}

// ── Save helpers ─────────────────────────────────────────────────────
async function saveJsonFromEditor(editorId, endpoint) {
  const raw = document.getElementById(editorId).value.trim();
  let data = {};
  if (raw) data = JSON.parse(raw);
  const res = await requestJson(endpoint, { method: "POST", body: JSON.stringify({ data }) });
  showToast(res.message || "Zapisano");
}

function _collectEnvPayload() {
  return {
    whisper_insecure_ssl: document.getElementById("whisperInsecureSsl").checked,
    swearing_intensity: document.getElementById("swearingIntensity").value,
    response_mode: document.getElementById("responseMode").value,
    allow_proactive_speak_up: document.getElementById("allowSpeakUp").checked,
    enable_additional_ai_players: document.getElementById("enableExtraPlayers").checked,
    buffer_max_exchanges: document.getElementById("bufferMaxExchanges").value,
    tts_backend: document.getElementById("ttsBackend").value,
    tts_voice: (document.getElementById("ttsVoice").value || "").trim(),
    openai_tts_model: (document.getElementById("openaiTtsModel").value || "").trim(),
    openai_tts_voice: (document.getElementById("openaiTtsVoice").value || "").trim(),
    openai_tts_format: document.getElementById("openaiTtsFormat").value,
  };
}

function _collectDiscordPayload() {
  return {
    discord_enabled: document.getElementById("discordEnabled").checked,
    discord_guild_id: (document.getElementById("discordGuildId").value || "").trim(),
    discord_text_channel_id: (document.getElementById("discordTextChannelId").value || "").trim(),
    discord_voice_channel_id: (document.getElementById("discordVoiceChannelId").value || "").trim(),
  };
}

async function saveEnv() {
  const payload = _collectEnvPayload();
  const key = (document.getElementById("openaiKey").value || "").trim();
  if (key) payload.openai_api_key = key;
  const res = await requestJson("/api/env", { method: "POST", body: JSON.stringify(payload) });
  state.envFormDirty = false;
  showToast(res.message || "Zapisano");
  document.getElementById("openaiKey").value = "";
  await refreshState();
}

async function saveDiscord() {
  const payload = _collectDiscordPayload();
  const token = (document.getElementById("discordBotToken").value || "").trim();
  if (token) payload.discord_bot_token = token;
  const res = await requestJson("/api/env", { method: "POST", body: JSON.stringify(payload) });
  showToast(res.message || "Zapisano Discord");
  document.getElementById("discordBotToken").value = "";
  await loadDiscordStatus();
}

// ── Actions ───────────────────────────────────────────────────────────
async function validateSetup() {
  setCommandOutput("Uruchamiam walidację...");
  const res = await requestJson("/api/validate", { method: "POST" });
  setCommandOutput(res.output || "(brak outputu)");
  showToast(res.ok ? "Walidacja OK" : "Walidacja z błędami", !res.ok);
}

async function ingestFiles() {
  const res = await requestJson("/api/ingest", { method: "POST" });
  showToast(res.message || "Ingest gotowy");
  await loadGameLog();
}

async function startBot() {
  const res = await requestJson("/api/bot/start", { method: "POST" });
  showToast(res.message || "Bot uruchomiony");
  await refreshState();
}

async function stopBot() {
  const res = await requestJson("/api/bot/stop", { method: "POST" });
  showToast(res.message || "Bot zatrzymany");
  await refreshState();
}

async function resetTarget(target) {
  const res = await requestJson("/api/reset", { method: "POST", body: JSON.stringify({ target }) });
  showToast(res.message || "Reset wykonany");
}

async function uploadFiles(ev) {
  ev.preventDefault();
  const input = document.getElementById("gameFilesInput");
  const files = input.files;
  if (!files || files.length === 0) { showToast("Wybierz pliki do wysłania", true); return; }
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const response = await fetch("/api/game-files/upload", { method: "POST", body: form });
  const json = await response.json();
  if (!response.ok) { showToast(json.message || "Błąd uploadu", true); return; }
  showToast(`Zapisano: ${(json.saved || []).join(", ") || "-"}`);
  input.value = "";
  await loadGameFiles();
  await refreshState();
}

async function loadSessionDetails(file) {
  const res = await requestJson(`/api/sessions/${encodeURIComponent(file)}`);
  document.getElementById("sessionDetails").textContent = JSON.stringify(res.session || {}, null, 2);
}

// ── Wire events ───────────────────────────────────────────────────────
function wireEvents() {
  const markDirty = () => { state.envFormDirty = true; };
  [
    "whisperInsecureSsl", "swearingIntensity", "responseMode", "allowSpeakUp", "enableExtraPlayers",
    "ttsBackend", "ttsVoice", "openaiTtsModel", "openaiTtsVoice", "openaiTtsFormat", "openaiKey",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) { el.addEventListener("change", markDirty); el.addEventListener("input", markDirty); }
  });

  document.getElementById("refreshStateBtn").addEventListener("click", async () => {
    await Promise.all([refreshState(), loadGameFiles(), loadSessions(), loadGameLog(), loadDiscordStatus()]);
  });

  document.getElementById("startBotBtn").addEventListener("click", startBot);
  document.getElementById("stopBotBtn").addEventListener("click", stopBot);
  document.getElementById("validateBtn").addEventListener("click", validateSetup);
  document.getElementById("ingestBtn").addEventListener("click", ingestFiles);
  document.getElementById("saveEnvBtn").addEventListener("click", saveEnv);
  document.getElementById("saveDiscordBtn")?.addEventListener("click", saveDiscord);
  document.getElementById("reloadGameLogBtn").addEventListener("click", loadGameLog);
  document.getElementById("reloadDiscordBtn")?.addEventListener("click", loadDiscordStatus);
  document.getElementById("reloadSessionsBtn").addEventListener("click", loadSessions);
  document.getElementById("uploadForm").addEventListener("submit", uploadFiles);

  document.getElementById("loadCharacterBtn").addEventListener("click", loadCharacter);
  document.getElementById("saveCharacterBtn").addEventListener("click", async () => {
    try { await saveJsonFromEditor("characterJson", "/api/character"); await refreshState(); }
    catch (err) { showToast(`Błąd JSON: ${err.message}`, true); }
  });

  document.getElementById("loadPersonalityBtn").addEventListener("click", loadPersonality);
  document.getElementById("savePersonalityBtn").addEventListener("click", async () => {
    try { await saveJsonFromEditor("personalityJson", "/api/personality"); await refreshState(); }
    catch (err) { showToast(`Błąd JSON: ${err.message}`, true); }
  });

  document.body.addEventListener("click", async (ev) => {
    const target = ev.target;
    if (!(target instanceof HTMLElement)) return;

    const resetTargetName = target.getAttribute("data-reset");
    if (resetTargetName) {
      await resetTarget(resetTargetName);
      await refreshState();
      await loadGameFiles();
      await loadSessions();
      await loadGameLog();
      if (resetTargetName === "character") document.getElementById("characterJson").value = "{}";
      if (resetTargetName === "personality") document.getElementById("personalityJson").value = "{}";
      return;
    }

    const deleteFile = target.getAttribute("data-delete-file");
    if (deleteFile) {
      await requestJson(`/api/game-files/${encodeURIComponent(deleteFile)}`, { method: "DELETE" });
      showToast(`Usunięto ${deleteFile}`);
      await loadGameFiles();
      await refreshState();
      return;
    }

    const sessionFile = target.getAttribute("data-session-file");
    if (sessionFile) await loadSessionDetails(sessionFile);
  });
}

// ── Bootstrap ────────────────────────────────────────────────────────
async function bootstrap() {
  initTabs();
  initSliders();
  wireEvents();
  await Promise.all([
    refreshState(), loadCharacter(), loadPersonality(),
    loadGameFiles(), loadSessions(), loadGameLog(), loadDiscordStatus(),
  ]);
  setInterval(async () => {
    await refreshState();
    await loadGameLog();
    await loadDiscordStatus();
  }, 4000);
}

bootstrap().catch((err) => showToast(`Błąd inicjalizacji: ${err.message}`, true));
