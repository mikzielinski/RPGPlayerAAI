```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║        ⚔   RPG AI PLAYER BOT   ⚔                               ║
║                                                                  ║
║   "Nie jestem pewien tej zasady... ale wiem, że spróbuję."      ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

> A Python application that joins your tabletop RPG session as a **human-like AI player**.
> It listens via microphone, speaks in Polish, creates its own character, and reacts
> to dice rolls, plot twists, and group debates — just like a real player would.

---

## ✦ What it does

The bot operates on **two simultaneous layers**, just like a real player:

| Layer | Role | Example |
|---|---|---|
| **Player** | Reacts *as a person at the table* | *"Nie spodziewałem się tego."* |
| **Character** | Speaks *in-world as the fictional PC* | *"Aldric sięga po łuk i mruży oczy."* |

**Session flow:**

```
  Mic input
     │
     ▼
  Whisper STT ──► Rolling buffer (context window)
     │                    │
     │                    ▼ (at threshold %)
     │             MemoryManager ──► context_general.json  ←──────┐
     │                    │         (LLM summarisation)           │
     │                    └── flush keeping last utterance ───────┘
     ▼
  Classifier (gpt-4o-mini) ──► WAIT / MY_TURN / SPEAK_UP
     │
     ▼
  Behavior chain ──► Injects contextual instructions
     │
     ▼
  Agent (gpt-4o)
    ├─ system: character + personality + context_general (long-term memory)
    └─ human:  context_window (recent exchanges) + now (last utterance)
     │
     ▼
  Edge TTS / OpenAI TTS / Kokoro ──► Spoken aloud at the table
```

---

## ✦ Three-tier memory

The bot never forgets anything that happened during a session:

| Tier | Content | Lifetime |
|---|---|---|
| **Now** | Last single utterance — the immediate trigger | Current loop tick |
| **Context Window** | Last N exchanges (rolling buffer) | Until flushed |
| **Context General** | LLM-compressed history: NPCs, locations, decisions, notes | Permanent (JSON file) |

When the context window reaches the **auto-flush threshold** (default 95%), the bot
automatically summarises the buffer into `context_general.json` via `gpt-4o-mini`
before flushing. The general memory is injected into every agent call so the bot
always knows the full game history, regardless of how many buffer flushes have occurred.

---

## ✦ Requirements

| Requirement | Notes |
|---|---|
| Python 3.10+ | [python.org](https://python.org) |
| OpenAI API key | `gpt-4o`, `gpt-4o-mini`, embeddings |
| ffmpeg | Required by Whisper STT |
| Microphone | Picks up the whole table |
| Internet | For Edge TTS and OpenAI (Kokoro TTS works offline) |

---

## ✦ Quick start

### 1 — Clone

```bash
git clone https://github.com/mikzielinski/rpgplayeraai.git
cd rpgplayeraai
```

### 2 — Set your API key

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-...
```

### 3 — Launch

**macOS / Linux:**
```bash
./run.sh
```

**Windows:**
```
run.bat
```

> The scripts handle everything automatically on first run:
> virtual environment creation, dependency installation, validation.
> Just set your key and go.

### 4 — Web control panel

Control everything from a browser instead of the terminal:

```bash
python3 -m rpg_player.webapp
```

Open `http://localhost:8080`

---

## ✦ Web panel

The panel has five tabs:

### Panel
- **Health status row** — coloured indicators for bot / API key / character / personality / game files
- **Buffer progress bar** — live fill level of the context window (blue → amber at 60% → red at 90%)
- Start / Stop bot, validate setup, trigger ingest
- **Flush buffer** button — clears the window keeping the last utterance; triggers summarisation

### Konfiguracja
- OpenAI API key (write-only, masked)
- Response mode: `manual` / `gm` / `auto`
- Context window size slider (5–40 exchanges)
- **Buffer flush threshold** slider (50–100%) — auto-flush + summarise at this fill %
- Swearing intensity, proactive speak-up, extra AI players
- TTS backend and voice selection (Edge / OpenAI / Kokoro)

### Postać
- Live JSON editors for `character.json` and `player_personality.json`
- Reset to defaults

### Zasoby
- Upload / delete game files (PDF, DOCX, XLSX)
- Session history browser with per-session detail view
- **Game log table** — sortable / filterable table (click headers to sort ↑↓; filter by event type, actor, or free text)

