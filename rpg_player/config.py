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

# STT
WHISPER_MODEL = "base"  # or "small" for better accuracy
SILENCE_THRESHOLD_SEC = 1.5
WHISPER_LANGUAGE = "pl"
WHISPER_INITIAL_PROMPT = (
    "Sesja RPG. Postacie: mag, wojownik, łotrzyk, kleryk. "
    "Słowa kluczowe: Mistrz Gry, MG, kość, rzut, d20, d6, "
    "trafienie krytyczne, zaklęcie, mana, dungeons, dragons."
)

# Session behaviour
BUFFER_MAX_EXCHANGES = 15
SPEAK_UP_COOLDOWN_SEC = 45
RAG_TIMEOUT_SEC = 2.5
MAX_CREATION_QUESTIONS = 5
# After N consecutive WAITs on a question → force MY_TURN
CONSECUTIVE_WAIT_FORCE_THRESHOLD: int = 4

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

# TTS backend: "edge" or "kokoro"
TTS_BACKEND = "edge"
TTS_VOICE = "pl-PL-MarekNeural"

# Available voices cycled with 'v' key at runtime
AVAILABLE_VOICES: list[str] = [
    "pl-PL-MarekNeural",   # Polish male
    "pl-PL-ZofiaNeural",   # Polish female
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

# Paths (absolute, anchored to rpg_player/data/)
CHARACTER_FILE = os.path.join(_DATA_DIR, "character.json")
PERSONALITY_FILE = os.path.join(_DATA_DIR, "player_personality.json")
GAME_FILES_DIR = os.path.join(_DATA_DIR, "game_files")
CHROMA_DIR = os.path.join(_DATA_DIR, "chroma_db")

# Cooldown overrides keyed by talk_frequency value from personality JSON
COOLDOWN_BY_FREQUENCY = {
    "często": 30,
    "umiarkowanie": 45,
    "rzadko ale trafnie": 90,
}

# Additional AI players. Each entry: {"personality_file": "...", "character_file": "..."}
# Example: [{"personality_file": "data/player2_personality.json", "character_file": "data/character2.json"}]
ADDITIONAL_PLAYERS: list[dict] = []
