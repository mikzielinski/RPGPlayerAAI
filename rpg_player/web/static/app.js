const state = {
  lastStatus: null,
  envFormDirty: false,
  charDirty: false,
  persDirty: false,
  memDirty: false,
  gameLogs: [],
  gameLogSort: { col: "timestamp", dir: "desc" },
  gameLogFilter: { text: "", event: "!wait", actor: "" },
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
  const pairs = [
    ["bufferMaxExchanges", "bufferMaxExchangesVal", (v) => v],
    ["bufferFlushThreshold", "bufferFlushThresholdVal", (v) => `${v}%`],
  ];
  pairs.forEach(([sliderId, valId, fmt]) => {
    const slider = document.getElementById(sliderId);
    const val = document.getElementById(valId);
    if (!slider || !val) return;
    slider.addEventListener("input", () => {
      val.textContent = fmt(slider.value);
      state.envFormDirty = true;
    });
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

// ── Health row ───────────────────────────────────────────────────────
function renderHealthRow(status) {
  const el = document.getElementById("healthRow");
  if (!el) return;
  const flags = status.flags || {};
  const bot = status.bot || {};

  const micMuted = !!flags.mic_muted;
  const checks = [
    { label: "Bot", ok: bot.running, val: bot.running ? `Działa (PID ${bot.pid || "?"})` : "Zatrzymany" },
    { label: "API Key", ok: flags.has_openai_key, val: flags.has_openai_key ? "Skonfigurowany" : "Brak klucza" },
    { label: "Postać", ok: flags.has_character, val: flags.has_character ? "Załadowana" : "Brak" },
    { label: "Osobowość", ok: flags.has_personality, val: flags.has_personality ? "Załadowana" : "Brak" },
    {
      label: "Pliki gry",
      ok: (flags.game_files_count || 0) > 0,
      val: `${flags.game_files_count || 0} plik${(flags.game_files_count || 0) === 1 ? "" : "ów"}`,
    },
    { label: "Mikrofon", ok: !micMuted, val: micMuted ? "Wyciszony (czat)" : "Aktywny (głos)" },
  ];

  el.innerHTML = checks
    .map(
      (c) =>
        `<div class="health-item ${c.ok ? "health-ok" : "health-fail"}">
          <span class="health-dot"></span>
          <span class="health-label">${c.label}</span>
          <span class="health-val">${c.val}</span>
        </div>`,
    )
    .join("");
}

// ── Buffer progress bar ──────────────────────────────────────────────
function renderBufferBar(status) {
  const bar = document.getElementById("bufferBar");
  const txt = document.getElementById("bufferBarText");
  if (!bar || !txt) return;
  const cur = (status.flags || {}).buffer_current || 0;
  const max = (status.env || {}).buffer_max_exchanges || 15;
  const pct = Math.min(100, Math.round((cur / max) * 100));
  bar.style.width = `${pct}%`;
  txt.textContent = `${cur} / ${max}`;
  bar.className = "progress-fill" + (pct >= 90 ? " buf-high" : pct >= 60 ? " buf-mid" : "");
}

// ── Status grid ──────────────────────────────────────────────────────
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

// ── Game log table ───────────────────────────────────────────────────
const _EVENT_ROW_CLASS = {
  wait: "log-row-dim",
  startup_ingest: "log-row-dim",
  bot_response: "log-row-success",
  session_ready: "log-row-success",
  agent_error: "log-row-danger",
  shutdown_requested: "log-row-warning",
  buffer_flushed: "log-row-warning",
  blocked_speak_up: "log-row-dim",
  cooldown_block: "log-row-dim",
};

function _normalizeLogEntry(entry) {
  const p = entry.payload || {};
  const event = p.event || (entry.type !== "state_trace" ? entry.type : "");
  return {
    timestamp: entry.timestamp || "",
    type: entry.type || "",
    event,
    actor: p.actor || entry.speaker || "",
    status: p.status || "",
    detail: p.detail || entry.text || "",
    _raw: entry,
  };
}

function _populateLogSelects(rows) {
  const evSel = document.getElementById("logFilterEvent");
  const acSel = document.getElementById("logFilterActor");
  if (!evSel || !acSel) return;

  const events = [...new Set(rows.map((r) => r.event).filter(Boolean))].sort();
  const actors = [...new Set(rows.map((r) => r.actor).filter(Boolean))].sort();

  const curEv = evSel.value;
  const curAc = acSel.value;

  evSel.innerHTML =
    `<option value="">Wszystkie zdarzenia</option>` +
    `<option value="!wait"${"!wait" === curEv ? " selected" : ""}>Bez wait</option>` +
    events.map((e) => `<option value="${e}"${e === curEv ? " selected" : ""}>${e}</option>`).join("");

  acSel.innerHTML =
    `<option value="">Wszyscy aktorzy</option>` +
    actors.map((a) => `<option value="${a}"${a === curAc ? " selected" : ""}>${a}</option>`).join("");
}

function _redrawLogTable() {
  const tbody = document.getElementById("gameLogBody");
  const countEl = document.getElementById("logCount");
  if (!tbody) return;

  let rows = state.gameLogs.map(_normalizeLogEntry);

  // Filter
  const { text, event, actor } = state.gameLogFilter;
  if (text) rows = rows.filter((r) => r.detail.toLowerCase().includes(text.toLowerCase()) || r.event.toLowerCase().includes(text.toLowerCase()));
  if (event === "!wait") rows = rows.filter((r) => r.event !== "wait");
  else if (event) rows = rows.filter((r) => r.event === event);
  if (actor) rows = rows.filter((r) => r.actor === actor);

  // Sort
  const { col, dir } = state.gameLogSort;
  rows = [...rows].sort((a, b) => {
    const av = a[col] || "";
    const bv = b[col] || "";
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return dir === "asc" ? cmp : -cmp;
  });

  if (countEl) countEl.textContent = `(${rows.length})`;

  // Update sort indicators on headers
  document.querySelectorAll(".log-table th[data-sort]").forEach((th) => {
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.sort === col) th.classList.add(dir === "asc" ? "sort-asc" : "sort-desc");
  });

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="log-empty">Brak wpisów</td></tr>`;
    return;
  }

  tbody.innerHTML = rows
    .map((r) => {
      const t = r.timestamp ? r.timestamp.substring(11, 19) : "";
      const rowCls = _EVENT_ROW_CLASS[r.event] || "";
      const detail = r.detail.length > 140 ? `${r.detail.substring(0, 140)}…` : r.detail;
      const safeDetail = detail.replace(/&/g, "&amp;").replace(/</g, "&lt;");
      const safeTitle = r.detail.replace(/"/g, "&quot;").replace(/&/g, "&amp;");
      const badgeCls = `ev-${r.event || r.type}`;
      return `<tr class="${rowCls}">
        <td class="log-time">${t}</td>
        <td><span class="log-badge ${badgeCls}">${r.event || r.type}</span></td>
        <td>${r.actor}</td>
        <td>${r.status}</td>
        <td class="log-detail" title="${safeTitle}">${safeDetail}</td>
      </tr>`;
    })
    .join("");
}

function renderGameLogTable(entries) {
  state.gameLogs = entries || [];
  _populateLogSelects(state.gameLogs.map(_normalizeLogEntry));
  _redrawLogTable();
}

function initLogTableEvents() {
  document.querySelectorAll(".log-table th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const col = th.dataset.sort;
      if (state.gameLogSort.col === col) {
        state.gameLogSort.dir = state.gameLogSort.dir === "asc" ? "desc" : "asc";
      } else {
        state.gameLogSort = { col, dir: "asc" };
      }
      _redrawLogTable();
    });
  });

  const filterText = document.getElementById("logFilterText");
  const filterEvent = document.getElementById("logFilterEvent");
  const filterActor = document.getElementById("logFilterActor");
  const filterClear = document.getElementById("logFilterClear");

  filterText?.addEventListener("input", () => {
    state.gameLogFilter.text = filterText.value;
    _redrawLogTable();
  });
  filterEvent?.addEventListener("change", () => {
    state.gameLogFilter.event = filterEvent.value;
    _redrawLogTable();
  });
  filterActor?.addEventListener("change", () => {
    state.gameLogFilter.actor = filterActor.value;
    _redrawLogTable();
  });
  filterClear?.addEventListener("click", () => {
    state.gameLogFilter = { text: "", event: "!wait", actor: "" };
    if (filterText) filterText.value = "";
    if (filterEvent) filterEvent.value = "!wait";
    if (filterActor) filterActor.value = "";
    _redrawLogTable();
  });
}

// ── Other renderers ──────────────────────────────────────────────────
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

function setDiscordStatus(payload) {
  const d = payload || {};
  const tokenOk = d.token_configured ?? false;
  const lines = [
    `── Konfiguracja (.env) ──────────────────`,
    `enabled:          ${d.enabled ?? false}`,
    `token:            ${tokenOk ? "✓ skonfigurowany" : "✗ BRAK — wklej token i zapisz"}`,
    `text_only:        ${d.text_only ?? true}`,
    `guild_id:         ${d.guild_id || "—"}`,
    `text_channel_id:  ${d.text_channel_id || "—"}`,
    `voice_channel_id: ${d.voice_channel_id || "—"}`,
    ``,
    `── Połączenie (aktywne gdy bot działa) ──`,
    `connected:    ${d.connected ?? false}`,
    `guild:        ${d.guild || "—"}`,
    `text_channel: ${d.text_channel || "—"}`,
    `voice_rx:     ${d.voice_rx ?? false}`,
    `voice_tx:     ${d.voice_tx ?? false}`,
    `known_users:  ${(d.known_users || []).join(", ") || "—"}`,
    `last_error:   ${d.last_error || "—"}`,
  ];
  document.getElementById("discordStatusView").textContent = lines.join("\n");

  // Update token field placeholder to reflect saved state
  const tokenEl = document.getElementById("discordBotToken");
  if (tokenEl && !tokenEl.value) {
    tokenEl.placeholder = tokenOk
      ? "●●●●●●●● (token zapisany — wklej nowy aby zmienić)"
      : "Bot token z Discord Developer Portal";
  }
}

// ── State refresh ────────────────────────────────────────────────────
async function refreshState() {
  const status = await requestJson("/api/state");
  state.lastStatus = status;
  renderStatusGrid(status);
  renderHealthRow(status);
  renderBufferBar(status);
  setBotLogs(status.bot?.logs || []);
  setDiscordStatus(status.discord || {});

  const buf = status.bot?.buffer || [];
  renderContextWindow(buf);
  renderNowView(buf);
  applyModeUI(!!(status.flags?.mic_muted));

  if (!state.envFormDirty) {
    const env = status.env || {};
    _setVal("whisperLanguage", env.whisper_language || "pl");
    _setVal("swearingIntensity", env.swearing_intensity || "off");
    _setVal("responseMode", env.response_mode || "gm");
    _setChecked("whisperInsecureSsl", !!env.whisper_insecure_ssl);
    _setChecked("allowSpeakUp", !!env.allow_proactive_speak_up);
    _setChecked("enableExtraPlayers", !!env.enable_additional_ai_players);
    _setVal("bufferMaxExchanges", String(env.buffer_max_exchanges || 15));
    const valEl = document.getElementById("bufferMaxExchangesVal");
    if (valEl) valEl.textContent = String(env.buffer_max_exchanges || 15);
    const threshPct = Math.round((env.buffer_flush_threshold ?? 0.95) * 100);
    _setVal("bufferFlushThreshold", String(threshPct));
    const threshValEl = document.getElementById("bufferFlushThresholdVal");
    if (threshValEl) threshValEl.textContent = `${threshPct}%`;
    _setVal("ttsBackend", env.tts_backend || "edge");
    _setVal("ttsVoice", env.tts_voice || "");
    _setVal("openaiTtsModel", env.openai_tts_model || "");
    _setVal("openaiTtsVoice", env.openai_tts_voice || "");
    _setVal("openaiTtsFormat", env.openai_tts_format || "mp3");
    _setChecked("discordEnabled", !!env.discord_enabled);
    _setChecked("discordTextOnly", env.discord_text_only !== false);
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

// ── Memory tab ───────────────────────────────────────────────────────
async function loadMemory() {
  const res = await requestJson("/api/memory");
  document.getElementById("memoryJson").value = JSON.stringify(res.data || {}, null, 2);
  state.memDirty = false;
  const err = document.getElementById("memoryJsonError");
  if (err) err.classList.add("hidden");
  const badge = document.getElementById("memoryStatusBadge");
  if (badge) {
    const d = res.data || {};
    const hasContent = Object.values(d).some((v) => (Array.isArray(v) ? v.length : v && typeof v === "object" ? Object.keys(v).length : false));
    badge.textContent = hasContent ? "Aktywna" : "Pusta";
    badge.className = `badge ${hasContent ? "badge-on" : "badge-off"}`;
  }
}

async function saveMemory() {
  const raw = document.getElementById("memoryJson").value.trim();
  let data = {};
  try { if (raw) data = JSON.parse(raw); } catch (e) { showToast(`Błąd JSON: ${e.message}`, true); return; }
  const res = await requestJson("/api/memory", { method: "POST", body: JSON.stringify({ data }) });
  state.memDirty = false;
  showToast(res.message || "Pamięć zapisana");
}

function renderContextWindow(buffer) {
  const el = document.getElementById("contextWindowView");
  if (!el) return;
  if (!buffer || !buffer.length) {
    el.innerHTML = `<div class="context-entry-empty">Bufor pusty</div>`;
    return;
  }
  el.innerHTML = buffer
    .map((e) => {
      const isBot = e.speaker && e.speaker !== "gracz";
      return `<div class="context-entry ${isBot ? "context-entry-bot" : ""}">
        <span class="context-entry-speaker">${e.speaker || "?"}</span>
        <span class="context-entry-text">${(e.text || "").replace(/</g, "&lt;")}</span>
      </div>`;
    })
    .join("");
  el.scrollTop = el.scrollHeight;
}

function renderNowView(buffer) {
  const el = document.getElementById("nowView");
  if (!el) return;
  const last = buffer && buffer.length ? buffer[buffer.length - 1] : null;
  if (!last) {
    el.innerHTML = `<span class="now-empty">Brak wypowiedzi</span>`;
    return;
  }
  el.innerHTML = `<strong>${last.speaker || "?"}</strong>: ${(last.text || "").replace(/</g, "&lt;")}`;
}

// ── Data loaders ─────────────────────────────────────────────────────
async function loadCharacter() {
  const res = await requestJson("/api/character");
  document.getElementById("characterJson").value = JSON.stringify(res.data || {}, null, 2);
  state.charDirty = false;
  const el = document.getElementById("characterJson");
  if (el) { el.classList.remove("json-invalid"); }
  const err = document.getElementById("characterJsonError");
  if (err) err.classList.add("hidden");
}

async function loadPersonality() {
  const res = await requestJson("/api/personality");
  document.getElementById("personalityJson").value = JSON.stringify(res.data || {}, null, 2);
  state.persDirty = false;
  const el = document.getElementById("personalityJson");
  if (el) { el.classList.remove("json-invalid"); }
  const err = document.getElementById("personalityJsonError");
  if (err) err.classList.add("hidden");
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
  renderGameLogTable(res.logs || []);
}

async function loadDiscordStatus() {
  const res = await requestJson("/api/discord");
  setDiscordStatus(res || {});
}

async function testDiscordConnection() {
  const btn = document.getElementById("testDiscordBtn");
  const view = document.getElementById("discordTestView");
  if (!view) return;
  view.style.display = "block";
  view.textContent = "⏳ Testuję połączenie z Discord...";
  if (btn) btn.disabled = true;
  try {
    const res = await requestJson("/api/discord/test", { method: "POST" });
    if (res.ok) {
      const lines = [
        `✅ Token OK — bot: ${res.bot} (ID: ${res.bot_id})`,
        res.guild   ? `✅ Serwer: ${res.guild}` : "",
        res.channel ? `✅ Kanał: ${res.channel}` : "",
      ].filter(Boolean);
      view.textContent = lines.join("\n");
      view.style.color = "var(--green, #4caf50)";
    } else {
      const lines = [
        `❌ Błąd na kroku: ${res.step || "?"}`,
        `   ${res.message || "nieznany błąd"}`,
        res.guild_error   ? `❌ Serwer: ${res.guild_error}` : "",
        res.channel_error ? `❌ Kanał: ${res.channel_error}` : "",
        res.bot ? `ℹ Bot: ${res.bot}` : "",
      ].filter(Boolean);
      view.textContent = lines.join("\n");
      view.style.color = "var(--red, #f44336)";
    }
  } catch (e) {
    view.textContent = `❌ Błąd: ${e.message}`;
    view.style.color = "var(--red, #f44336)";
  } finally {
    if (btn) btn.disabled = false;
  }
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
  const threshSlider = document.getElementById("bufferFlushThreshold");
  const threshVal = threshSlider ? (parseInt(threshSlider.value, 10) / 100) : 0.95;
  return {
    whisper_language: document.getElementById("whisperLanguage")?.value || "pl",
    whisper_insecure_ssl: document.getElementById("whisperInsecureSsl").checked,
    swearing_intensity: document.getElementById("swearingIntensity").value,
    response_mode: document.getElementById("responseMode").value,
    allow_proactive_speak_up: document.getElementById("allowSpeakUp").checked,
    enable_additional_ai_players: document.getElementById("enableExtraPlayers").checked,
    buffer_max_exchanges: document.getElementById("bufferMaxExchanges").value,
    buffer_flush_threshold: threshVal,
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
    discord_text_only: document.getElementById("discordTextOnly")?.checked ?? true,
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
  state.envFormDirty = false;
  showToast(res.message || "Zapisano Discord");
  const tokenEl = document.getElementById("discordBotToken");
  tokenEl.value = "";
  if (token) tokenEl.placeholder = "●●●●●●●● (token zapisany — wklej nowy aby zmienić)";
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

async function flushBuffer() {
  const res = await requestJson("/api/buffer/flush", { method: "POST" });
  showToast(res.message || "Bufor przepłukany");
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
// ── Chat mode ────────────────────────────────────────────────────────
let _chatPollInterval = null;
let _lastChatTs = "";

function _chatBubble(msg) {
  const isBot = msg.role === "bot";
  const speaker = (msg.speaker || (isBot ? "bot" : "gracz")).replace(/</g, "&lt;");
  const text = (msg.text || "").replace(/</g, "&lt;").replace(/\n/g, "<br/>");
  const time = msg.ts ? new Date(msg.ts).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
  return `<div class="chat-bubble ${isBot ? "chat-bubble-bot" : "chat-bubble-user"}">
    <div class="chat-bubble-meta">
      <span class="chat-speaker">${speaker}</span>
      <span class="chat-time">${time}</span>
    </div>
    <div class="chat-bubble-text">${text}</div>
  </div>`;
}

async function loadChatHistory() {
  try {
    const data = await requestJson("/api/chat/history");
    const msgs = data.history || [];
    const el = document.getElementById("chatMessages");
    if (!el) return;

    if (!msgs.length) {
      el.innerHTML = '<div class="chat-empty">Brak wiadomości. Wpisz coś poniżej.</div>';
      return;
    }

    const lastTs = msgs[msgs.length - 1]?.ts || "";
    const isNew = lastTs !== _lastChatTs;
    _lastChatTs = lastTs;

    el.innerHTML = msgs.map(_chatBubble).join("");
    if (isNew) el.scrollTop = el.scrollHeight;
  } catch (_) {}
}

async function sendChatMessage() {
  const input = document.getElementById("chatInput");
  const speakerEl = document.getElementById("chatSpeaker");
  const text = (input?.value || "").trim();
  if (!text) return;
  const speaker = (speakerEl?.value || "gracz").trim() || "gracz";

  input.value = "";
  input.style.height = "";

  try {
    await requestJson("/api/chat/message", {
      method: "POST",
      body: JSON.stringify({ text, speaker }),
    });
    await loadChatHistory();
  } catch (err) {
    showToast(`Błąd wysyłania: ${err.message}`, true);
  }
}

async function clearChatHistory() {
  await requestJson("/api/chat/history", { method: "DELETE" });
  _lastChatTs = "";
  await loadChatHistory();
  showToast("Historia czatu wyczyszczona.");
}

function startChatPolling() {
  if (_chatPollInterval) return;
  _chatPollInterval = setInterval(async () => {
    await loadChatHistory();
    // mirror activity badge into chat sidebar
    try {
      const data = await requestJson("/api/bot/activity");
      const badge = document.getElementById("chatActivityBadge");
      const detail = document.getElementById("chatActivityDetail");
      if (badge) {
        const s = (data.status || "unknown").toUpperCase();
        badge.textContent = _ACTIVITY_LABELS[s] || s;
        badge.className = `badge ${_ACTIVITY_CLASS[s] || "badge-off"}`;
      }
      if (detail) {
        const parts = [];
        if (data.actor) parts.push(data.actor);
        if (data.detail) parts.push(data.detail);
        detail.textContent = parts.join(" — ");
      }
    } catch (_) {}
  }, 1500);
}

function stopChatPolling() {
  if (_chatPollInterval) { clearInterval(_chatPollInterval); _chatPollInterval = null; }
}

// ── Input mode (voice / chat) ────────────────────────────────────────
async function setInputMode(mode) {
  try {
    await requestJson("/api/bot/mode", { method: "POST", body: JSON.stringify({ mode }) });
    applyModeUI(mode === "chat");
    showToast(mode === "chat" ? "Tryb czatu — mikrofon wyciszony." : "Tryb głosowy — mikrofon aktywny.");
  } catch (err) {
    showToast(`Błąd zmiany trybu: ${err.message}`, true);
  }
}

function applyModeUI(muted) {
  const label = muted ? "💬 Czat — mikrofon wyciszony" : "🎤 Głos — mikrofon aktywny";

  // Panel tab
  ["modeVoiceBtn", "modeChatBtn"].forEach((id) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    const isActive = muted ? btn.dataset.mode === "chat" : btn.dataset.mode === "voice";
    btn.classList.toggle("mode-btn-active", isActive);
  });
  const txt = document.getElementById("modeStatusText");
  if (txt) txt.textContent = muted ? "Mikrofon wyciszony" : "Mikrofon aktywny";

  // Chat tab sidebar
  ["chatModeVoiceBtn", "chatModeChatBtn"].forEach((id) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    const isActive = muted ? btn.dataset.mode === "chat" : btn.dataset.mode === "voice";
    btn.classList.toggle("mode-btn-active", isActive);
  });
  const chatTxt = document.getElementById("chatModeStatusText");
  if (chatTxt) chatTxt.textContent = label;
}

// ── Force turn ───────────────────────────────────────────────────────
async function forceTurn() {
  const res = await requestJson("/api/bot/force", { method: "POST" });
  showToast(res.message || "Sygnał wysłany");
}

// ── Activity monitor ─────────────────────────────────────────────────
const _ACTIVITY_LABELS = {
  LISTENING: "Słucha",
  SPEAKING: "Mówi",
  CLASSIFYING: "Klasyfikuje",
  COOLDOWN: "Cooldown",
  MEMORIZING: "Zapamiętuje",
  ERROR: "Błąd",
  STOPPED: "Zatrzymany",
};
const _ACTIVITY_CLASS = {
  LISTENING: "badge-on",
  SPEAKING: "badge-speaking",
  CLASSIFYING: "badge-classifying",
  MEMORIZING: "badge-classifying",
  COOLDOWN: "badge-off",
  ERROR: "badge-off",
  STOPPED: "badge-off",
};

async function refreshActivity() {
  try {
    const data = await requestJson("/api/bot/activity");
    const badge = document.getElementById("activityBadge");
    const detail = document.getElementById("activityDetail");
    if (!badge) return;
    const s = (data.status || "unknown").toUpperCase();
    badge.textContent = _ACTIVITY_LABELS[s] || s;
    badge.className = `badge ${_ACTIVITY_CLASS[s] || "badge-off"}`;
    if (detail) {
      const parts = [];
      if (data.actor) parts.push(data.actor);
      if (data.detail) parts.push(data.detail);
      detail.textContent = parts.join(" — ");
    }
  } catch (_) {}
}

// ── JSON editor helpers ───────────────────────────────────────────────
function formatJson(editorId) {
  const el = document.getElementById(editorId);
  const errEl = document.getElementById(`${editorId}Error`);
  if (!el) return;
  try {
    const parsed = JSON.parse(el.value);
    el.value = JSON.stringify(parsed, null, 2);
    el.classList.remove("json-invalid");
    if (errEl) errEl.classList.add("hidden");
  } catch (e) {
    el.classList.add("json-invalid");
    if (errEl) { errEl.textContent = `JSON error: ${e.message}`; errEl.classList.remove("hidden"); }
  }
}

function validateJsonEditor(editorId) {
  const el = document.getElementById(editorId);
  const errEl = document.getElementById(`${editorId}Error`);
  if (!el || !el.value.trim()) return;
  try {
    JSON.parse(el.value);
    el.classList.remove("json-invalid");
    if (errEl) errEl.classList.add("hidden");
  } catch (e) {
    el.classList.add("json-invalid");
    if (errEl) { errEl.textContent = `JSON error: ${e.message}`; errEl.classList.remove("hidden"); }
  }
}

// ── Auto-reload JSON editors (if not dirty) ──────────────────────────
async function _autoReloadChar() {
  if (state.charDirty) return;
  const res = await requestJson("/api/character");
  const el = document.getElementById("characterJson");
  if (el) el.value = JSON.stringify(res.data || {}, null, 2);
}
async function _autoReloadPers() {
  if (state.persDirty) return;
  const res = await requestJson("/api/personality");
  const el = document.getElementById("personalityJson");
  if (el) el.value = JSON.stringify(res.data || {}, null, 2);
}
async function _autoReloadMem() {
  if (state.memDirty) return;
  const res = await requestJson("/api/memory");
  const el = document.getElementById("memoryJson");
  if (el) el.value = JSON.stringify(res.data || {}, null, 2);
  const badge = document.getElementById("memoryStatusBadge");
  if (badge) {
    const d = res.data || {};
    const hasContent = Object.values(d).some((v) => (Array.isArray(v) ? v.length : v && typeof v === "object" ? Object.keys(v).length : false));
    badge.textContent = hasContent ? "Aktywna" : "Pusta";
    badge.className = `badge ${hasContent ? "badge-on" : "badge-off"}`;
  }
}

// ── Secrets ──────────────────────────────────────────────────────────
async function loadSecrets() {
  const el = document.getElementById("secretsList");
  if (!el) return;
  try {
    const data = await requestJson("/api/secrets");
    const secrets = data.secrets || [];
    if (!secrets.length) {
      el.innerHTML = '<p class="help-text">Brak aktywnych sekretów.</p>';
      return;
    }
    el.innerHTML = secrets.map((s) => {
      const date = s.added_at ? new Date(s.added_at).toLocaleString("pl-PL") : "";
      const srcBadge = `<span class="badge badge-${s.source === "gm" ? "on" : "off"}" style="font-size:0.7em">${(s.source || "gm").toUpperCase()}</span>`;
      const preview = (s.content || "").slice(0, 200).replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const more = s.content && s.content.length > 200 ? "…" : "";
      return `<div class="secret-item" data-secret-id="${s.id}">
        <div class="secret-header">
          ${srcBadge}
          <strong>${(s.title || "Sekret").replace(/</g, "&lt;")}</strong>
          <span class="secret-date">${date}</span>
          <button class="btn btn-danger btn-sm" data-delete-secret="${s.id}">Usuń</button>
        </div>
        <pre class="secret-preview">${preview}${more}</pre>
      </div>`;
    }).join("");
  } catch (err) {
    if (el) el.innerHTML = `<p class="help-text error">Błąd: ${err.message}</p>`;
  }
}

async function addTextSecret() {
  const title = (document.getElementById("secretTitle")?.value || "").trim();
  const text = (document.getElementById("secretText")?.value || "").trim();
  const source = document.getElementById("secretSource")?.value || "gm";
  if (!text) { showToast("Wpisz treść sekretu.", true); return; }
  try {
    const res = await requestJson("/api/secrets", {
      method: "POST",
      body: JSON.stringify({ title, text, source }),
    });
    showToast(res.message || "Sekret dodany.");
    document.getElementById("secretTitle").value = "";
    document.getElementById("secretText").value = "";
    await loadSecrets();
  } catch (err) {
    showToast(`Błąd: ${err.message}`, true);
  }
}

async function uploadSecretFile() {
  const fileInput = document.getElementById("secretFile");
  const file = fileInput?.files?.[0];
  if (!file) { showToast("Wybierz plik.", true); return; }
  const title = (document.getElementById("secretFileTitle")?.value || "").trim();
  const source = document.getElementById("secretFileSource")?.value || "gm";

  const progress = document.getElementById("secretUploadProgress");
  if (progress) progress.style.display = "block";

  try {
    const form = new FormData();
    form.append("file", file);
    form.append("title", title);
    form.append("source", source);
    const resp = await fetch("/api/secrets/upload", { method: "POST", body: form });
    const res = await resp.json();
    if (!resp.ok) throw new Error(res.message || `HTTP ${resp.status}`);
    showToast(res.message || "Plik wgrany i przetworzony.");
    fileInput.value = "";
    if (document.getElementById("secretFileTitle")) document.getElementById("secretFileTitle").value = "";
    await loadSecrets();
  } catch (err) {
    showToast(`Błąd: ${err.message}`, true);
  } finally {
    if (progress) progress.style.display = "none";
  }
}

function wireEvents() {
  const markDirty = () => { state.envFormDirty = true; };
  [
    "whisperLanguage", "whisperInsecureSsl", "swearingIntensity", "responseMode", "allowSpeakUp",
    "enableExtraPlayers", "ttsBackend", "ttsVoice", "openaiTtsModel", "openaiTtsVoice",
    "openaiTtsFormat", "openaiKey",
    "discordEnabled", "discordTextOnly", "discordGuildId", "discordTextChannelId",
    "discordVoiceChannelId", "discordBotToken",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) { el.addEventListener("change", markDirty); el.addEventListener("input", markDirty); }
  });

  document.getElementById("refreshStateBtn").addEventListener("click", async () => {
    await Promise.all([refreshState(), loadGameFiles(), loadSessions(), loadGameLog(), loadDiscordStatus()]);
  });

  document.getElementById("startBotBtn").addEventListener("click", startBot);
  document.getElementById("stopBotBtn").addEventListener("click", stopBot);
  document.getElementById("flushBufferBtn").addEventListener("click", flushBuffer);
  document.getElementById("forceTurnBtn")?.addEventListener("click", forceTurn);

  ["modeVoiceBtn", "modeChatBtn", "chatModeVoiceBtn", "chatModeChatBtn"].forEach((id) => {
    document.getElementById(id)?.addEventListener("click", (e) => {
      setInputMode(e.currentTarget.dataset.mode);
    });
  });
  document.getElementById("validateBtn").addEventListener("click", validateSetup);
  document.getElementById("ingestBtn").addEventListener("click", ingestFiles);
  document.getElementById("saveEnvBtn").addEventListener("click", saveEnv);
  document.getElementById("saveDiscordBtn")?.addEventListener("click", saveDiscord);
  document.getElementById("reloadGameLogBtn").addEventListener("click", loadGameLog);
  document.getElementById("reloadDiscordBtn")?.addEventListener("click", loadDiscordStatus);
  document.getElementById("testDiscordBtn")?.addEventListener("click", testDiscordConnection);
  document.getElementById("reloadSessionsBtn").addEventListener("click", loadSessions);
  document.getElementById("uploadForm").addEventListener("submit", uploadFiles);

  document.getElementById("chatSendBtn")?.addEventListener("click", sendChatMessage);
  document.getElementById("chatInput")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
  });
  document.getElementById("clearChatBtn")?.addEventListener("click", clearChatHistory);

  // Start/stop chat polling based on active tab
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.tab === "chat") { loadChatHistory(); startChatPolling(); }
      else stopChatPolling();
    });
  });

  document.getElementById("addSecretBtn")?.addEventListener("click", addTextSecret);
  document.getElementById("uploadSecretBtn")?.addEventListener("click", uploadSecretFile);
  document.getElementById("reloadSecretsBtn")?.addEventListener("click", loadSecrets);

  document.getElementById("loadMemoryBtn")?.addEventListener("click", loadMemory);
  document.getElementById("saveMemoryBtn")?.addEventListener("click", saveMemory);
  document.getElementById("resetMemoryBtn")?.addEventListener("click", async () => {
    const empty = { known_npcs: {}, known_locations: [], key_decisions: [], session_notes: [], known_players: {}, last_updated: "" };
    const res = await requestJson("/api/memory", { method: "POST", body: JSON.stringify({ data: empty }) });
    showToast(res.message || "Pamięć wyczyszczona");
    document.getElementById("memoryJson").value = JSON.stringify(empty, null, 2);
    const badge = document.getElementById("memoryStatusBadge");
    if (badge) { badge.textContent = "Pusta"; badge.className = "badge badge-off"; }
  });

  document.getElementById("loadCharacterBtn").addEventListener("click", loadCharacter);
  document.getElementById("saveCharacterBtn").addEventListener("click", async () => {
    try { await saveJsonFromEditor("characterJson", "/api/character"); state.charDirty = false; await refreshState(); }
    catch (err) { showToast(`Błąd JSON: ${err.message}`, true); }
  });
  document.getElementById("characterJson")?.addEventListener("input", () => {
    state.charDirty = true;
    validateJsonEditor("characterJson");
  });

  document.getElementById("loadPersonalityBtn").addEventListener("click", loadPersonality);
  document.getElementById("savePersonalityBtn").addEventListener("click", async () => {
    try { await saveJsonFromEditor("personalityJson", "/api/personality"); state.persDirty = false; await refreshState(); }
    catch (err) { showToast(`Błąd JSON: ${err.message}`, true); }
  });
  document.getElementById("personalityJson")?.addEventListener("input", () => {
    state.persDirty = true;
    validateJsonEditor("personalityJson");
  });

  document.getElementById("memoryJson")?.addEventListener("input", () => {
    state.memDirty = true;
    validateJsonEditor("memoryJson");
  });

  document.body.addEventListener("click", (e) => {
    const formatTarget = e.target.getAttribute?.("data-format-json");
    if (formatTarget) { formatJson(formatTarget); return; }
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

    const deleteSecret = target.getAttribute("data-delete-secret");
    if (deleteSecret) {
      await requestJson(`/api/secrets/${encodeURIComponent(deleteSecret)}`, { method: "DELETE" });
      showToast("Sekret usunięty.");
      await loadSecrets();
      return;
    }
  });

  initLogTableEvents();
}

// ── Bootstrap ────────────────────────────────────────────────────────
async function bootstrap() {
  initTabs();
  initSliders();
  wireEvents();
  await Promise.all([
    refreshState(), loadCharacter(), loadPersonality(),
    loadGameFiles(), loadSessions(), loadGameLog(), loadDiscordStatus(), loadMemory(), loadSecrets(),
    refreshActivity(),
  ]);
  setInterval(async () => {
    await refreshState();
    await loadGameLog();
    await loadDiscordStatus();
    await _autoReloadMem();
    await _autoReloadChar();
    await _autoReloadPers();
    await loadSecrets();
    await loadGameFiles();
  }, 4000);

  setInterval(refreshActivity, 2000);
}

bootstrap().catch((err) => showToast(`Błąd inicjalizacji: ${err.message}`, true));
