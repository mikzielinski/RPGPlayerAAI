#!/usr/bin/env python3
"""Post-install validation - checks API key, model access, and required packages."""
import os
import sys
import platform

# Enable ANSI colors on Windows 10+ cmd.exe
if platform.system() == "Windows":
    os.system("")

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; RST = "\033[0m"

_ok   = lambda m: print(f"  {G}[OK]{RST}  {m}")
_fail = lambda m: print(f"  {R}[ERR]{RST} {m}")
_warn = lambda m: print(f"  {Y}[WARN]{RST} {m}")
_info = lambda m: print(f"  {C}-> {RST} {m}", flush=True)

REQUIRED_PACKAGES = [
    ("openai",        "openai"),
    ("langchain",     "langchain"),
    ("chromadb",      "chromadb"),
    ("edge_tts",      "edge-tts"),
    ("whisper",       "openai-whisper"),
    ("sounddevice",   "sounddevice"),
    ("rich",          "rich"),
    ("pydantic",      "pydantic"),
]

def check_packages() -> bool:
    print(f"\n{B}[1/3] Checking installed packages...{RST}")
    all_ok = True
    for module, package in REQUIRED_PACKAGES:
        try:
            __import__(module)
            _ok(package)
        except ImportError:
            _fail(f"{package} not installed")
            all_ok = False
    return all_ok

def check_api_key() -> bool:
    print(f"\n{B}[2/3] Checking API key format...{RST}")
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        _fail("OPENAI_API_KEY is empty")
        return False
    if not (key.startswith("sk-") or key.startswith("sk-proj-")):
        _warn(f"Key doesn't look like a standard OpenAI key (got: {key[:8]}...)")
        _warn("Continuing anyway - the connection test will confirm.")
    else:
        _ok(f"Key format OK  ({key[:8]}...{key[-4:]})")
    return True

def check_connection() -> bool:
    print(f"\n{B}[3/3] Testing OpenAI connection...{RST}")
    try:
        from openai import OpenAI, AuthenticationError, PermissionDeniedError
    except ImportError:
        _fail("openai package not installed - run setup again")
        return False

    key = os.environ.get("OPENAI_API_KEY", "").strip()
    _info("Connecting to OpenAI API (this takes a few seconds)...")

    try:
        client = OpenAI(api_key=key)
        models_page = client.models.list()
        model_ids = [m.id for m in models_page.data]
    except AuthenticationError:
        _fail("Authentication failed - API key is invalid or revoked.")
        print(f"       Get a new key at: {C}https://platform.openai.com/api-keys{RST}")
        return False
    except PermissionDeniedError:
        _fail("Permission denied - check your organisation / billing settings.")
        return False
    except Exception as e:
        _fail(f"Cannot reach OpenAI: {e}")
        print(f"       Check your internet connection and try again.")
        return False

    _ok("OpenAI API reachable")

    needs = {"gpt-4o": False, "gpt-4o-mini": False}
    for mid in model_ids:
        if "gpt-4o-mini" in mid:
            needs["gpt-4o-mini"] = True
        elif "gpt-4o" in mid:
            needs["gpt-4o"] = True

    all_ok = True
    for model, found in needs.items():
        if found:
            _ok(f"{model} available")
        else:
            _warn(f"{model} not found in your account - check API plan / tier")
            all_ok = False

    return all_ok

def main() -> int:
    print(f"\n{B}{C}{'-'*44}{RST}")
    print(f"{B}{C}  Setup Validation - RPG AI Player Bot{RST}")
    print(f"{B}{C}{'-'*44}{RST}")

    pkg_ok  = check_packages()
    key_ok  = check_api_key()
    conn_ok = check_connection() if key_ok else False

    print()
    if pkg_ok and key_ok and conn_ok:
        print(f"  {G}{B}All checks passed. Ready to play!{RST}")
        return 0
    elif key_ok and conn_ok:
        print(f"  {Y}{B}Setup complete with warnings - some packages may be missing.{RST}")
        return 0
    else:
        print(f"  {R}{B}Setup incomplete - fix the errors above and run again.{RST}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
