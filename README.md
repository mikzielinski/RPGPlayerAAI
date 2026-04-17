# RPG AI Player Bot

A Python application that acts as a **human-like AI player** at your tabletop RPG table. It listens via microphone, participates in conversation proactively (not only when called), creates or loads its own character, and uses your uploaded game documents as rulebook memory. All spoken output is in **Polish**.

---

## Table of Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [First run — onboarding](#first-run--onboarding)
- [Starting a session](#starting-a-session)
- [Adding game documents](#adding-game-documents)
- [Voices](#voices)
- [Resetting character or personality](#resetting-character-or-personality)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## How it works

```
Startup
  │
  ├─ Scan data/game_files/ → build RAG index (skipped if up to date)
  ├─ Load player_personality.json → if missing: voice interview (Polish)
  ├─ Load character.json          → if missing: voice interview (Polish)
  │
Session loop
  │
  ├─ Mic → Whisper STT → rolling buffer (last 15 exchanges)
  ├─ Classifier (gpt-4o-mini) → WAIT / MY_TURN / SPEAK_UP
  ├─ if MY_TURN or SPEAK_UP → Agent (gpt-4o) → TTS response
  └─ Enforce cooldown between proactive interruptions
```

The bot operates on **two simultaneous layers**:

| Layer | What it is | Example |
|---|---|---|
| **Player layer** | Reacts as a player — to dice rolls, plot twists, group debates | *"Nie spodziewałem się tego."* |
| **Character layer** | Speaks and acts as the fictional character | *"Aldric milczy i sięga po łuk."* |

---

## Requirements

- Python 3.10 or newer
- A microphone
- An **OpenAI API key** (`gpt-4o` + `gpt-4o-mini` + `text-embedding-*`)
- Internet connection (for Edge TTS and OpenAI API)
- [ffmpeg](https://ffmpeg.org/) installed and available on PATH (required by Whisper)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/mikzielinski/rpgplayeraai.git
cd rpgplayeraai
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `openai-whisper` downloads model weights on first run (~140 MB for `base`). This is automatic.

### 4. Set your OpenAI API key

```bash
export OPENAI_API_KEY="sk-..."   # Linux / macOS
set OPENAI_API_KEY=sk-...        # Windows CMD
$env:OPENAI_API_KEY="sk-..."     # Windows PowerShell
```

---

## Configuration

All settings live in `rpg_player/config.py`. Edit directly — no `.env` file needed beyond the API key.

| Setting | Default | Description |
|---|---|---|
| `CLASSIFIER_MODEL` | `gpt-4o-mini` | Fast model for deciding when to speak |
| `AGENT_MODEL` | `gpt-4o` | Full model for generating responses |
| `WHISPER_MODEL` | `base` | STT model size (`tiny` / `base` / `small` / `medium`) |
| `SILENCE_THRESHOLD_SEC` | `1.5` | Seconds of silence that end an utterance |
| `BUFFER_MAX_EXCHANGES` | `15` | Rolling context window size |
| `SPEAK_UP_COOLDOWN_SEC` | `45` | Default minimum gap between proactive interruptions |
| `TTS_BACKEND` | `edge` | `"edge"` (online, free) or `"kokoro"` (local, better) |
| `TTS_VOICE` | `pl-PL-MarekNeural` | Edge TTS voice (see [Voices](#voices)) |
| `RAG_TIMEOUT_SEC` | `2.5` | Max seconds for a rules lookup before giving up |

**Cooldown by talk frequency** — automatically applied based on the personality interview answer:

| Personality answer | Cooldown |
|---|---|
| `często` | 30 s |
| `umiarkowanie` | 45 s |
| `rzadko ale trafnie` | 90 s |

---

## First run — onboarding

Run from inside the `rpg_player/` directory:

```bash
cd rpg_player
python main.py
```

### Step 1 — Personality interview

If `data/player_personality.json` does not exist the bot will ask **6 questions in Polish** via TTS. Speak your answers aloud — Whisper captures them.

The questions cover:
1. What kind of player should the bot be (enthusiast, tactician, roleplayer…)
2. How often should it speak and whether it can interrupt
3. How it should handle being wrong or uncertain
4. How it should relate to other players
5. What humor level fits the table
6. What behaviours are absolutely forbidden

After the interview the bot confirms and saves `data/player_personality.json`.

### Step 2 — Character creation

If `data/character.json` does not exist the bot asks **5 questions in Polish** shaped by the personality it just learned:

1. What kind of game — fantasy, sci-fi, horror, other?
2. Suggested class or race, or should it surprise you?
3. Tone check — dark and gritty or light and heroic?
4. Personality traits — sarcastic, noble, cowardly?
5. Character name, or should the bot pick one?

The bot then introduces the character in voice and saves `data/character.json`.

> **Both files are only created once.** On subsequent runs the bot loads them instantly and goes straight to the session loop.

---

## Starting a session

```bash
cd rpg_player
python main.py
```

Once onboarding is done (or skipped because files exist) the bot announces it is ready and begins listening. Place your microphone where it can pick up the whole table.

**The bot will:**
- Respond immediately when directly addressed by name (`MY_TURN`)
- Proactively join in when it has something relevant to say (`SPEAK_UP`), respecting the cooldown
- Stay silent when the conversation is not relevant to it (`WAIT`)

**To stop the session:** press `Ctrl+C`.

---

## Adding game documents

Drop `.pdf`, `.docx`, or `.xlsx` files into:

```
rpg_player/data/game_files/
```

The bot scans this folder at startup. If new files are detected it re-indexes everything into a local Chroma vector database (`data/chroma_db/`). If nothing changed, the existing index is loaded instantly.

Supported formats:

| Extension | Example use |
|---|---|
| `.pdf` | Core rulebook, adventure module |
| `.docx` | House rules, setting lore, NPC list |
| `.xlsx` | Spell tables, item lists, encounter tables |

When the bot needs to recall a rule it will **speak a filler phrase first** (e.g. *"Chyba było coś o tym w podręczniku, daj mi chwilę."*) before searching — intentionally human-paced. If the lookup times out it admits uncertainty aloud instead of making something up.

---

## Voices

The bot uses **Edge TTS** by default — no installation required beyond `pip install edge-tts`.

| Voice ID | Language | Character |
|---|---|---|
| `pl-PL-MarekNeural` | Polish | Male (default) |
| `pl-PL-ZofiaNeural` | Polish | Female |

To switch voice, edit `config.py`:

```python
TTS_VOICE = "pl-PL-ZofiaNeural"
```

### Kokoro TTS (local, higher quality)

For fully offline and better-quality audio:

```bash
pip install kokoro-onnx
```

Download the model file `kokoro-v0_19.onnx` and `voices.json` and place them in `rpg_player/data/`. Then set:

```python
TTS_BACKEND = "kokoro"
```

---

## Resetting character or personality

To create a new character, delete (or rename) the file and restart:

```bash
rm rpg_player/data/character.json
```

To redo the personality interview:

```bash
rm rpg_player/data/player_personality.json
```

To force a full re-index of game documents:

```bash
rm -rf rpg_player/data/chroma_db/
```

---

## Project structure

```
rpg_player/
├── main.py                      # Entry point — startup + session loop
├── config.py                    # API keys, model names, tunable constants
├── onboarding/
│   ├── file_ingest.py           # Parse .docx/.pdf/.xlsx → Chroma RAG index
│   ├── character_loader.py      # Load character.json
│   ├── character_creator.py     # Voice interview → generate character sheet
│   ├── personality_loader.py    # Load player_personality.json
│   └── personality_creator.py  # Voice interview → generate player personality
├── session/
│   ├── listener.py              # Whisper STT + rolling buffer
│   ├── classifier.py            # Fast LLM: WAIT / MY_TURN / SPEAK_UP
│   ├── agent.py                 # LangChain agent — two-layer response
│   └── rag.py                   # Human-paced async RAG lookup
├── tts/
│   └── speaker.py               # TTS abstraction (Edge TTS / Kokoro)
└── data/
    ├── character.json           # Auto-created on first run
    ├── player_personality.json  # Auto-created on first run
    ├── game_files/              # Drop rulebooks here before session
    └── chroma_db/               # Auto-generated vector index
```

---

## Troubleshooting

**Bot does not speak / TTS silent**
- Check your system audio output is not muted
- Confirm `edge-tts` is installed: `pip install edge-tts`
- Test internet connectivity (Edge TTS requires it)

**Whisper does not transcribe / always empty**
- Confirm `ffmpeg` is installed: `ffmpeg -version`
- Try a larger model: set `WHISPER_MODEL = "small"` in `config.py`
- Check your microphone is the system default input device

**OpenAI errors / rate limits**
- Verify `OPENAI_API_KEY` is set and has credits
- Reduce cost by switching `AGENT_MODEL = "gpt-4o-mini"` during testing

**Bot speaks too often or not enough**
- During personality interview answer the frequency question with `często`, `umiarkowanie`, or `rzadko ale trafnie` — this sets the cooldown automatically
- Or override directly in `config.py`: `SPEAK_UP_COOLDOWN_SEC = 60`

**Re-indexing is slow**
- Only happens when files in `data/game_files/` change
- Subsequent runs load the existing Chroma index instantly

**Kokoro model not found**
- Download `kokoro-v0_19.onnx` and `voices.json` manually and place in `rpg_player/data/`
- Or switch back to Edge TTS: `TTS_BACKEND = "edge"`
