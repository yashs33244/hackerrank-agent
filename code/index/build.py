"""Offline index builder — run once before main.py.

Produces:
  index/data/chunks.jsonl      — all contextual chunks
  index/data/embeddings.npy    — Gemini text-embedding-004 vectors
  index/data/bm25_corpus.txt   — (informational, for inspection)

Usage:
  python -m index.build
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
INDEX_DIR = Path(__file__).resolve().parent / "data"
CHUNK_SIZE = 400      # target tokens per chunk (approx 1 token ≈ 4 chars)
CHUNK_OVERLAP = 80
EMBED_BATCH = 20      # Gemini embedding batch size


# ── Chunking ──────────────────────────────────────────────────────────────────

def _domain_from_path(path: Path) -> str:
    parts = path.relative_to(DATA_DIR).parts
    return parts[0] if parts else "unknown"


def _header_from_path(path: Path) -> str:
    parts = path.relative_to(DATA_DIR).parts
    return " > ".join(p.replace("-", " ").replace("_", " ") for p in parts)


def _split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split by markdown headers first, then by size."""
    sections = re.split(r'\n(?=#{1,3} )', text)
    chunks = []
    for section in sections:
        words = section.split()
        if len(words) <= chunk_size:
            if section.strip():
                chunks.append(section.strip())
        else:
            for i in range(0, len(words), chunk_size - overlap):
                chunk = " ".join(words[i:i + chunk_size])
                if chunk.strip():
                    chunks.append(chunk.strip())
    return chunks


def build_chunks() -> list[dict]:
    chunks = []
    chunk_id = 0
    md_files = sorted(DATA_DIR.rglob("*.md"))
    print(f"Found {len(md_files)} markdown files in corpus")

    for path in md_files:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue
        domain = _domain_from_path(path)
        header = _header_from_path(path)
        for chunk_text in _split_into_chunks(text):
            chunks.append({
                "id": chunk_id,
                "source_path": str(path.relative_to(REPO_ROOT)),
                "domain": domain,
                "header": header,
                "text": chunk_text,
            })
            chunk_id += 1

    print(f"Created {len(chunks)} chunks from {len(md_files)} files")
    return chunks


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_chunks(chunks: list[dict]) -> np.ndarray:
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    client = genai.Client(api_key=api_key)

    model = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")
    texts = [c["text"][:2000] for c in chunks]  # keep within token limit
    embeddings = []
    total_batches = (len(texts) + EMBED_BATCH - 1) // EMBED_BATCH

    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        batch_num = i // EMBED_BATCH + 1
        print(f"  Embedding batch {batch_num}/{total_batches} ({len(embeddings)}/{len(texts)} done)...", end="\r")
        result = client.models.embed_content(model=model, contents=batch)
        # result.embeddings is a list of ContentEmbedding objects
        for emb in result.embeddings:
            embeddings.append(emb.values)
        time.sleep(0.05)  # rate limit courtesy

    print(f"\nEmbedded {len(embeddings)} chunks")
    return np.array(embeddings, dtype=np.float32)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    print("Building chunks...")
    chunks = build_chunks()

    chunks_path = INDEX_DIR / "chunks.jsonl"
    with open(chunks_path, "w") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")
    print(f"Saved {len(chunks)} chunks → {chunks_path}")

    print("Embedding chunks with Gemini (this takes a few minutes)...")
    embeddings = embed_chunks(chunks)

    emb_path = INDEX_DIR / "embeddings.npy"
    np.save(str(emb_path), embeddings)
    print(f"Saved embeddings → {emb_path}  shape={embeddings.shape}")

    # Informational BM25 corpus dump
    bm25_path = INDEX_DIR / "bm25_corpus.txt"
    with open(bm25_path, "w") as f:
        for c in chunks:
            f.write(c["text"] + "\n---\n")
    print(f"Saved BM25 corpus → {bm25_path}")
    print("\nIndex build complete.")


if __name__ == "__main__":
    main()
