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
  Whisper STT ──► Rolling buffer (last 15 exchanges)
     │
     ▼
  Classifier (gpt-4o-mini) ──► WAIT / MY_TURN / SPEAK_UP
     │                              │
     │              ┌───────────────┘
     ▼              ▼
  Behavior chain ──► Injects contextual instructions
     │
     ▼
  Agent (gpt-4o) ──► Polish response
     │
     ▼
  Edge TTS ──► Spoken aloud at the table
```

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

### 4 — Optional web control panel (HTML)

If you prefer controlling the bot through a browser:

```bash
python3 -m rpg_player.webapp
```

Then open:

```
http://localhost:8080
```

The panel lets you:
- start/stop the bot process,
- edit `character.json` and `player_personality.json`,
- upload/delete RAG game files and trigger ingest,
- generate system-specific character sheets from rulebooks with AI,
- edit the character card live during session (JSON + visual card view),
- control Discord bot from web panel (start/stop/send status messages),
- change runtime behavior mode:
  - `manual` — bot speaks only after `f`,
  - `gm` — bot responds only when directly addressed,
  - `auto` — legacy autonomous behavior.

### 5 — Character wizard by game system (rulebook-driven)

In web panel:

1. Upload one or more rulebooks in **Pliki gry (RAG)** (`.pdf`, `.docx`, `.xlsx`).
2. Open **Kreator postaci AI (na podstawie podrecznika)**.
3. Select:
   - **System gry** (`auto` or explicit, e.g. DnD5e),
   - **Koncepcja postaci** (brief GM prompt),
   - **Podreczniki** to use as source context.
4. Click **Generuj karte AI**.

The app will:
- detect or use selected game system,
- extract snippets from selected rulebooks,
- generate a complete JSON character sheet,
- save it to `rpg_player/data/character.json`,
- render a readable character card preview in UI.

You can edit this card any time during session and click **Zapisz**.

### 6 — Discord integration (web-managed)

#### Step A: Configure `.env` in panel

In **Konfiguracja .env** set:

```env
DISCORD_ENABLED=1
DISCORD_BOT_TOKEN=your_token
DISCORD_GUILD_ID=your_server_id
DISCORD_TEXT_CHANNEL_ID=your_text_channel_id
DISCORD_VOICE_CHANNEL_ID=your_voice_channel_id
```

Save `.env` in panel.

#### Step B: Start Discord bot from web

Use **Discord - panel zarzadzania botem**:
- **Start Discord bota**
- **Prosba o przedstawienie** (asks users to map player -> character)
- **Wyslij na Discord** (manual GM control message)
- **Odswiez status Discord**

The status panel shows:
- running/connected state,
- active guild/channel names,
- known users,
- recent incoming/outgoing messages,
- last connection error.

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
╔══════════════════════════════════════════════════════════════╗
║  ⚔  RPG AI Player Bot                                       ║
╠══════════════════════════════════════════════════════════════╣
║  🎤 LISTENING   Aldric  ·  Half-Elf Ranger Lv.1             ║
╠══════════════════════╦═══════════════════════════════════════╣
║  ⚔  Rozmowa         ║  📊  Status sesji                     ║
║                      ║                                       ║
║  unknown: Co robimy  ║  Decyzja:    MY_TURN                 ║
║  unknown: Może lewą  ║  Styl:       Taktyk · umiarkowanie   ║
║  ▶ Aldric: Czekaj,   ║  Cooldown:   ████████░░ 12s          ║
║    znam to miejsce.  ║  Zachowania: group_debate, plot_twist ║
║                      ║  Ostatnia:   Czekaj, znam to miejsce ║
╠══════════════════════╩═══════════════════════════════════════╣
║  📋  Dziennik zdarzeń                                        ║
║  12:34:01  Postać 'Aldric' załadowana                        ║
║  12:34:05  Sesja aktywna — cooldown: 45s                     ║
║  12:35:22  Agent wywoływany [MY_TURN]                        ║
║  12:35:25  Odpowiedź: Czekaj, znam to miejsce...             ║
╚══════════════════════════════════════════════════════════════╝
```

**Status indicators:**

| Badge | Meaning |
|---|---|
| `🎤 LISTENING` | Microphone active, waiting for speech |
| `🤔 CLASSIFYING` | Running the fast turn classifier |
| `🔊 SPEAKING` | TTS playing a response |
| `⏱ COOLDOWN` | Waiting out the proactive speech cooldown |
| `📚 INGESTING` | Indexing game documents |
| `💬 ONBOARDING` | Running a setup interview |

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

### Building a custom chain

```python
from rpg_player.behaviors import BehaviorChain
from rpg_player.behaviors.dice_reactions import CriticalHitBehavior
from rpg_player.behaviors.my_behavior import MyBehavior

combat_chain = (
    BehaviorChain()
    .register(CriticalHitBehavior())
    .register(MyBehavior())
)
```

