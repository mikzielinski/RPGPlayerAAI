#!/usr/bin/env python3
"""Interactive game file setup — describe formats, scan folder, confirm, save to .env."""
import os
import sys
import platform
import subprocess
from pathlib import Path

# Enable ANSI on Windows 10+ cmd.exe
if platform.system() == "Windows":
    os.system("")

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"
C = "\033[96m"; B = "\033[1m"; D = "\033[2m"; RST = "\033[0m"

SUPPORTED = {".pdf", ".docx", ".xlsx"}

FORMAT_HELP = [
    (".pdf",  "Core rulebook, adventure module, setting guide"),
    (".docx", "House rules, NPC list, session notes, lore document"),
    (".xlsx", "Spell tables, magic item lists, encounter tables"),
]

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GAME_DIR  = _REPO_ROOT / "rpg_player" / "data" / "game_files"
_ENV_PATH  = _REPO_ROOT / ".env"


# ── Helpers ────────────────────────────────────────────────────────────────────

def scan() -> list[Path]:
    _GAME_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(f for f in _GAME_DIR.iterdir() if f.suffix.lower() in SUPPORTED)


def open_folder() -> None:
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(str(_GAME_DIR))
        elif system == "Darwin":
            subprocess.run(["open", str(_GAME_DIR)], check=True)
        else:
            subprocess.run(["xdg-open", str(_GAME_DIR)], check=True)
    except Exception as e:
        print(f"  {Y}Could not open folder automatically: {e}{RST}")
        print(f"  Open manually: {B}{_GAME_DIR}{RST}")


def save_env(confirmed: bool) -> None:
    """Write GAME_FILES_CONFIRMED=1/0 into .env, preserving other lines."""
    lines: list[str] = []
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            if not line.startswith("GAME_FILES_CONFIRMED="):
                lines.append(line)
    lines.append(f"GAME_FILES_CONFIRMED={'1' if confirmed else '0'}")
    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _size_str(path: Path) -> str:
    n = path.stat().st_size
    return f"{n / 1_048_576:.1f} MB" if n >= 1_000_000 else f"{n / 1024:.0f} KB"


def print_files(files: list[Path]) -> None:
    if not files:
        print(f"  {D}(no supported files found){RST}")
        return
    total = sum(f.stat().st_size for f in files)
    for f in files:
        print(f"  {G}+{RST}  {B}{f.name}{RST}  {D}({_size_str(f)}){RST}")
    total_str = f"{total / 1_048_576:.1f} MB" if total >= 1_000_000 else f"{total / 1024:.0f} KB"
    print(f"\n  {len(files)} file(s)  ·  {total_str} total")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    already_confirmed = os.environ.get("GAME_FILES_CONFIRMED") == "1"

    print(f"\n{B}{C}  Game Document Setup{RST}")
    print(f"  {D}{'─' * 42}{RST}")
    print(f"""
  The bot indexes your RPG files into a local vector database and uses
  them to look up rules, lore, and spells during the session — just like
  a player who actually read the manual.

  {B}Supported formats:{RST}""")
    for ext, desc in FORMAT_HELP:
        print(f"    {G}{ext:6}{RST}  {desc}")
    print(f"""
  {B}Where to put them:{RST}
    {C}{_GAME_DIR}{RST}
""")

    # If previously confirmed, show current state and let user confirm quickly
    if already_confirmed:
        files = scan()
        print(f"  {D}(previously confirmed){RST}  Current state:")
        print_files(files)
        if files:
            print()
            choice = input(f"  Keep these files and continue? [{B}Y{RST}/n/o(pen)]: ").strip().lower()
            if choice in ("", "y"):
                save_env(True)
                print(f"\n  {G}✓{RST}  Confirmed — files will be indexed on startup")
                return 0
            elif choice == "n":
                save_env(False)
                print(f"\n  {Y}⚠{RST}  Skipping — RAG will be disabled this session")
                return 0
            elif choice == "o":
                open_folder()
                input("  Add or remove files, then press Enter to re-scan... ")
                # fall through to main loop below

    # Main interactive loop
    while True:
        files = scan()
        print(f"\n  {B}Current contents of game_files/:{RST}")
        print_files(files)
        print()

        if files:
            print(f"  {B}[Y]{RST}  Use these files  (will be indexed at startup)")
            print(f"  {B}[O]{RST}  Open folder to add/remove files, then re-scan")
            print(f"  {B}[S]{RST}  Skip game files  (RAG will be disabled)")
            choice = input(f"\n  Your choice [Y/o/s]: ").strip().lower()

            if choice in ("", "y"):
                save_env(True)
                print(f"\n  {G}✓{RST}  Confirmed — {len(files)} file(s) will be indexed on startup")
                print(f"  {G}✓{RST}  Saved GAME_FILES_CONFIRMED=1 to .env")
                return 0
            elif choice == "o":
                open_folder()
                input("  Folder opened. Add your files then press Enter to re-scan... ")
            elif choice == "s":
                save_env(False)
                print(f"\n  {Y}⚠{RST}  Skipping — RAG lookup will be disabled this session")
                return 0

        else:
            print(f"  {B}[O]{RST}  Open the folder in your file browser")
            print(f"  {B}[R]{RST}  Re-scan (if you added files in another window)")
            print(f"  {B}[S]{RST}  Skip — continue without game files")
            choice = input(f"\n  Your choice [O/r/s]: ").strip().lower()

            if choice in ("", "o"):
                open_folder()
                input("  Folder opened. Add your files then press Enter to re-scan... ")
            elif choice == "r":
                pass  # loop again
            elif choice == "s":
                save_env(False)
                print(f"\n  {Y}⚠{RST}  Skipping — RAG will be disabled this session")
                return 0


if __name__ == "__main__":
    sys.exit(main())
