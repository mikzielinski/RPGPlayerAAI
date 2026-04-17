#!/usr/bin/env bash
# RPG AI Player Bot — macOS / Linux launcher
# Full auto-setup: venv, deps, API key prompt, connection validation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

ok()     { echo -e "  ${GREEN}✓${RESET}  $*"; }
info()   { echo -e "  ${CYAN}→${RESET}  $*"; }
warn()   { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
fail()   { echo -e "\n  ${RED}✖  ERROR:${RESET} $*\n" >&2; exit 1; }
step()   { echo -e "\n${BOLD}${CYAN}[$1]${RESET}${BOLD} $2${RESET}"; }

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════╗"
echo -e "║   ⚔   RPG AI Player Bot  — Setup      ║"
echo -e "╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── Step 1 — Load .env ────────────────────────────────────────────────────────
step "1/5" "Loading environment"
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
    ok ".env loaded"
else
    info "No .env file found — will check for API key below"
fi

# ── Step 2 — System checks ────────────────────────────────────────────────────
step "2/5" "System checks"

# Python
if ! command -v python3 &>/dev/null; then
    fail "python3 not found.\n  Install Python 3.10+ from https://python.org"
fi
PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PMAJOR=$(echo "$PYTHON_VER" | cut -d. -f1)
PMINOR=$(echo "$PYTHON_VER" | cut -d. -f2)
if [ "$PMAJOR" -lt 3 ] || { [ "$PMAJOR" -eq 3 ] && [ "$PMINOR" -lt 10 ]; }; then
    fail "Python 3.10+ required — found $PYTHON_VER\n  Install from https://python.org"
fi
ok "Python $PYTHON_VER"

# ffmpeg
if command -v ffmpeg &>/dev/null; then
    ok "ffmpeg found"
else
    warn "ffmpeg not found — Whisper STT will not work"
    echo -e "       ${DIM}Install: brew install ffmpeg  (macOS)"
    echo -e "                sudo apt install ffmpeg  (Ubuntu)"
    echo -e "                sudo dnf install ffmpeg  (Fedora)${RESET}"
fi

# ── Step 3 — Virtual environment & dependencies ───────────────────────────────
step "3/5" "Python environment"

if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    python3 -m venv .venv --without-pip
    ok "Virtual environment created"
fi

source .venv/bin/activate

# Bootstrap pip if missing
if ! python3 -m pip --version &>/dev/null; then
    info "Bootstrapping pip..."
    python3 -m ensurepip --upgrade \
        || fail "Could not bootstrap pip.\n  Try: python3 -m ensurepip --upgrade"
    python3 -m pip install --upgrade pip --quiet
    ok "pip bootstrapped"
fi

# Install / update dependencies
STAMP=".venv/.install_stamp"
NEEDS_INSTALL=0
[ ! -f "$STAMP" ] && NEEDS_INSTALL=1
{ [ -f "$STAMP" ] && [ requirements.txt -nt "$STAMP" ]; } && NEEDS_INSTALL=1

if [ "$NEEDS_INSTALL" -eq 1 ]; then
    info "Installing dependencies — pip will show progress below..."
    echo ""
    python3 -m pip install --upgrade pip --quiet
    python3 -m pip install -r requirements.txt
    echo ""
    touch "$STAMP"
    ok "All dependencies installed"
else
    ok "Dependencies up to date"
fi

# ── Step 4 — API key ──────────────────────────────────────────────────────────
step "4/6" "OpenAI API key"

if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo ""
    warn "OPENAI_API_KEY is not set."
    echo -e "  ${DIM}Get your key from: https://platform.openai.com/api-keys${RESET}"
    echo ""

    # Prompt (hidden input)
    read -r -s -p "  Enter your OpenAI API key: " OPENAI_API_KEY
    echo ""

    if [ -z "$OPENAI_API_KEY" ]; then
        fail "No key entered."
    fi

    export OPENAI_API_KEY

    # Offer to persist it
    echo ""
    read -r -p "  Save key to .env for future runs? [Y/n]: " SAVE_KEY
    if [[ -z "$SAVE_KEY" || "$SAVE_KEY" =~ ^[Yy] ]]; then
        # Preserve any existing non-key lines
        if [ -f .env ]; then
            grep -v "^OPENAI_API_KEY=" .env > .env.tmp && mv .env.tmp .env || true
        fi
        echo "OPENAI_API_KEY=$OPENAI_API_KEY" >> .env
        ok "Key saved to .env"
    fi
fi

ok "OPENAI_API_KEY set"

# ── Step 5 — Validate connection ──────────────────────────────────────────────
step "5/6" "Validating connection"
python3 scripts/validate_setup.py
VALIDATE_EXIT=$?
if [ "$VALIDATE_EXIT" -ne 0 ]; then
    echo ""
    fail "Validation failed — fix the errors above and run again."
fi

# ── Step 6 — Game files ───────────────────────────────────────────────────────
step "6/6" "Game documents"
python3 scripts/setup_game_files.py
if [ $? -ne 0 ]; then
    fail "Game file setup failed unexpectedly."
fi

# ── Launch ─────────────────────────────────────────────────────────────────────
MODE_ARG="${1:-}"
LAUNCH_MODE=""

case "$MODE_ARG" in
    web|--web)
        LAUNCH_MODE="web"
        ;;
    cli|--cli|"")
        LAUNCH_MODE=""
        ;;
    *)
        warn "Unknown mode '$MODE_ARG' (expected: cli|web). Falling back to interactive choice."
        ;;
esac

if [ -z "$LAUNCH_MODE" ]; then
    echo ""
    echo -e "${BOLD}Choose launch mode:${RESET}"
    echo "  1) CLI session (terminal dashboard)"
    echo "  2) Web panel (HTML interface)"
    read -r -p "Select [1/2] (default 1): " MODE_CHOICE
    if [ "$MODE_CHOICE" = "2" ]; then
        LAUNCH_MODE="web"
    else
        LAUNCH_MODE="cli"
    fi
fi

if [ "$LAUNCH_MODE" = "web" ]; then
    WEB_HOST="${RPG_WEB_HOST:-0.0.0.0}"
    WEB_PORT="${RPG_WEB_PORT:-8080}"
    echo ""
    echo -e "${BOLD}${GREEN}Setup complete. Starting web panel...${RESET}"
    echo -e "  ${DIM}Open: http://localhost:${WEB_PORT}${RESET}"
    echo -e "  ${DIM}Press Ctrl+C to stop.${RESET}"
    echo ""
    python3 -m rpg_player.webapp
else
    echo ""
    echo -e "${BOLD}${GREEN}Setup complete. Starting session...${RESET}"
    echo -e "  ${DIM}Press Ctrl+C to end the session.${RESET}"
    echo ""
    python3 -m rpg_player.main
fi
