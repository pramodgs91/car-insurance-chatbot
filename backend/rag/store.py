"""
Lightweight retrieval store using TF-IDF + cosine similarity.
Zero external services, small dependency footprint. Interface is vector-DB
shaped so it can be swapped for pgvector / Chroma / Pinecone in production.
"""
from __future__ import annotations
import json
import math
import re
import threading
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable


_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text) if len(t) > 1]


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_name: str
    text: str
    source: str = "upload"  # upload | builtin
    tokens: list[str] = field(default_factory=list)
    tf: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class VectorStore:
    """In-memory TF-IDF store with JSON persistence."""

    def __init__(self, persist_path: Path | None = None):
        self.persist_path = persist_path
        self._lock = threading.RLock()
        self._chunks: list[Chunk] = []
        self._df: Counter = Counter()  # document frequency per token
        self._enabled = True
        if persist_path and persist_path.exists():
            self._load()

    # ── ingestion ────────────────────────────────────────────────────────

    def add_chunks(self, doc_id: str, doc_name: str, chunks: Iterable[str], source: str = "upload") -> int:
        """Add multiple chunks for a document. Returns count added."""
        with self._lock:
            added = 0
            for i, text in enumerate(chunks):
                text = text.strip()
                if not text:
                    continue
                tokens = _tokenize(text)
                if not tokens:
                    continue
                tf = dict(Counter(tokens))
                chunk_id = f"{doc_id}::{i}"
                c = Chunk(chunk_id=chunk_id, doc_id=doc_id, doc_name=doc_name,
                          text=text, source=source, tokens=tokens, tf=tf)
                self._chunks.append(c)
                for tok in set(tokens):
                    self._df[tok] += 1
                added += 1
            self._persist()
            return added

    def remove_doc(self, doc_id: str) -> int:
        with self._lock:
            removed = [c for c in self._chunks if c.doc_id == doc_id]
            if not removed:
                return 0
            self._chunks = [c for c in self._chunks if c.doc_id != doc_id]
            for c in removed:
                for tok in set(c.tokens):
                    self._df[tok] -= 1
                    if self._df[tok] <= 0:
                        del self._df[tok]
            self._persist()
            return len(removed)

    def list_docs(self) -> list[dict]:
        with self._lock:
            docs: dict[str, dict] = {}
            for c in self._chunks:
                if c.doc_id not in docs:
                    docs[c.doc_id] = {
                        "doc_id": c.doc_id,
                        "doc_name": c.doc_name,
                        "source": c.source,
                        "chunks": 0,
                    }
                docs[c.doc_id]["chunks"] += 1
            return sorted(docs.values(), key=lambda d: d["doc_name"])

    # ── search ───────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 3, min_score: float = 0.05) -> list[dict]:
        with self._lock:
            if not self._chunks:
                return []
            q_tokens = _tokenize(query)
            if not q_tokens:
                return []
            q_tf = Counter(q_tokens)
            n_docs = len(self._chunks)

            def idf(tok: str) -> float:
                df = self._df.get(tok, 0)
                if df == 0:
                    return 0.0
                return math.log((n_docs + 1) / (df + 1)) + 1

            q_vec = {tok: (1 + math.log(cnt)) * idf(tok) for tok, cnt in q_tf.items()}
            q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1

            scored = []
            for c in self._chunks:
                dot = 0.0
                d_norm_sq = 0.0
                for tok, cnt in c.tf.items():
                    w = (1 + math.log(cnt)) * idf(tok)
                    d_norm_sq += w * w
                    if tok in q_vec:
                        dot += w * q_vec[tok]
                d_norm = math.sqrt(d_norm_sq) or 1
                score = dot / (q_norm * d_norm)
                if score >= min_score:
                    scored.append((score, c))

            scored.sort(key=lambda x: -x[0])
            return [
                {
                    "chunk_id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "doc_name": c.doc_name,
                    "text": c.text,
                    "score": round(s, 3),
                }
                for s, c in scored[:top_k]
            ]

    # ── config ───────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, v: bool) -> None:
        self._enabled = v

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_chunks": len(self._chunks),
                "total_docs": len({c.doc_id for c in self._chunks}),
                "vocab_size": len(self._df),
                "enabled": self._enabled,
            }

    # ── persistence ──────────────────────────────────────────────────────

    def _persist(self) -> None:
        if self.persist_path is None:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with self.persist_path.open("w") as f:
            json.dump({"chunks": [c.to_dict() for c in self._chunks]}, f)

    def _load(self) -> None:
        try:
            with self.persist_path.open() as f:
                data = json.load(f)
            self._chunks = []
            self._df = Counter()
            for c in data.get("chunks", []):
                chunk = Chunk(**c)
                self._chunks.append(chunk)
                for tok in set(chunk.tokens):
                    self._df[tok] += 1
        except Exception:
            self._chunks = []
            self._df = Counter()
