"""
Document ingestion: PDF / DOCX / TXT / MD → chunks.
"""
from __future__ import annotations
import io
import re
from pathlib import Path


def _chunk_text(text: str, target: int = 500, overlap: int = 80) -> list[str]:
    """Split text into roughly-target-sized chunks on sentence boundaries."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    # Sentence-ish split
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) < target:
            current = f"{current} {sent}".strip()
        else:
            if current:
                chunks.append(current)
            # Add overlap from previous chunk
            if overlap and current and len(current) > overlap:
                current = current[-overlap:] + " " + sent
            else:
                current = sent
    if current:
        chunks.append(current)
    return [c for c in chunks if len(c) > 30]


def extract_text(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext in (".txt", ".md"):
        return data.decode("utf-8", errors="ignore")
    if ext == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pypdf is required to ingest PDFs") from exc
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if ext in (".docx", ".doc"):
        try:
            from docx import Document  # type: ignore
        except ImportError as exc:
            raise RuntimeError("python-docx is required to ingest DOCX") from exc
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"Unsupported file type: {ext}")


def ingest_bytes(filename: str, data: bytes) -> list[str]:
    """Extract text and return chunks."""
    text = extract_text(filename, data)
    return _chunk_text(text)


def ingest_string(text: str) -> list[str]:
    return _chunk_text(text)
