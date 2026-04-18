const state = {
  lastStatus: null,
  envFormDirty: false,
  wizardOptionsLoaded: false,
};

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const json = await response.json();
  if (!response.ok) {
    throw new Error(json.message || `HTTP ${response.status}`);
  }
  return json;
}

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  toast.classList.toggle("error", isError);
  setTimeout(() => toast.classList.add("hidden"), 2500);
}

function sizeHuman(bytes) {
  if (bytes > 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  if (bytes > 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function renderStatusGrid(status) {
  const el = document.getElementById("statusGrid");
  const flags = status.flags || {};
  const env = status.env || {};
  const bot = status.bot || {};
  const rows = [
    ["Bot", bot.running ? `Dziala (PID ${bot.pid || "-"})` : "Zatrzymany"],
    ["Tryb odpowiedzi", env.response_mode || "-"],
    ["Proaktywne SPEAK_UP", env.allow_proactive_speak_up ? "wlaczone" : "wylaczone"],
    ["Dodatkowi bot-gracze", env.enable_additional_ai_players ? "wlaczone" : "wylaczone"],
    ["Postac", flags.has_character ? "OK" : "Brak"],
    ["Osobowosc", flags.has_personality ? "OK" : "Brak"],
    ["OPENAI_API_KEY", env.openai_api_key_masked || "brak"],
    ["Pliki gry", String(flags.game_files_count || 0)],
    ["Zapisane sesje", String(flags.sessions_count || 0)],
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
    list.innerHTML = `<li class="list-empty">Brak plikow .pdf/.docx/.xlsx</li>`;
    return;
  }
  list.innerHTML = files
    .map(
      (f) => `
    <li>
      <span>${f.name} <small>(${sizeHuman(f.size_bytes)})</small></span>
      <button class="btn btn-danger btn-small" data-delete-file="${f.name}">Usun</button>
    </li>
  `,
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
      <span>${s.file} — ${s.character || "?"} — ${s.exchanges_count} wypowiedzi</span>
      <button class="btn btn-small" data-session-file="${s.file}">Podglad</button>
    </li>
  `,
    )
    .join("");
}

function setCommandOutput(text) {
  document.getElementById("commandOutput").textContent = text || "";
}

function setBotLogs(lines) {
  document.getElementById("botLogs").textContent = (lines || []).join("\n");
}

function renderCharacterCard(card) {
  const el = document.getElementById("characterCardView");
  if (!card) {
    el.innerHTML = `<div class="list-empty">Brak danych karty postaci.</div>`;
    return;
  }
  const statHtml = (card.stats || [])
    .map((s) => `<div class="stat-box"><div class="stat-key">${s.key}</div><div class="stat-value">${s.value}</div></div>`)
    .join("");
  const pills = (arr) =>
    (arr || []).map((v) => `<span class="pill">${v}</span>`).join("") || `<span class="pill">-</span>`;

  const customSections = ((card.system || {}).sheet_sections || [])
    .map((section) => {
      const fields = (section.fields || [])
        .map((f) => `<div class="status-item"><div class="status-key">${f.label}</div><div class="status-value">${f.value}</div></div>`)
        .join("");
      return `<div class="section-title">${section.title}</div><div class="status-grid">${fields}</div>`;
    })
    .join("");

  el.innerHTML = `
    <h3>${card.title || "Nowa postac"}</h3>
    <div class="subtitle">${card.subtitle || ""}</div>
    <div class="section-title">System</div>
    <div class="pill-list">${pills([(card.system || {}).name || "Generic"])}</div>
    <div class="section-title">HP</div>
    <div class="pill-list"><span class="pill">${card.hp?.current || 0} / ${card.hp?.max || 0}</span></div>
    <div class="section-title">Statystyki</div>
    <div class="stats-grid">${statHtml || '<div class="list-empty">Brak statystyk</div>'}</div>
    <div class="section-title">Osobowosc</div>
    <div>${card.personality || "-"}</div>
    <div class="section-title">Historia</div>
    <div>${card.backstory_short || "-"}</div>
    <div class="section-title">Zaklecia</div>
    <div class="pill-list">${pills(card.spells)}</div>
    <div class="section-title">Ekwipunek</div>
    <div class="pill-list">${pills(card.inventory)}</div>
    <div class="section-title">Frazy</div>
    <div class="pill-list">${pills(card.signature_phrases)}</div>
    ${customSections}
  `;
}

function setGameLog(payload) {
  document.getElementById("gameLogView").textContent = JSON.stringify(payload || {}, null, 2);
}

function setDiscordStatus(payload) {
  document.getElementById("discordStatus").textContent = JSON.stringify(payload || {}, null, 2);
}

async function refreshState() {
  const status = await requestJson("/api/state");
  state.lastStatus = status;
  renderStatusGrid(status);
  setBotLogs(status.bot?.logs || []);
  setDiscordStatus(status.discord || {});

  if (!state.envFormDirty) {
    const env = status.env || {};
    document.getElementById("swearingIntensity").value = env.swearing_intensity || "off";
    document.getElementById("responseMode").value = env.response_mode || "gm";
    document.getElementById("allowSpeakUp").checked = !!env.allow_proactive_speak_up;
    document.getElementById("enableExtraPlayers").checked = !!env.enable_additional_ai_players;
    document.getElementById("bufferMaxExchanges").value = String(env.buffer_max_exchanges || 15);
    document.getElementById("ttsBackend").value = env.tts_backend || "edge";
    document.getElementById("ttsVoice").value = env.tts_voice || "";
    document.getElementById("openaiTtsModel").value = env.openai_tts_model || "";
    document.getElementById("openaiTtsVoice").value = env.openai_tts_voice || "";
    document.getElementById("discordEnabled").checked = !!env.discord_enabled;
    document.getElementById("discordGuildId").value = env.discord_guild_id || "";
    document.getElementById("discordTextChannelId").value = env.discord_text_channel_id || "";
    document.getElementById("discordVoiceChannelId").value = env.discord_voice_channel_id || "";
  }
}

async function loadCharacter() {
  const res = await requestJson("/api/character");
  document.getElementById("characterJson").value = JSON.stringify(res.data || {}, null, 2);
  renderCharacterCard(res.card || null);
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
  setGameLog(res);
}

async function loadDiscordStatus() {
  const res = await requestJson("/api/discord");
  setDiscordStatus(res);
}

async function loadWizardOptions() {
  const res = await requestJson("/api/character-wizard/options");
  const systemSel = document.getElementById("wizardSystem");
  const booksSel = document.getElementById("wizardRulebooks");
  systemSel.innerHTML = (res.systems || [])
    .map((s) => `<option value="${s.key}">${s.name}</option>`)
    .join("");
  booksSel.innerHTML = (res.rulebooks || [])
    .map((f) => `<option value="${f.name}">${f.name} (${f.ext})</option>`)
    .join("");
  state.wizardOptionsLoaded = true;
}

async function generateCharacterFromWizard() {
  if (!state.wizardOptionsLoaded) {
    await loadWizardOptions();
  }
  const preferredSystem = document.getElementById("wizardSystem").value || "auto";
  const conceptPrompt = document.getElementById("wizardConcept").value.trim();
  const selected = Array.from(document.getElementById("wizardRulebooks").selectedOptions).map((o) => o.value);
  const res = await requestJson("/api/character-wizard/generate", {
    method: "POST",
    body: JSON.stringify({
      preferred_system: preferredSystem,
      concept_prompt: conceptPrompt,
      selected_rulebooks: selected,
      save: true,
    }),
  });
  document.getElementById("wizardMeta").textContent = JSON.stringify(res.metadata || {}, null, 2);
  document.getElementById("characterJson").value = JSON.stringify(res.data || {}, null, 2);
  renderCharacterCard(res.card || null);
  showToast(res.message || "Wygenerowano karte postaci");
  await refreshState();
}

async function discordStart() {
  const res = await requestJson("/api/discord/start", { method: "POST" });
  showToast(res.message || "Discord start");
  await loadDiscordStatus();
}

async function discordStop() {
  const res = await requestJson("/api/discord/stop", { method: "POST" });
  showToast(res.message || "Discord stop");
  await loadDiscordStatus();
}

async function discordAskIntro() {
  const res = await requestJson("/api/discord/introductions", { method: "POST" });
  showToast(res.message || "Wyslano prosbe o przedstawienie");
  await loadDiscordStatus();
}

async function discordSendManual() {
  const text = document.getElementById("discordManualMessage").value.trim();
  const res = await requestJson("/api/discord/send", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  showToast(res.message || "Wyslano wiadomosc");
  document.getElementById("discordManualMessage").value = "";
  await loadDiscordStatus();
}

async function saveJsonFromEditor(editorId, endpoint) {
  const raw = document.getElementById(editorId).value.trim();
  let data = {};
  if (raw) data = JSON.parse(raw);
  const res = await requestJson(endpoint, {
    method: "POST",
    body: JSON.stringify({ data }),
  });
  showToast(res.message || "Zapisano");
}

async function saveEnv() {
  const key = document.getElementById("openaiKey").value.trim();
  const swearing = document.getElementById("swearingIntensity").value;
  const responseMode = document.getElementById("responseMode").value;
  const allowSpeakUp = document.getElementById("allowSpeakUp").checked;
  const enableExtraPlayers = document.getElementById("enableExtraPlayers").checked;
  const bufferMaxExchanges = document.getElementById("bufferMaxExchanges").value;
  const ttsBackend = document.getElementById("ttsBackend").value;
  const ttsVoice = document.getElementById("ttsVoice").value.trim();
  const openaiTtsModel = document.getElementById("openaiTtsModel").value.trim();
  const openaiTtsVoice = document.getElementById("openaiTtsVoice").value.trim();
  const discordEnabled = document.getElementById("discordEnabled").checked;
  const discordBotToken = document.getElementById("discordBotToken").value.trim();
  const discordGuildId = document.getElementById("discordGuildId").value.trim();
  const discordTextChannelId = document.getElementById("discordTextChannelId").value.trim();
  const discordVoiceChannelId = document.getElementById("discordVoiceChannelId").value.trim();

  const payload = {
    swearing_intensity: swearing,
    response_mode: responseMode,
    allow_proactive_speak_up: allowSpeakUp,
    enable_additional_ai_players: enableExtraPlayers,
    buffer_max_exchanges: bufferMaxExchanges,
    tts_backend: ttsBackend,
    tts_voice: ttsVoice,
    openai_tts_model: openaiTtsModel,
    openai_tts_voice: openaiTtsVoice,
    discord_enabled: discordEnabled,
    discord_guild_id: discordGuildId,
    discord_text_channel_id: discordTextChannelId,
    discord_voice_channel_id: discordVoiceChannelId,
  };
  if (key) payload.openai_api_key = key;
  if (discordBotToken) payload.discord_bot_token = discordBotToken;

  const res = await requestJson("/api/env", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.envFormDirty = false;
  showToast(res.message || "Zapisano");
  document.getElementById("openaiKey").value = "";
  document.getElementById("discordBotToken").value = "";
  await refreshState();
  await loadDiscordStatus();
}

async function validateSetup() {
  setCommandOutput("Uruchamiam walidacje...");
  const res = await requestJson("/api/validate", { method: "POST" });
  setCommandOutput(res.output || "(brak outputu)");
  showToast(res.ok ? "Walidacja OK" : "Walidacja z bledami", !res.ok);
}

async function ingestFiles() {
  const res = await requestJson("/api/ingest", { method: "POST" });
  showToast(res.message || "Ingest gotowy");
  await loadWizardOptions();
}

async function startBot() {
  const res = await requestJson("/api/bot/start", { method: "POST" });
  showToast(res.message || "Bot uruchomiony");
}

async function stopBot() {
  const res = await requestJson("/api/bot/stop", { method: "POST" });
  showToast(res.message || "Bot zatrzymany");
}

async function resetTarget(target) {
  const res = await requestJson("/api/reset", {
    method: "POST",
    body: JSON.stringify({ target }),
  });
  showToast(res.message || "Reset wykonany");
}

async function uploadFiles(ev) {
  ev.preventDefault();
  const input = document.getElementById("gameFilesInput");
  const files = input.files;
  if (!files || files.length === 0) {
    showToast("Wybierz pliki do wyslania", true);
    return;
  }
  const form = new FormData();
  for (const file of files) form.append("files", file);

  const response = await fetch("/api/game-files/upload", {
    method: "POST",
    body: form,
  });
  const json = await response.json();
  if (!response.ok) {
    showToast(json.message || "Blad uploadu", true);
    return;
  }
  const summary = `Zapisano: ${(json.saved || []).join(", ") || "-"}`;
  showToast(summary);
  input.value = "";
  await loadGameFiles();
  await refreshState();
}

async function loadSessionDetails(file) {
  const res = await requestJson(`/api/sessions/${encodeURIComponent(file)}`);
  document.getElementById("sessionDetails").textContent = JSON.stringify(res.session || {}, null, 2);
}

function wireEvents() {
  const markEnvDirty = () => {
    state.envFormDirty = true;
  };

  [
    "swearingIntensity",
    "responseMode",
    "allowSpeakUp",
    "enableExtraPlayers",
    "openaiKey",
    "discordBotToken",
    "discordGuildId",
    "discordTextChannelId",
    "discordVoiceChannelId",
    "discordEnabled",
    "bufferMaxExchanges",
    "ttsBackend",
    "ttsVoice",
    "openaiTtsModel",
    "openaiTtsVoice",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", markEnvDirty);
    el.addEventListener("input", markEnvDirty);
  });

  document.getElementById("refreshStateBtn").addEventListener("click", async () => {
    await refreshState();
    await loadGameFiles();
    await loadSessions();
    await loadGameLog();
    await loadDiscordStatus();
  });

  document.getElementById("startBotBtn").addEventListener("click", startBot);
  document.getElementById("stopBotBtn").addEventListener("click", stopBot);
  document.getElementById("validateBtn").addEventListener("click", validateSetup);
  document.getElementById("ingestBtn").addEventListener("click", ingestFiles);
  document.getElementById("saveEnvBtn").addEventListener("click", saveEnv);
  document.getElementById("generateCharacterBtn").addEventListener("click", async () => {
    try {
      await generateCharacterFromWizard();
    } catch (err) {
      showToast(`Blad kreatora: ${err.message}`, true);
    }
  });
  document.getElementById("reloadGameLogBtn").addEventListener("click", loadGameLog);
  document.getElementById("discordRefreshBtn").addEventListener("click", loadDiscordStatus);
  document.getElementById("discordStartBtn").addEventListener("click", discordStart);
  document.getElementById("discordStopBtn").addEventListener("click", discordStop);
  document.getElementById("discordIntroBtn").addEventListener("click", discordAskIntro);
  document.getElementById("discordSendBtn").addEventListener("click", discordSendManual);

  document.getElementById("loadCharacterBtn").addEventListener("click", loadCharacter);
  document.getElementById("saveCharacterBtn").addEventListener("click", async () => {
    try {
      await saveJsonFromEditor("characterJson", "/api/character");
      await loadCharacter();
      await refreshState();
    } catch (err) {
      showToast(`Blad JSON: ${err.message}`, true);
    }
  });

  document.getElementById("loadPersonalityBtn").addEventListener("click", loadPersonality);
  document.getElementById("savePersonalityBtn").addEventListener("click", async () => {
    try {
      await saveJsonFromEditor("personalityJson", "/api/personality");
      await refreshState();
    } catch (err) {
      showToast(`Blad JSON: ${err.message}`, true);
    }
  });

  document.getElementById("reloadSessionsBtn").addEventListener("click", loadSessions);
  document.getElementById("uploadForm").addEventListener("submit", uploadFiles);

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
      await loadDiscordStatus();
      if (resetTargetName === "character") document.getElementById("characterJson").value = "{}";
      if (resetTargetName === "personality") document.getElementById("personalityJson").value = "{}";
      if (resetTargetName === "character") renderCharacterCard(null);
      return;
    }

    const deleteFile = target.getAttribute("data-delete-file");
    if (deleteFile) {
      await requestJson(`/api/game-files/${encodeURIComponent(deleteFile)}`, { method: "DELETE" });
      showToast(`Usunieto ${deleteFile}`);
      await loadGameFiles();
      await refreshState();
      return;
    }

    const sessionFile = target.getAttribute("data-session-file");
    if (sessionFile) {
      await loadSessionDetails(sessionFile);
    }
  });
}

async function bootstrap() {
  wireEvents();
  await Promise.all([
    refreshState(),
    loadCharacter(),
    loadPersonality(),
    loadGameFiles(),
    loadSessions(),
    loadGameLog(),
    loadDiscordStatus(),
    loadWizardOptions(),
  ]);
  setInterval(async () => {
    await refreshState();
    await loadGameLog();
    await loadDiscordStatus();
  }, 4000);
}

bootstrap().catch((err) => {
  showToast(`Blad inicjalizacji: ${err.message}`, true);
});
