import os

# Absolute path to the rpg_player/ package directory — used to anchor all data paths
# so the bot works regardless of which directory it is launched from.
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_PKG_DIR, "data")

# LLM
CLASSIFIER_MODEL = "gpt-4o-mini"
AGENT_MODEL = "gpt-4o"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# Request timeout for OpenAI calls (seconds). Helps avoid hanging requests.
OPENAI_TIMEOUT_SEC = float(os.environ.get("OPENAI_TIMEOUT_SEC", "35"))
# Max retries inside OpenAI client/SDK wrappers.
OPENAI_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "1"))
# Fine-grained timeouts/retries for each stage.
CLASSIFIER_TIMEOUT_SEC = float(os.environ.get("CLASSIFIER_TIMEOUT_SEC", "12"))
AGENT_TIMEOUT_SEC = float(os.environ.get("AGENT_TIMEOUT_SEC", str(OPENAI_TIMEOUT_SEC)))
AGENT_MAX_RETRIES = int(os.environ.get("AGENT_MAX_RETRIES", str(OPENAI_MAX_RETRIES)))

# OpenAI TTS support (optional, used when TTS_BACKEND == "openai")
OPENAI_TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE", "alloy")
OPENAI_TTS_FORMAT = os.environ.get("OPENAI_TTS_FORMAT", "mp3")
OPENAI_TTS_ALLOWED_FORMATS = {"mp3", "wav", "opus", "flac", "pcm"}
OPENAI_TTS_EMOTION_SPEED = {
    "anger": float(os.environ.get("OPENAI_TTS_SPEED_ANGER", "1.1")),
    "fear": float(os.environ.get("OPENAI_TTS_SPEED_FEAR", "1.12")),
    "joy": float(os.environ.get("OPENAI_TTS_SPEED_JOY", "1.08")),
    "sadness": float(os.environ.get("OPENAI_TTS_SPEED_SADNESS", "0.9")),
    "neutral": float(os.environ.get("OPENAI_TTS_SPEED_NEUTRAL", "1.0")),
}