### Pamięć
- **Context General editor** — view and manually edit `context_general.json` (the bot's long-term memory)
- **Context Window** — live view of what's currently in the rolling buffer
- **Teraz (Now)** — the last utterance the bot sees as its immediate trigger

### Discord
- Token, Guild ID, channel IDs
- Live connection status

---

## ✦ First run — onboarding

On first launch the bot has no character and no personality. It will guide you
through two short voice interviews **entirely in Polish**.

### Step 1 — Personality interview (~2 min)

The bot asks 6 questions to understand how you want it to behave at the table:

1. What player archetype should it be? *(enthusiast / tactician / roleplayer / ...)*
2. How often should it speak — can it interrupt?
3. How does it handle being wrong or uncertain?
4. How should it relate to other players?
5. What humor level fits — dry, warm, absurd, none?
6. Are there any behaviors that are absolutely off-limits?

Answers are saved to `rpg_player/data/player_personality.json`. **Asked once, remembered forever.**

### Step 2 — Character creation (~2 min)

The bot asks 5 questions, shaped by the personality it just learned:

1. What kind of game — fantasy, sci-fi, horror, other?
2. Any class or race in mind, or should it surprise you?
3. Vibe: dark and gritty, or light and heroic?
4. Personality traits — sarcastic? noble? cowardly?
5. Character name, or should the bot pick one?

The bot then introduces itself **in character voice** and saves `rpg_player/data/character.json`.
**Asked once, remembered forever.**

> On all subsequent runs, both files are loaded instantly and the session begins immediately.

---

## ✦ Adding game documents

Drop rulebooks, modules, and lore files into:

```
rpg_player/data/game_files/
```

| Format | Examples |
|---|---|
| `.pdf` | Core rulebook, adventure module |
| `.docx` | House rules, setting lore, NPC list |
| `.xlsx` | Spell tables, item lists, encounter tables |

The bot indexes everything into a local vector database on startup. If nothing changed
since the last run, the existing index loads instantly.

When recalling a rule, the bot **always pauses and speaks a filler phrase first** —
*"Chyba było coś o tym w podręczniku, daj mi chwilę..."* — before returning an answer.
It never looks instant.

---

## ✦ Live dashboard

Once the session starts, a **Rich terminal dashboard** takes over the screen:

```
╔══════════════════════════════════════════════════════════════════╗
║  ⚔  RPG AI Player Bot                                           ║
╠══════════════════════════════════════════════════════════════════╣
║  << LISTENING  Aldric  ·  Half-Elf Ranger Lv.1  ·  MarekNeural ║
╠═══════════════════════════════╦══════════════════════════════════╣
║  Rozmowa przy stole           ║  Status sesji                   ║
║                               ║                                 ║
║  ████████░░░░ 10/15           ║  Decyzja:  MY_TURN              ║
║                               ║  Tryb:     gm — gdy zagadnięty ║
║    unknown: Co robimy?        ║  Bufor:    ████████░░ 10/15     ║
║    unknown: Może lewą stronę  ║  Cooldown: gotowy               ║
║  ▶ Aldric: Czekaj, znam to    ║  Tokeny:   12.4k tokenów        ║
║            miejsce.           ║  Pamięć:   OK  14:22:01  8 fakt.║
║                               ║  Gracze:   Marek, Kasia         ║
║                               ║  Ostatnia: Czekaj, znam to m…  ║
╠═══════════════════════════════╩══════════════════════════════════╣
║  Dziennik zdarzeń                                               ║
║  14:34:01  Postać 'Aldric' załadowana                           ║
║  14:34:05  Sesja aktywna — cooldown: 45s                        ║
║  14:35:22  Agent wywoływany [MY_TURN]                           ║
║  14:35:25  Aldric: Czekaj, znam to miejsce...                   ║
║                                                                 ║
║    [f] wymuś odpowiedź   [v] zmień głos   [q] zakończ          ║
╚══════════════════════════════════════════════════════════════════╝
```

**Status badges:**

| Badge | Meaning |
|---|---|
| `<< LISTENING` | Microphone active, waiting for speech |
| `?? CLASSIFYING` | Running the fast turn classifier |
| `>> SPEAKING` | TTS playing a response |
| `\|\| COOLDOWN` | Waiting out the proactive speech cooldown |
| `** INGESTING` | Indexing game documents |
| `>> ONBOARDING` | Running a setup interview |
| `~~ MEMORIZING` | Saving buffer to long-term memory (background) |
| `!! ERROR` | An error occurred — detail shown in stats panel |
| `[] STOPPED` | Session ended |

When memory summarisation is running in the background a second badge appears in the header: `~~ ZAPISUJE PAMIĘĆ`.

**Buffer panel** border colour changes dynamically:
- Blue — normal fill
- Amber — fill ≥ 60 %
- Red — fill ≥ 90 % with `AUTO-FLUSH wkrótce` warning

**Hotkeys — single keypress, no Enter required:**

| Key | Action |
|---|---|
| `f` | Force the bot to take a turn immediately |
| `v` | Cycle to the next TTS voice |
| `q` or `Esc` | Quit and save the session |

Keys respond on the keypress itself — no need to press Enter. Terminal settings are restored automatically when the session exits.

---

## ✦ Behavior system

Behaviors are **modular, pluggable rules** that inject extra instructions into the agent
before each response. They live in `rpg_player/behaviors/` and are completely independent —
you can add, remove, or reorder them without touching any other code.

### Built-in behaviors

| File | Behavior | Triggers when... |
|---|---|---|
| `dice_reactions.py` | `CriticalHitBehavior` | Buffer mentions nat 20 / critical hit |
| `dice_reactions.py` | `CriticalFailBehavior` | Buffer mentions nat 1 / fumble |
| `dice_reactions.py` | `GoodRollBehavior` | Buffer praises a good roll |
| `plot_reactions.py` | `PlotTwistBehavior` | Buffer contains surprise/revelation language |
| `plot_reactions.py` | `EmotionalSceneBehavior` | Buffer describes a death or sacrifice |
| `uncertainty.py` | `RulesUncertaintyBehavior` | Buffer discusses rules or mechanics |
| `group_dynamics.py` | `GroupDebateBehavior` | Buffer shows group planning or debate |
| `silence_filler.py` | `SilenceFillerBehavior` | DM asked a question with no response |

### Adding a new behavior

**1.** Create `rpg_player/behaviors/my_behavior.py`:

```python
from rpg_player.behaviors.base import Behavior, BehaviorContext

class MyBehavior(Behavior):
    name = "my_behavior"

    def should_trigger(self, ctx: BehaviorContext) -> bool:
        return "dragon" in ctx.last_utterance.lower()

    def get_instruction(self, ctx: BehaviorContext) -> str:
        return (
            "Właśnie pojawił się smok. Twoja postać powinna zareagować "
            "strachem lub podnieceniem — zgodnie z osobowością."
        )
```

**2.** Register it at the bottom of `rpg_player/behaviors/__init__.py`:

```python
from rpg_player.behaviors.my_behavior import MyBehavior
DEFAULT_CHAIN.register(MyBehavior())
```

Done. No other files need to change.

---

## ✦ Configuration

All settings live in `rpg_player/config.py` and can be overridden via `.env`.

### Core

| Setting | Default | Description |
|---|---|---|
| `CLASSIFIER_MODEL` | `gpt-4o-mini` | Fast model for turn decisions |
| `AGENT_MODEL` | `gpt-4o` | Full model for responses |
| `RESPONSE_MODE` | `gm` | `manual` / `gm` / `auto` |

### STT (Whisper)

| Setting | Default | Description |
|---|---|---|
| `WHISPER_MODEL` | `base` | `tiny` / `base` / `small` / `medium` |
| `WHISPER_ENERGY_THRESHOLD` | `800` | Mic energy floor — raise if ambient noise triggers STT |
| `WHISPER_INSECURE_SSL` | `0` | Set `1` on corporate VPNs with self-signed certs |
| `SILENCE_THRESHOLD_SEC` | `1.5` | Silence gap that ends an utterance |

### Memory

| Setting | Default | Description |
|---|---|---|
| `BUFFER_MAX_EXCHANGES` | `15` | Rolling context window size |
| `BUFFER_FLUSH_THRESHOLD` | `0.95` | Auto-flush + summarise at this fill fraction |
| `GENERAL_CONTEXT_FILE` | `data/context_general.json` | Long-term memory file |

### TTS

| Setting | Default | Description |
|---|---|---|
| `TTS_BACKEND` | `edge` | `edge` / `openai` / `kokoro` |
| `TTS_VOICE` | `pl-PL-MarekNeural` | Default voice |
| `OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` | Model for OpenAI TTS |
| `OPENAI_TTS_VOICE` | `alloy` | OpenAI voice name |
| `OPENAI_TTS_FORMAT` | `mp3` | `mp3` / `wav` / `opus` / `flac` / `pcm` |

### Voices

| Voice ID | Character |
|---|---|
| `pl-PL-MarekNeural` | Polish male (Edge, default) |
| `pl-PL-ZofiaNeural` | Polish female (Edge) |
| `alloy` / `verse` / `shimmer` / `echo` / `onyx` | OpenAI TTS |

**Kokoro TTS (local, offline):**
```bash
pip install kokoro-onnx
# Place kokoro-v0_19.onnx and voices.json in rpg_player/data/
```
Then set `TTS_BACKEND=kokoro` in `.env`.

**Cooldown by talk frequency:**

| Personality answer | Cooldown |
|---|---|
| `często` | 30 s |
| `umiarkowanie` | 45 s |
| `rzadko ale trafnie` | 90 s |

---

## ✦ Resetting

| What to reset | CLI | Web panel |
|---|---|---|
| Character | `rm rpg_player/data/character.json` | Postać → Reset domyślny |
| Personality | `rm rpg_player/data/player_personality.json` | Postać → Reset domyślny |
| Game document index | `rm -rf rpg_player/data/chroma_db/` | Zasoby → Wyczyść Chroma DB |
| All sessions | `rm rpg_player/data/sessions/session_*.json` | Zasoby → Usuń wszystkie |
| General memory | `rm rpg_player/data/context_general.json` | Pamięć → Wyczyść pamięć ogólną |

---

## ✦ Project structure

```
rpgplayeraai/
├── run.sh                         # macOS / Linux launcher (auto-setup)
├── run.bat                        # Windows launcher (auto-setup)
├── requirements.txt
├── .env                           # OPENAI_API_KEY etc. (not committed)
└── rpg_player/
    ├── main.py                    # entry point — startup + session loop
    ├── config.py                  # all tunable constants
    ├── webapp.py                  # Flask web control panel
    │
    ├── behaviors/                 # ✦ pluggable behavior system
    │   ├── __init__.py            #   BehaviorChain + DEFAULT_CHAIN
    │   ├── base.py                #   Behavior ABC + BehaviorContext
    │   ├── dice_reactions.py      #   crit hit / fail / good roll
    │   ├── plot_reactions.py      #   plot twist / emotional scene
    │   ├── uncertainty.py         #   rules uncertainty framing
    │   ├── group_dynamics.py      #   group debate participation
    │   └── silence_filler.py      #   break DM silence
    │
    ├── onboarding/
    │   ├── file_ingest.py         #   parse docs → Chroma RAG index
    │   ├── character_loader.py
    │   ├── character_creator.py   #   voice interview → character sheet
    │   ├── personality_loader.py
    │   └── personality_creator.py
    │
    ├── session/
    │   ├── listener.py            #   Whisper STT + rolling buffer
    │   ├── classifier.py          #   fast LLM: WAIT / MY_TURN / SPEAK_UP
    │   ├── agent.py               #   LangChain two-layer agent (3-tier memory)
    │   ├── memory_manager.py      #   context_general: LLM summarisation + persistence
    │   ├── game_log.py            #   structured JSONL session log
    │   ├── session_memory.py      #   between-session persistence
    │   ├── speaker_registry.py    #   player name detection + registry
    │   └── token_tracker.py       #   token usage warnings
    │
    ├── tts/
    │   └── speaker.py             #   Edge TTS / OpenAI TTS / Kokoro abstraction
    │
    ├── integrations/
    │   └── discord_connector.py   #   optional Discord bridge
    │
    ├── ui/
    │   └── dashboard.py           #   Rich live terminal dashboard
    │
    └── web/
        ├── templates/index.html   #   single-page control panel
        └── static/
            ├── app.js
            └── styles.css
```

---

## ✦ Troubleshooting

**Bot does not speak**
- Check system audio output is not muted
- Confirm `edge-tts` installed: `pip install edge-tts`
- Edge TTS requires internet — check connectivity
- For OpenAI TTS: verify `OPENAI_API_KEY` and `TTS_BACKEND=openai` in `.env`

**Whisper doesn't transcribe / transcribes garbage**
- Confirm `ffmpeg` installed and on PATH: `ffmpeg -version`
- Try a larger model: `WHISPER_MODEL=small` in `.env`
- Check your microphone is the system default input
- Raise the energy threshold: `WHISPER_ENERGY_THRESHOLD=1200` in `.env` (filters ambient noise)

**Whisper model download fails (SSL error)**
- Set `WHISPER_INSECURE_SSL=1` in `.env` (bypasses certificate verification on corporate VPNs)
- Or download the model manually to `~/.cache/whisper/`

**Bot stopped responding / stuck in WAIT**
- Click **Przepłucz bufor** in the web panel to clear accumulated noise from the buffer
- Check the context window in the **Pamięć** tab — garbage STT entries will be visible
- Increase `WHISPER_ENERGY_THRESHOLD` to reduce noise pickup

**OpenAI errors / rate limits**
- Verify `OPENAI_API_KEY` is set and has credits
- For testing, set `AGENT_MODEL=gpt-4o-mini` in `.env` to reduce cost

**Bot speaks too often or not enough**
- Re-run personality interview: delete `rpg_player/data/player_personality.json`
- Or set `SPEAK_UP_COOLDOWN_SEC=60` in `.env`

**Hotkeys not responding**
- Hotkeys require a real terminal (not piped/redirected stdin)
- In a piped environment the bot falls back to line-buffered mode: type the key then Enter

**Re-indexing is slow**
- Only happens when files in `data/game_files/` change
- Subsequent runs load the existing index instantly

**Kokoro model not found**
- Download `kokoro-v0_19.onnx` + `voices.json` → place in `rpg_player/data/`
- Or switch back: `TTS_BACKEND=edge`

---

```
  "Chyba było coś o tym w podręczniku, daj mi chwilę..."
                                        — Aldric, prawdopodobnie
```
