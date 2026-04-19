"""Manage GM/player secrets injected into agent system prompt.

Secrets are private notes or files visible only to the AI character —
useful for puzzle clues, private quest hooks, or whispered info from the GM.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rpg_player import config

_INDEX = Path(config.SECRETS_DIR) / "secrets.json"
_FILES_DIR = Path(config.SECRETS_DIR) / "files"

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_TEXT_EXTS = {".txt"}
_PDF_EXTS = {".pdf"}
SUPPORTED_EXTS = _IMAGE_EXTS | _TEXT_EXTS | _PDF_EXTS


def _load() -> list[dict]:
    if not _INDEX.exists():
        return []
    try:
        return json.loads(_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(secrets: list[dict]) -> None:
    _INDEX.parent.mkdir(parents=True, exist_ok=True)
    _INDEX.write_text(json.dumps(secrets, ensure_ascii=False, indent=2), encoding="utf-8")


def list_secrets() -> list[dict]:
    return _load()


def add_text(title: str, text: str, source: str = "gm") -> dict:
    secrets = _load()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "type": "text",
        "title": title or "Sekret",
        "content": text,
        "source": source,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    secrets.append(entry)
    _save(secrets)
    return entry


def add_file(filename: str, content: str, title: str = "", source: str = "gm") -> dict:
    secrets = _load()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "type": "file",
        "title": title or filename,
        "filename": filename,
        "content": content,
        "source": source,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    secrets.append(entry)
    _save(secrets)
    return entry


def delete(secret_id: str) -> bool:
    secrets = _load()
    filtered = [s for s in secrets if s.get("id") != secret_id]
    if len(filtered) == len(secrets):
        return False
    _save(filtered)
    return True


def build_context() -> str:
    """Return formatted block for injection into agent system prompt."""
    secrets = _load()
    if not secrets:
        return ""
    parts = ["=== TAJEMNE INFORMACJE (tylko Ty je znasz — nie zdradzaj wprost) ==="]
    for s in secrets:
        src = s.get("source", "gm").upper()
        title = s.get("title", "Sekret")
        content = s.get("content", "")
        parts.append(f"[{src}] {title}:\n{content}")
    parts.append("(koniec tajemnych informacji)")
    return "\n\n".join(parts)


def extract_file_content(file_path: Path, openai_api_key: str = "") -> str:
    """Extract text content from a secret file (txt/pdf/image)."""
    ext = file_path.suffix.lower()

    if ext in _TEXT_EXTS:
        return file_path.read_text(encoding="utf-8", errors="replace")

    if ext in _PDF_EXTS:
        try:
            from langchain_community.document_loaders import PyPDFLoader
            docs = PyPDFLoader(str(file_path)).load()
            return "\n".join(d.page_content for d in docs if d.page_content.strip())
        except Exception as exc:
            return f"[Błąd odczytu PDF: {exc}]"

    if ext in _IMAGE_EXTS:
        try:
            import base64
            from langchain_core.messages import HumanMessage
            from langchain_openai import ChatOpenAI

            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime = mime_map.get(ext, "image/png")
            img_b64 = base64.b64encode(file_path.read_bytes()).decode()

            llm = ChatOpenAI(
                model="gpt-4o",
                openai_api_key=openai_api_key or config.OPENAI_API_KEY,
                temperature=0.0,
                timeout=30,
            )
            resp = llm.invoke([HumanMessage(content=[
                {
                    "type": "text",
                    "text": (
                        "Opisz zawartość tego obrazu szczegółowo po polsku. "
                        "Jeśli to zagadka lub dokument, wymień wszystkie widoczne wskazówki, "
                        "napisy i szczegóły."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{img_b64}"},
                },
            ])])
            return resp.content
        except Exception as exc:
            return f"[Obraz: {file_path.name}] (opis niedostępny: {exc})"

    return f"[Nieobsługiwany typ pliku: {ext}]"