# STT
WHISPER_MODEL = "base"  # or "small" for better accuracy
SILENCE_THRESHOLD_SEC = float(os.environ.get("SILENCE_THRESHOLD_SEC", "1.5"))
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "pl").strip().lower() or "pl"
WHISPER_ENERGY_THRESHOLD = int(os.environ.get("WHISPER_ENERGY_THRESHOLD", "800"))
WHISPER_INSECURE_SSL = os.environ.get("WHISPER_INSECURE_SSL", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WHISPER_INITIAL_PROMPT = (
    "Sesja RPG. Postacie: mag, wojownik, łotrzyk, kleryk. "
    "Słowa kluczowe: Mistrz Gry, MG, kość, rzut, d20, d6, "
    "trafienie krytyczne, zaklęcie, mana, dungeons, dragons."
)

# Session behaviour
BUFFER_MAX_EXCHANGES = int(os.environ.get("BUFFER_MAX_EXCHANGES", "15"))
SPEAK_UP_COOLDOWN_SEC = 45
RAG_TIMEOUT_SEC = 2.5
MAX_CREATION_QUESTIONS = 5
# After N consecutive WAITs on a question → force MY_TURN
CONSECUTIVE_WAIT_FORCE_THRESHOLD: int = 4
# Exposed in web panel for easier tuning.
BUFFER_MIN_EXCHANGES = 5
BUFFER_MAX_EXCHANGES_LIMIT = 40

# Flag file written by the web panel to request a buffer flush from the running bot.
BUFFER_FLUSH_FLAG = os.path.join(_DATA_DIR, ".flush_buffer_request")
FORCE_TURN_FLAG = os.path.join(_DATA_DIR, ".force_turn_request")
CHAT_QUEUE_FILE = os.path.join(_DATA_DIR, ".chat_queue.jsonl")
CHAT_HISTORY_FILE = os.path.join(_DATA_DIR, "chat_history.jsonl")
# When this file exists the microphone is muted (chat-only mode).
MIC_MUTE_FLAG = os.path.join(_DATA_DIR, ".mic_muted")

# Auto-flush the context window when fill reaches this fraction (0.0–1.0).
# Before flushing, the window is summarised into context_general asynchronously.
BUFFER_FLUSH_THRESHOLD = float(os.environ.get("BUFFER_FLUSH_THRESHOLD", "0.95"))

# Three-tier memory: persistent general context JSON file.
GENERAL_CONTEXT_FILE = os.path.join(_DATA_DIR, "context_general.json")

# Detected game type / genre / intro (set automatically by game_detector).
GAME_TYPE_FILE = os.path.join(_DATA_DIR, "game_type.json")

# Reply control:
# - "manual": bot speaks only after explicit force command ("f")
# - "gm": bot replies when directly addressed by GM/player, otherwise waits
# - "auto": legacy autonomous classifier mode
RESPONSE_MODE = os.environ.get("RESPONSE_MODE", "gm").strip().lower()
if RESPONSE_MODE not in {"manual", "gm", "auto"}:
    RESPONSE_MODE = "gm"

# If true, bot can interrupt with SPEAK_UP in auto mode.
ALLOW_PROACTIVE_SPEAK_UP = os.environ.get("ALLOW_PROACTIVE_SPEAK_UP", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Safety switch for loading ADDITIONAL_PLAYERS.
ENABLE_ADDITIONAL_AI_PLAYERS = os.environ.get("ENABLE_ADDITIONAL_AI_PLAYERS", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# TTS backend: "edge" or "kokoro" or "openai"
TTS_BACKEND = os.environ.get("TTS_BACKEND", "edge").strip().lower()
if TTS_BACKEND not in {"edge", "kokoro", "openai"}:
    TTS_BACKEND = "edge"

# Default voice for selected backend
TTS_VOICE = os.environ.get("TTS_VOICE", "pl-PL-MarekNeural")

# Available voices cycled with 'v' key at runtime
AVAILABLE_VOICES: list[str] = [
    "pl-PL-MarekNeural",   # Polish male (Edge)
    "pl-PL-ZofiaNeural",   # Polish female (Edge)
    "alloy",               # OpenAI TTS
    "verse",               # OpenAI TTS
]

# Emotion → Edge TTS prosody adjustments (rate and pitch)
EMOTION_VOICE_PARAMS: dict[str, dict[str, str]] = {
    "anger":   {"rate": "+15%", "pitch": "+5Hz"},
    "fear":    {"rate": "+20%", "pitch": "+15Hz"},
    "joy":     {"rate": "+10%", "pitch": "+8Hz"},
    "sadness": {"rate": "-15%", "pitch": "-5Hz"},
    "neutral": {"rate": "+0%",  "pitch": "+0Hz"},
}

# Swearing intensity injected into agent system prompt
# Values: "off" | "mild" | "moderate" | "heavy"
SWEARING_INTENSITY: str = os.environ.get("SWEARING_INTENSITY", "off")

# Token warning thresholds (cumulative tokens in current session)
TOKEN_WARN_AT: int = 60_000
TOKEN_CRITICAL_AT: int = 90_000

# Session persistence
SESSIONS_DIR = os.path.join(_DATA_DIR, "sessions")
SESSION_HISTORY_CONTEXT_EXCHANGES: int = 10

# Structured game-state log (JSONL)
GAME_LOG_ENABLED = os.environ.get("GAME_LOG_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
GAME_LOGS_DIR = os.path.join(_DATA_DIR, "game_logs")
GAME_LOG_TAIL_DEFAULT = 80

# Paths (absolute, anchored to rpg_player/data/)
CHARACTER_FILE = os.path.join(_DATA_DIR, "character.json")
PERSONALITY_FILE = os.path.join(_DATA_DIR, "player_personality.json")
GAME_FILES_DIR = os.path.join(_DATA_DIR, "game_files")
CHROMA_DIR = os.path.join(_DATA_DIR, "chroma_db")
SECRETS_DIR = os.path.join(_DATA_DIR, "secrets")

# Cooldown overrides keyed by talk_frequency value from personality JSON
COOLDOWN_BY_FREQUENCY = {
    "często": 30,
    "umiarkowanie": 45,
    "rzadko ale trafnie": 90,
}

# Additional AI players. Each entry: {"personality_file": "...", "character_file": "..."}
# Example: [{"personality_file": "data/player2_personality.json", "character_file": "data/character2.json"}]
ADDITIONAL_PLAYERS: list[dict] = []

# Discord integration (MVP)
DISCORD_ENABLED = os.environ.get("DISCORD_ENABLED", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
DISCORD_TEXT_CHANNEL_ID = os.environ.get("DISCORD_TEXT_CHANNEL_ID", "").strip()
DISCORD_VOICE_CHANNEL_ID = os.environ.get("DISCORD_VOICE_CHANNEL_ID", "").strip()
# When True, skip TTS and microphone — bot communicates via Discord text only.
# Defaults to True when DISCORD_ENABLED is set (can be overridden to 0 for hybrid voice+Discord).
DISCORD_TEXT_ONLY = os.environ.get("DISCORD_TEXT_ONLY", "1" if os.environ.get("DISCORD_ENABLED", "0") in {"1", "true", "yes", "on"} else "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
