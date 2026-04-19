"""
FastAPI application — chat, voice, and admin APIs.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote as urlquote

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from admin import AdminSession, RuntimeConfig, verify_password
from admin.auth import admin_configured
from agent import Agent
from extraction import extract_from_upload, format_for_agent, merge_into_session
from llm import ModelRouter
from rag import VectorStore, ingest_bytes, seed_defaults
from voice import VoiceService


DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
KB_STORE_PATH = DATA_DIR / "kb.json"
CONFIG_STORE_PATH = DATA_DIR / "config.json"
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


vector_store = VectorStore(KB_STORE_PATH)
seed_defaults(vector_store)
runtime_config = RuntimeConfig(CONFIG_STORE_PATH)
model_router = ModelRouter(runtime_config)
voice_service = VoiceService(runtime_config, model_router)
admin_sessions = AdminSession()
agent = Agent(vector_store, runtime_config, model_router)

# In-memory chat sessions
sessions: dict[str, dict[str, Any]] = {}


app = FastAPI(title="Car Insurance Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class VoiceSettingsRequest(BaseModel):
    output_enabled: bool | None = None
    input_enabled: bool | None = None
    language: str | None = None
    tone: str | None = None
    detail_level: str | None = None
    auto_play: bool | None = None
    interruptible: bool | None = None
    speed: str | None = None
    tts_voice: str | None = None


class ModelSettingsRequest(BaseModel):
    model_family: str | None = None
    task_models: dict[str, str] | None = None


class VoiceTTSRequest(BaseModel):
    text: str
    voice: str = "alloy"
    speed: float = 1.0
    language: str = "english"


class VoiceSpeakRequest(BaseModel):
    message: str
    ux: dict | None = None
    stage: str | None = None
    language: str | None = None
    detail_level: str | None = None
    tone: str | None = None
    query: str | None = None
    voice: str = "alloy"
    speed: float = 1.0


class VoiceGuideRequest(BaseModel):
    message: str
    ux: dict | None = None
    stage: str | None = None
    language: str | None = None
    detail_level: str | None = None
    tone: str | None = None
    query: str | None = None


class VoiceIntentRequest(BaseModel):
    transcript: str
    message: str | None = None
    ux: dict | None = None
    stage: str | None = None


def _require_admin(token: str | None) -> None:
    if not admin_sessions.validate(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _session_for(session_id: str | None) -> tuple[str, dict[str, Any]]:
    sid = session_id or str(uuid.uuid4())
    if sid not in sessions:
        sessions[sid] = {"history": [], "data": {}}
    return sid, sessions[sid]


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    session_id, session = _session_for(req.session_id)

    async def generate():
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
    session_id, session = _session_for(req.session_id)
    final = {"response": "", "ux": None}
    async for evt in agent.stream(req.message, session["history"], session["data"]):
        if evt["type"] == "final":
            final = {"response": evt["text"], "ux": evt.get("ux")}
        elif evt["type"] == "error":
            raise HTTPException(status_code=500, detail=evt["text"])
    return {"session_id": session_id, **final}


@app.post("/api/chat/upload/stream")
async def chat_upload_stream(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
    doc_hint: str | None = Form(None),
):
    sid, session = _session_for(session_id)
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    filename = file.filename or "upload"

    async def generate():
        yield f"event: session\ndata: {json.dumps({'session_id': sid})}\n\n"
        yield f"event: progress\ndata: {json.dumps({'type': 'progress', 'text': f'Reading {filename}...'})}\n\n"
        try:
            extracted = await extract_from_upload(
                data,
                file.content_type,
                filename,
                model_router,
                doc_hint,
            )
        except ValueError as exc:
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"
            return
        except RuntimeError as exc:
            err_text = f"Couldn't read the document: {exc}"
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'text': err_text})}\n\n"
            return

        applied = merge_into_session(session["data"], extracted)
        synthetic = format_for_agent(filename, extracted, applied)
        summary_bits = [f"{key}: {value}" for key, value in applied.items()]
        summary = ", ".join(summary_bits[:3]) if summary_bits else "no fields readable"
        yield f"event: progress\ndata: {json.dumps({'type': 'progress', 'text': f'Extracted — {summary}'})}\n\n"

        try:
            async for evt in agent.stream(synthetic, session["history"], session["data"]):
                yield f"event: {evt['type']}\ndata: {json.dumps(evt)}\n\n"
        except Exception as exc:
            err = {"type": "error", "text": str(exc)}
            yield f"event: error\ndata: {json.dumps(err)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/reset")
async def reset_session(session_id: str | None = None):
    if session_id and session_id in sessions:
        del sessions[session_id]
    return {"status": "ok"}


@app.get("/api/health")
async def health():
    return {"status": "healthy", "admin_configured": admin_configured()}


@app.get("/api/runtime/public")
async def public_runtime():
    return runtime_config.public_snapshot()


@app.post("/api/voice/tts")
async def voice_tts(req: VoiceTTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    try:
        audio = await model_router.synthesize_speech(
            text=req.text[:2000],
            voice=req.voice,
            speed=req.speed,
            language=req.language,
        )
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"TTS unavailable: {exc}") from exc


@app.post("/api/voice/speak")
async def voice_speak(req: VoiceSpeakRequest):
    """Merged guide + TTS: one round-trip, streams audio back as chunked mp3."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    # Step 1 — get AI-generated spoken summary (fast, cached)
    try:
        guide = await voice_service.guide(
            message=req.message,
            ux=req.ux,
            stage=req.stage,
            language=req.language,
            detail_level=req.detail_level,
            tone=req.tone,
            query=req.query,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    spoken = (guide.get("text") or "").strip()
    if not spoken:
        raise HTTPException(status_code=204, detail="Nothing to speak")

    lang = req.language or "english"

    # Step 2 — stream TTS audio back to client (no extra RTT vs separate /tts call)
    async def audio_stream():
        try:
            async for chunk in model_router.stream_speech(
                text=spoken[:2000],
                voice=req.voice,
                speed=req.speed,
                language=lang,
            ):
                yield chunk
        except Exception:
            return

    return StreamingResponse(
        audio_stream(),
        media_type="audio/mpeg",
        headers={"X-Voice-Text": urlquote(spoken[:300])},
    )


@app.post("/api/voice/guide")
async def voice_guide(req: VoiceGuideRequest):
    try:
        return await voice_service.guide(
            message=req.message,
            ux=req.ux,
            stage=req.stage,
            language=req.language,
            detail_level=req.detail_level,
            tone=req.tone,
            query=req.query,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/voice/intent")
async def voice_intent(req: VoiceIntentRequest):
    try:
        return await voice_service.classify(
            transcript=req.transcript,
            message=req.message,
            ux=req.ux,
            stage=req.stage,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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


@app.get("/api/admin/config")
async def get_config(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    return {**runtime_config.snapshot(), "kb_stats": vector_store.stats()}


@app.post("/api/admin/style")
async def set_style(req: StyleRequest, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    try:
        runtime_config.update_style(req.style)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return runtime_config.snapshot()


@app.post("/api/admin/feature")
async def toggle_feature(req: FeatureToggleRequest, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    try:
        runtime_config.toggle_feature(req.feature, req.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return runtime_config.snapshot()


@app.post("/api/admin/voice")
async def update_voice(req: VoiceSettingsRequest, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    try:
        runtime_config.update_voice(**req.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return runtime_config.snapshot()


@app.post("/api/admin/models")
async def update_models(req: ModelSettingsRequest, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    try:
        if req.model_family is not None:
            runtime_config.update_model_family(req.model_family)
        if req.task_models is not None:
            runtime_config.update_task_models(req.task_models)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return runtime_config.snapshot()


@app.post("/api/admin/instructions")
async def add_instruction(req: InstructionRequest, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    block_id = runtime_config.add_instruction(req.title, req.content, req.enabled)
    return {"block_id": block_id, **runtime_config.snapshot()}


@app.patch("/api/admin/instructions/{block_id}")
async def update_instruction(
    block_id: str,
    req: InstructionUpdateRequest,
    x_admin_token: str | None = Header(default=None),
):
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
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    try:
        chunks = ingest_bytes(file.filename, data)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not chunks:
        raise HTTPException(status_code=400, detail="No extractable text in file")

    doc_id = uuid.uuid4().hex[:10]
    vector_store.add_chunks(doc_id=doc_id, doc_name=file.filename, chunks=chunks)

    try:
        (UPLOADS_DIR / f"{doc_id}_{file.filename}").write_bytes(data)
    except Exception:
        pass

    return {
        "doc_id": doc_id,
        "doc_name": file.filename,
        "chunks": len(chunks),
        "stats": vector_store.stats(),
    }


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


frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        target = frontend_dist / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(frontend_dist / "index.html")
