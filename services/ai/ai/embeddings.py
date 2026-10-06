"""Chunking + embeddings + vector store (ChromaDB with JSONL cosine fallback).

Persistence: ``storage/chroma`` collection ``regulations`` (PLAN.md §2.3).
If chromadb is unavailable or fails to open, a local JSONL store implementing
the same interface (hash embeddings + cosine similarity) is used instead.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

from . import config

log = logging.getLogger(__name__)

DEFAULT_DIM = 256
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_OVERLAP = 200

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "shall", "must",
    "are", "was", "were", "have", "has", "been", "any", "not", "but", "its",
    "into", "per", "via", "any", "all", "may", "can", "will", "upon", "under",
    "within", "thereof", "herein", "a", "an", "of", "to", "in", "on", "or",
    "is", "be", "by", "as", "at", "it", "we", "you", "their", "his", "her",
}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower())
            if len(t) >= 2 and t not in _STOPWORDS]


def embed_text(text: str, dim: int = DEFAULT_DIM) -> list[float]:
    """Deterministic hashed bag-of-words embedding, L2 normalized.

    Offline, dependency-free and stable across runs - the same function backs
    both the JSONL fallback store and (optionally) ChromaDB.
    """
    vec = [0.0] * dim
    counts: dict[str, int] = {}
    for token in tokenize(text):
        counts[token] = counts.get(token, 0) + 1
    for token, count in counts.items():
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[index] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def embed_texts(texts: Iterable[str], dim: int = DEFAULT_DIM) -> list[list[float]]:
    return [embed_text(t, dim=dim) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# chunking
# ---------------------------------------------------------------------------
@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _pack(paragraphs: list[str], chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if not current:
            current = para
        elif len(current) + 2 + len(para) <= chunk_size:
            current = f"{current}\n{para}"
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap > 0 else ""
            current = f"{tail}\n{para}".strip() if tail else para
        if len(current) >= chunk_size:
            chunks.append(current)
            current = ""
    if current.strip():
        chunks.append(current)
    return chunks


def chunk_text(text: str, *, base_id: str, chunk_size: int = DEFAULT_CHUNK_SIZE,
               overlap: int = DEFAULT_OVERLAP,
               metadata: dict[str, Any] | None = None) -> list[Chunk]:
    text = text or ""
    paragraphs = re.split(r"\n\s*\n|\r\n\s*\r\n", text)
    if len(paragraphs) <= 1 and len(text) > chunk_size:
        sentences = re.split(r"(?<=[.;!?])\s+", text)
        paragraphs, buf = [], ""
        for sentence in sentences:
            if len(buf) + len(sentence) <= chunk_size:
                buf = f"{buf} {sentence}".strip()
            else:
                if buf:
                    paragraphs.append(buf)
                buf = sentence
        if buf:
            paragraphs.append(buf)

    pieces = _pack(paragraphs, chunk_size, overlap) or ([text] if text else [])
    base_metadata = dict(metadata or {})
    chunks: list[Chunk] = []
    for index, piece in enumerate(pieces):
        meta = dict(base_metadata)
        meta["chunk_index"] = index
        meta["char_count"] = len(piece)
        chunks.append(Chunk(id=f"{base_id}:{index}", text=piece, metadata=meta))
    return chunks


# ---------------------------------------------------------------------------
# stores
# ---------------------------------------------------------------------------
class VectorStore(Protocol):
    backend: str

    def upsert(self, chunks: list[Chunk]) -> int: ...

    def query(self, text: str, k: int = 5) -> list[tuple[Chunk, float]]: ...

    def count(self) -> int: ...


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in metadata.items()
            if isinstance(v, (str, int, float, bool)) and v is not None}


class ChromaStore:
    """ChromaDB persistent store, collection ``regulations`` (cosine space)."""

    backend = "chroma"

    def __init__(self, persist_dir: Path | str, collection: str = "regulations"):
        import chromadb  # guarded import - may be missing/broken

        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        try:
            self._collection = self._client.get_or_create_collection(
                collection, metadata={"hnsw:space": "cosine"})
        except Exception:
            self._collection = self._client.get_or_create_collection(collection)

    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        embeddings = embed_texts([c.text for c in chunks])
        self._collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[_clean_metadata(c.metadata) for c in chunks],
        )
        return len(chunks)

    def query(self, text: str, k: int = 5) -> list[tuple[Chunk, float]]:
        embedding = embed_text(text)
        result = self._collection.query(
            query_embeddings=[embedding], n_results=k,
            include=["documents", "metadatas", "distances"])
        out: list[tuple[Chunk, float]] = []
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for i, chunk_id in enumerate(ids):
            distance = float(dists[i]) if i < len(dists) else 1.0
            out.append((
                Chunk(id=chunk_id,
                      text=docs[i] if i < len(docs) else "",
                      metadata=dict(metas[i]) if i < len(metas) and metas[i] else {}),
                max(-1.0, min(1.0, 1.0 - distance)),  # cosine distance -> similarity
            ))
        return out

    def count(self) -> int:
        return int(self._collection.count())


class JsonlVectorStore:
    """Fallback store: JSONL persistence + cosine similarity over hash embeddings."""

    backend = "jsonl"

    def __init__(self, persist_dir: Path | str, filename: str = "regulations.jsonl"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.persist_dir / filename
        self._records: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("id"):
                    self._records[record["id"]] = record

    def _flush(self) -> None:
        tmp = self.path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for record in self._records.values():
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        tmp.replace(self.path)

    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        embeddings = embed_texts([c.text for c in chunks])
        for chunk, embedding in zip(chunks, embeddings):
            self._records[chunk.id] = {
                "id": chunk.id,
                "text": chunk.text,
                "metadata": _clean_metadata(chunk.metadata),
                "embedding": embedding,
            }
        self._flush()
        return len(chunks)

    def query(self, text: str, k: int = 5) -> list[tuple[Chunk, float]]:
        probe = embed_text(text)
        scored: list[tuple[Chunk, float]] = []
        for record in self._records.values():
            score = cosine(probe, record.get("embedding") or [])
            scored.append((
                Chunk(id=record["id"], text=record.get("text", ""),
                      metadata=dict(record.get("metadata") or {})),
                score,
            ))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:k]

    def count(self) -> int:
        return len(self._records)


def get_vector_store(persist_dir: Path | str | None = None,
                     collection: str = "regulations") -> VectorStore:
    """ChromaDB when usable, otherwise the JSONL cosine fallback (never raises)."""
    directory = Path(persist_dir) if persist_dir else config.chroma_dir()
    try:
        store = ChromaStore(directory, collection=collection)
        store.count()  # force a round of real I/O
        return store
    except Exception as exc:  # noqa: BLE001 - guarded chroma import/use
        log.warning("ChromaDB unavailable (%s: %s); using JSONL fallback store",
                    type(exc).__name__, exc)
        return JsonlVectorStore(directory)
