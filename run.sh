#!/usr/bin/env bash
# RPG AI Player Bot — macOS / Linux launcher
# Handles full setup on first run: venv creation, dependency install, validation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}✓${RESET} $*"; }
info() { echo -e "${CYAN}→${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET} $*"; }
fail() { echo -e "${RED}✖ ERROR:${RESET} $*" >&2; exit 1; }

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════╗"
echo -e "║       RPG AI Player Bot              ║"
echo -e "╚══════════════════════════════════════╝${RESET}"
echo ""

# ── Load .env ──────────────────────────────────────────────────────────────────
if [ -f .env ]; then
    info "Loading .env file..."
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
    ok ".env loaded"
fi

# ── Check Python 3.10+ ─────────────────────────────────────────────────────────
info "Checking Python version..."
if ! command -v python3 &>/dev/null; then
    fail "python3 not found.\nInstall Python 3.10+ from https://python.org"
fi

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VER" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VER" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    fail "Python 3.10+ required — found $PYTHON_VER\nInstall from https://python.org"
fi
ok "Python $PYTHON_VER"

# ── Check ffmpeg (needed by Whisper) ───────────────────────────────────────────
if ! command -v ffmpeg &>/dev/null; then
    warn "ffmpeg not found — Whisper STT will not work."
    echo "  Install: brew install ffmpeg  (macOS)"
    echo "           sudo apt install ffmpeg  (Ubuntu/Debian)"
    echo "           sudo dnf install ffmpeg  (Fedora)"
    echo ""
fi

# ── Create virtual environment if missing ──────────────────────────────────────
if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    python3 -m venv .venv
    ok "Virtual environment created"
fi

source .venv/bin/activate

# ── Install / update dependencies ─────────────────────────────────────────────
STAMP=".venv/.install_stamp"
NEEDS_INSTALL=0

[ ! -f "$STAMP" ] && NEEDS_INSTALL=1
[ -f "$STAMP" ] && [ requirements.txt -nt "$STAMP" ] && NEEDS_INSTALL=1

if [ "$NEEDS_INSTALL" -eq 1 ]; then
    info "Installing dependencies (first run may take a few minutes)..."
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    touch "$STAMP"
    ok "Dependencies installed"
else
    ok "Dependencies up to date"
fi

# ── Validate OpenAI API key ────────────────────────────────────────────────────
if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo ""
    fail "OPENAI_API_KEY is not set.\n\nCreate a .env file in this directory:\n  echo 'OPENAI_API_KEY=sk-...' > .env\n\nOr export it in your shell before running."
fi
ok "OPENAI_API_KEY found"

# ── Ensure data directories exist ─────────────────────────────────────────────
mkdir -p rpg_player/data/game_files

# ── Launch ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Starting session...${RESET}"
echo "Drop game PDFs / DOCX files into:  rpg_player/data/game_files/"
echo "Press Ctrl+C to end the session."
echo ""

cd rpg_player
python main.py
