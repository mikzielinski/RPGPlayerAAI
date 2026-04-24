"""Scan data/game_files/, parse supported formats, build/update Chroma vectorstore."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    UnstructuredExcelLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

from rpg_player import config
from rpg_player.session import game_detector

_SUPPORTED = {".docx", ".pdf", ".xlsx"}
_MTIME_CACHE = "data/chroma_db/.mtime_cache.json"
_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 100
_CACHE_VERSION = f"chunk_{_CHUNK_SIZE}_{_CHUNK_OVERLAP}"


def _load_mtime_cache() -> dict:
    try:
        with open(_MTIME_CACHE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_mtime_cache(cache: dict) -> None:
    Path(_MTIME_CACHE).parent.mkdir(parents=True, exist_ok=True)
    with open(_MTIME_CACHE, "w") as f:
        json.dump(cache, f)


def _files_changed(game_dir: Path, cache: dict) -> bool:
    if cache.get("_version") != _CACHE_VERSION:
        return True
    for p in game_dir.iterdir():
        if p.suffix.lower() in _SUPPORTED:
            mtime = p.stat().st_mtime
            if cache.get(str(p)) != mtime:
                return True
    return False


def _loader_for(path: Path):
    ext = path.suffix.lower()
    if ext == ".docx":
        return Docx2txtLoader(str(path))
    if ext == ".pdf":
        return PyPDFLoader(str(path))
    if ext == ".xlsx":
        return UnstructuredExcelLoader(str(path))
    raise ValueError(f"Unsupported file type: {ext}")


def ingest_game_files(
    game_dir: str = config.GAME_FILES_DIR,
    chroma_dir: str = config.CHROMA_DIR,
) -> Optional[Chroma]:
    """Parse game files and build/return a Chroma vectorstore.

    Returns None if no game files are present.
    """
    game_path = Path(game_dir)
    game_path.mkdir(parents=True, exist_ok=True)

    files = [p for p in game_path.iterdir() if p.suffix.lower() in _SUPPORTED]
    if not files:
        print("[ingest] Brak plikow gry w data/game_files/ - pomijam indeksowanie.")
        return None

    mtime_cache = _load_mtime_cache()
    chroma_path = Path(chroma_dir)

    embeddings = OpenAIEmbeddings(openai_api_key=config.OPENAI_API_KEY)

    if chroma_path.exists() and not _files_changed(game_path, mtime_cache):
        print("[ingest] Baza wektorowa aktualna - wczytuje istniejaca.")
        return Chroma(persist_directory=str(chroma_path), embedding_function=embeddings)

    print("[ingest] Indeksuję pliki gry...")
    all_docs = []
    new_cache: dict[str, float] = {}

    for file_path in files:
        print(f"  -> {file_path.name}")
        loader = _loader_for(file_path)
        docs = loader.load()
        all_docs.extend(docs)
        new_cache[str(file_path)] = file_path.stat().st_mtime

    splitter = RecursiveCharacterTextSplitter(chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP)
    chunks = splitter.split_documents(all_docs)

    chroma_path.mkdir(parents=True, exist_ok=True)
    vectorstore = Chroma.from_documents(
        chunks,
        embeddings,
        persist_directory=str(chroma_path),
    )

    new_cache["_version"] = _CACHE_VERSION
    _save_mtime_cache(new_cache)
    print(f"[ingest] Zaindeksowano {len(chunks)} fragmentów z {len(files)} pliku/ów.")

    # Auto-detect game system/genre from the loaded document texts
    try:
        print("[ingest] Wykrywam typ gry z dokumentów...")
        doc_texts = [d.page_content for d in all_docs if d.page_content.strip()]
        result = game_detector.detect_and_save(doc_texts)
        print(f"[ingest] Typ gry: {result.get('system')} / {result.get('genre')} / {result.get('tone')}")
    except Exception as exc:
        print(f"[ingest] Błąd detekcji typu gry (niekrytyczny): {exc}")

    return vectorstore
