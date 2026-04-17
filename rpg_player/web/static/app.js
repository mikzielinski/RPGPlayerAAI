const state = {
  lastStatus: null,
  envFormDirty: false,
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

async function refreshState() {
  const status = await requestJson("/api/state");
  state.lastStatus = status;
  renderStatusGrid(status);
  setBotLogs(status.bot?.logs || []);

  if (!state.envFormDirty) {
    const env = status.env || {};
    document.getElementById("swearingIntensity").value = env.swearing_intensity || "off";
    document.getElementById("responseMode").value = env.response_mode || "gm";
    document.getElementById("allowSpeakUp").checked = !!env.allow_proactive_speak_up;
    document.getElementById("enableExtraPlayers").checked = !!env.enable_additional_ai_players;
  }
}

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

  const payload = {
    swearing_intensity: swearing,
    response_mode: responseMode,
    allow_proactive_speak_up: allowSpeakUp,
    enable_additional_ai_players: enableExtraPlayers,
  };
  if (key) payload.openai_api_key = key;

  const res = await requestJson("/api/env", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.envFormDirty = false;
  showToast(res.message || "Zapisano");
  document.getElementById("openaiKey").value = "";
  await refreshState();
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

  document.getElementById("swearingIntensity").addEventListener("change", markEnvDirty);
  document.getElementById("responseMode").addEventListener("change", markEnvDirty);
  document.getElementById("allowSpeakUp").addEventListener("change", markEnvDirty);
  document.getElementById("enableExtraPlayers").addEventListener("change", markEnvDirty);

  document.getElementById("refreshStateBtn").addEventListener("click", async () => {
    await refreshState();
    await loadGameFiles();
    await loadSessions();
  });

  document.getElementById("startBotBtn").addEventListener("click", startBot);
  document.getElementById("stopBotBtn").addEventListener("click", stopBot);
  document.getElementById("validateBtn").addEventListener("click", validateSetup);
  document.getElementById("ingestBtn").addEventListener("click", ingestFiles);
  document.getElementById("saveEnvBtn").addEventListener("click", saveEnv);

  document.getElementById("loadCharacterBtn").addEventListener("click", loadCharacter);
  document.getElementById("saveCharacterBtn").addEventListener("click", async () => {
    try {
      await saveJsonFromEditor("characterJson", "/api/character");
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
      if (resetTargetName === "character") document.getElementById("characterJson").value = "{}";
      if (resetTargetName === "personality") document.getElementById("personalityJson").value = "{}";
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
  await Promise.all([refreshState(), loadCharacter(), loadPersonality(), loadGameFiles(), loadSessions()]);
  setInterval(refreshState, 4000);
}

bootstrap().catch((err) => {
  showToast(`Blad inicjalizacji: ${err.message}`, true);
});
