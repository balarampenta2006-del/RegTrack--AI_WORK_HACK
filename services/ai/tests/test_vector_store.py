"""Vector store round-trip tests: embed -> query -> found (chroma or fallback)."""

import pytest

from ai import embeddings
from ai.embeddings import (Chunk, JsonlVectorStore, chunk_text, cosine,
                           embed_text, get_vector_store)

DOC_A = ("RBI circular on digital lending and customer KYC norms for NBFCs "
         "and fintech lenders.")
DOC_B = "SEBI circular on mutual fund total expense ratios for asset managers."

IDS = ("reg:1:v2:old:0", "reg:1:v2:new:0")


def _chunks():
    return [
        Chunk(id=IDS[0], text=DOC_A,
              metadata={"regulation_id": 1, "version_no": 1, "source": "RBI"}),
        Chunk(id=IDS[1], text=DOC_B,
              metadata={"regulation_id": 1, "version_no": 2, "source": "SEBI"}),
    ]


def test_embed_text_is_deterministic_and_normalized():
    a = embed_text(DOC_A)
    b = embed_text(DOC_A)
    assert a == b
    assert len(a) == embeddings.DEFAULT_DIM
    assert abs(sum(v * v for v in a) - 1.0) < 1e-6
    assert cosine(a, embed_text(DOC_B)) < cosine(a, a)


def test_chunk_text_creates_metadata_and_unique_ids():
    text = "\n\n".join(f"Paragraph {i} " + "filler words " * 40 for i in range(12))
    chunks = chunk_text(text, base_id="1:v2:new",
                        metadata={"regulation_id": 1, "version_no": 2,
                                  "source": "RBI"})
    assert len(chunks) >= 2
    assert len({c.id for c in chunks}) == len(chunks)
    for chunk in chunks:
        assert chunk.metadata["regulation_id"] == 1
        assert chunk.metadata["source"] == "RBI"
        assert isinstance(chunk.metadata["chunk_index"], int)


def test_jsonl_store_round_trip(tmp_path):
    store = JsonlVectorStore(tmp_path / "chroma")
    assert store.backend == "jsonl"
    assert store.upsert(_chunks()) == 2
    assert store.count() == 2

    hits = store.query("digital lending KYC for NBFC lenders", k=1)
    assert hits, "query returned nothing"
    top_chunk, score = hits[0]
    assert top_chunk.id == IDS[0]
    assert score > 0

    # persistence: a fresh instance must see the same records
    reopened = JsonlVectorStore(tmp_path / "chroma")
    assert reopened.count() == 2
    assert reopened.query("digital lending KYC", k=1)[0][0].id == IDS[0]


def test_chroma_store_round_trip(tmp_path):
    try:
        store = __import__("ai.embeddings", fromlist=["ChromaStore"]).ChromaStore(
            tmp_path / "chroma", collection="regulations")
    except Exception as exc:  # pragma: no cover - guarded optional dependency
        pytest.skip(f"chromadb unavailable: {exc}")

    assert store.backend == "chroma"
    assert store.upsert(_chunks()) == 2
    assert store.count() == 2

    hits = store.query("digital lending KYC for NBFC lenders", k=1)
    assert hits, "query returned nothing"
    top_chunk, score = hits[0]
    assert top_chunk.id == IDS[0]
    assert score > 0
    assert top_chunk.metadata.get("source") == "RBI"


def test_get_vector_store_round_trip(tmp_path):
    store = get_vector_store(tmp_path / "chroma")
    assert store.backend in {"chroma", "jsonl"}
    store.upsert(_chunks())
    hits = store.query("digital lending KYC", k=1)
    assert hits[0][0].id == IDS[0]


def test_get_vector_store_falls_back_when_chroma_broken(tmp_path, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("chromadb exploded")

    monkeypatch.setattr(embeddings, "ChromaStore", _boom)
    store = get_vector_store(tmp_path / "chroma")
    assert store.backend == "jsonl"
    store.upsert(_chunks())
    hits = store.query("digital lending KYC", k=1)
    assert hits[0][0].id == IDS[0]