Pass it to `run_agent(behavior_chain=combat_chain)` or swap `DEFAULT_CHAIN` in `main.py`.

---

## ✦ Configuration

All settings live in `rpg_player/config.py`.

| Setting | Default | Description |
|---|---|---|
| `CLASSIFIER_MODEL` | `gpt-4o-mini` | Fast model for turn decisions |
| `AGENT_MODEL` | `gpt-4o` | Full model for responses |
| `WHISPER_MODEL` | `base` | STT size: `tiny` / `base` / `small` / `medium` |
| `SILENCE_THRESHOLD_SEC` | `1.5` | Silence gap that ends an utterance |
| `BUFFER_MAX_EXCHANGES` | `15` | Rolling context window |
| `TTS_BACKEND` | `edge` | `"edge"` (online) or `"kokoro"` (local) |
| `TTS_VOICE` | `pl-PL-MarekNeural` | Voice for Edge TTS |
| `RAG_TIMEOUT_SEC` | `2.5` | Max wait for a rules lookup |

**Cooldown by talk frequency** — set automatically from the personality interview:

| Personality answer | Cooldown |
|---|---|
| `często` | 30 s |
| `umiarkowanie` | 45 s |
| `rzadko ale trafnie` | 90 s |

### Voices

| Voice ID | Character |
|---|---|
| `pl-PL-MarekNeural` | Polish male (default) |
| `pl-PL-ZofiaNeural` | Polish female |

**Kokoro TTS (local, better quality):**
```bash
pip install kokoro-onnx
# Place kokoro-v0_19.onnx and voices.json in rpg_player/data/
```
Then set `TTS_BACKEND = "kokoro"` in `config.py`.

---

## ✦ Resetting

| What to reset | Command |
|---|---|
| Character | `rm rpg_player/data/character.json` |
| Personality | `rm rpg_player/data/player_personality.json` |
| Game document index | `rm -rf rpg_player/data/chroma_db/` |

---

## ✦ Project structure

```
rpgplayeraai/
├── run.sh                       # macOS / Linux launcher (auto-setup)
├── run.bat                      # Windows launcher (auto-setup)
├── requirements.txt
├── .env                         # your OPENAI_API_KEY (not committed)
└── rpg_player/
    ├── main.py                  # entry point — startup + session loop
    ├── config.py                # all tunable constants
    │
    ├── behaviors/               # ✦ pluggable behavior system
    │   ├── __init__.py          #   BehaviorChain + DEFAULT_CHAIN
    │   ├── base.py              #   Behavior ABC + BehaviorContext
    │   ├── dice_reactions.py    #   crit hit / fail / good roll
    │   ├── plot_reactions.py    #   plot twist / emotional scene
    │   ├── uncertainty.py       #   rules uncertainty framing
    │   ├── group_dynamics.py    #   group debate participation
    │   └── silence_filler.py    #   break DM silence
    │
    ├── onboarding/
    │   ├── file_ingest.py       # parse docs → Chroma RAG index
    │   ├── character_loader.py  # load character.json
    │   ├── character_creator.py # voice interview → character sheet
    │   ├── personality_loader.py
    │   └── personality_creator.py
    │
    ├── session/
    │   ├── listener.py          # Whisper STT + rolling buffer
    │   ├── classifier.py        # fast LLM: WAIT / MY_TURN / SPEAK_UP
    │   ├── agent.py             # LangChain two-layer agent
    │   └── rag.py               # human-paced async RAG lookup
    │
    ├── tts/
    │   └── speaker.py           # Edge TTS / Kokoro abstraction
    │
    └── ui/
        └── dashboard.py         # Rich live terminal dashboard
```

---

## ✦ Troubleshooting

**Bot does not speak**
- Check system audio output is not muted
- Confirm `edge-tts` installed: `pip install edge-tts`
- Edge TTS requires internet — check connectivity

**Whisper doesn't transcribe**
- Confirm `ffmpeg` installed and on PATH: `ffmpeg -version`
- Try a larger model: `WHISPER_MODEL = "small"` in `config.py`
- Check your microphone is the system default input

**OpenAI errors / rate limits**
- Verify `OPENAI_API_KEY` is set and has credits
- For testing, set `AGENT_MODEL = "gpt-4o-mini"` to reduce cost

**Bot speaks too often or not enough**
- Re-run personality interview: `rm rpg_player/data/player_personality.json`
- Or override directly: `SPEAK_UP_COOLDOWN_SEC = 60` in `config.py`

**Re-indexing is slow**
- Only happens when files in `data/game_files/` change
- Subsequent runs load the existing index instantly

**Kokoro model not found**
- Download `kokoro-v0_19.onnx` + `voices.json` → place in `rpg_player/data/`
- Or switch back: `TTS_BACKEND = "edge"`

---

```
  "Chyba było coś o tym w podręczniku, daj mi chwilę..."
                                        — Aldric, prawdopodobnie
```
