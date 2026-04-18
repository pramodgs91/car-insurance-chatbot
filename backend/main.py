"""
FastAPI application — chat (streaming via SSE) + admin APIs.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import Agent
from rag import VectorStore, ingest_bytes, seed_defaults
from admin import RuntimeConfig, AdminSession, verify_password
from admin.auth import admin_configured


# ── Paths ────────────────────────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
KB_STORE_PATH = DATA_DIR / "kb.json"
CONFIG_STORE_PATH = DATA_DIR / "config.json"
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ── Singletons ───────────────────────────────────────────────────────────────

vector_store = VectorStore(KB_STORE_PATH)
seed_defaults(vector_store)
runtime_config = RuntimeConfig(CONFIG_STORE_PATH)
admin_sessions = AdminSession()
agent = Agent(vector_store, runtime_config)

# In-memory chat sessions
sessions: dict[str, dict] = {}


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="Car Insurance Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class AdminLoginRequest(BaseModel):
    password: str


class StyleRequest(BaseModel):
    style: str


class FeatureToggleRequest(BaseModel):
    feature: str
    enabled: bool


class InstructionRequest(BaseModel):
    title: str
    content: str
    enabled: bool = True


class InstructionUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    enabled: bool | None = None


# ── Chat (SSE streaming) ─────────────────────────────────────────────────────

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    if session_id not in sessions:
        sessions[session_id] = {"history": [], "data": {}}
    session = sessions[session_id]

    async def generate():
        # send session id upfront
        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"
        try:
            async for evt in agent.stream(req.message, session["history"], session["data"]):
                yield f"event: {evt['type']}\ndata: {json.dumps(evt)}\n\n"
        except Exception as exc:
            err = {"type": "error", "text": str(exc)}
            yield f"event: error\ndata: {json.dumps(err)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/chat")
async def chat_non_streaming(req: ChatRequest):
    """Fallback non-streaming endpoint. Consumes the stream and returns final."""
    session_id = req.session_id or str(uuid.uuid4())
    if session_id not in sessions:
        sessions[session_id] = {"history": [], "data": {}}
    session = sessions[session_id]

    final = {"response": "", "ux": None}
    async for evt in agent.stream(req.message, session["history"], session["data"]):
        if evt["type"] == "final":
            final = {"response": evt["text"], "ux": evt.get("ux")}
        elif evt["type"] == "error":
            raise HTTPException(status_code=500, detail=evt["text"])
    return {"session_id": session_id, **final}


@app.post("/api/reset")
async def reset_session(session_id: str | None = None):
    if session_id and session_id in sessions:
        del sessions[session_id]
    return {"status": "ok"}


@app.get("/api/health")
async def health():
    return {"status": "healthy", "admin_configured": admin_configured()}


# ── Admin auth ───────────────────────────────────────────────────────────────

def _require_admin(token: str | None) -> None:
    if not admin_sessions.validate(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/api/admin/login")
async def admin_login(req: AdminLoginRequest):
    if not admin_configured():
        raise HTTPException(
            status_code=503,
            detail="Admin mode is not configured. Set ADMIN_PASSWORD env var to enable.",
        )
    if not verify_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = admin_sessions.issue()
    return {"token": token}


@app.post("/api/admin/logout")
async def admin_logout(x_admin_token: str | None = Header(default=None)):
    if x_admin_token:
        admin_sessions.revoke(x_admin_token)
    return {"status": "ok"}


# ── Admin config ─────────────────────────────────────────────────────────────

@app.get("/api/admin/config")
async def get_config(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    return {
        **runtime_config.snapshot(),
        "kb_stats": vector_store.stats(),
    }


@app.post("/api/admin/style")
async def set_style(req: StyleRequest, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    try:
        runtime_config.update_style(req.style)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return runtime_config.snapshot()


@app.post("/api/admin/feature")
async def toggle_feature(req: FeatureToggleRequest, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    try:
        runtime_config.toggle_feature(req.feature, req.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return runtime_config.snapshot()


@app.post("/api/admin/instructions")
async def add_instruction(req: InstructionRequest, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    block_id = runtime_config.add_instruction(req.title, req.content, req.enabled)
    return {"block_id": block_id, **runtime_config.snapshot()}


@app.patch("/api/admin/instructions/{block_id}")
async def update_instruction(block_id: str, req: InstructionUpdateRequest,
                              x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    ok = runtime_config.update_instruction(block_id, req.title, req.content, req.enabled)
    if not ok:
        raise HTTPException(status_code=404, detail="Instruction not found")
    return runtime_config.snapshot()


@app.delete("/api/admin/instructions/{block_id}")
async def delete_instruction(block_id: str, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    ok = runtime_config.delete_instruction(block_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Instruction not found")
    return runtime_config.snapshot()


# ── Admin knowledge base ─────────────────────────────────────────────────────

@app.get("/api/admin/knowledge")
async def list_knowledge(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    return {"docs": vector_store.list_docs(), "stats": vector_store.stats()}


@app.post("/api/admin/knowledge/upload")
async def upload_knowledge(
    file: UploadFile = File(...),
    x_admin_token: str | None = Header(default=None),
):
    _require_admin(x_admin_token)
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:  # 10 MB
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    try:
        chunks = ingest_bytes(file.filename, data)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not chunks:
        raise HTTPException(status_code=400, detail="No extractable text in file")

    doc_id = uuid.uuid4().hex[:10]
    vector_store.add_chunks(doc_id=doc_id, doc_name=file.filename, chunks=chunks)

    # persist raw upload too
    try:
        (UPLOADS_DIR / f"{doc_id}_{file.filename}").write_bytes(data)
    except Exception:
        pass

    return {"doc_id": doc_id, "doc_name": file.filename, "chunks": len(chunks),
            "stats": vector_store.stats()}


@app.delete("/api/admin/knowledge/{doc_id}")
async def delete_knowledge(doc_id: str, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    removed = vector_store.remove_doc(doc_id)
    if removed == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"removed": removed, "stats": vector_store.stats()}


@app.post("/api/admin/knowledge/test")
async def test_search(q: str, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    return {"results": vector_store.search(q, top_k=5)}


# ── Frontend ─────────────────────────────────────────────────────────────────

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        target = frontend_dist / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(frontend_dist / "index.html")
