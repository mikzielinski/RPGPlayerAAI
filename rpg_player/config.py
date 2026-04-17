import os

# Absolute path to the rpg_player/ package directory — used to anchor all data paths
# so the bot works regardless of which directory it is launched from.
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_PKG_DIR, "data")

# LLM
CLASSIFIER_MODEL = "gpt-4o-mini"
AGENT_MODEL = "gpt-4o"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# STT
WHISPER_MODEL = "base"  # or "small" for better accuracy
SILENCE_THRESHOLD_SEC = 1.5

# Session behaviour
BUFFER_MAX_EXCHANGES = 15
SPEAK_UP_COOLDOWN_SEC = 45
RAG_TIMEOUT_SEC = 2.5
MAX_CREATION_QUESTIONS = 5

# TTS backend: "edge" or "kokoro"
TTS_BACKEND = "edge"
TTS_VOICE = "pl-PL-MarekNeural"  # Polish male; alternative: pl-PL-ZofiaNeural (female)

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
