from contextlib import asynccontextmanager
from pathlib import Path
import time

import cv2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .service import Assistant

ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app):
    app.state.assistant = Assistant(ROOT)
    yield
    app.state.assistant.close()


app = FastAPI(title="离线智能眼镜", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])


@app.middleware("http")
async def local_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in {"http://127.0.0.1:8765", "http://localhost:8765"}:
        return Response("Only the local application may control devices", status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "glasses/ui.html").read_text(encoding="utf-8")


@app.get("/api/status")
def status(request: Request):
    a = request.app.state.assistant
    try:
        vlm_ready = a.vlm.ready()
    except Exception:
        vlm_ready = False
    return {"vlm_ready": vlm_ready, "camera_running": a.camera.is_running(), "camera_error": a.camera.error, "sensor_source":a.config["sensor_source"], "sensor_status":a.transport.status() if a.transport else None, "voice_phase": a.voice.phase, "voice_error": a.voice.error, "transcript": a.voice.last_transcript, "wake_phrase": a.config["wake_phrase"], "database_configured": a.people.path.is_file(), "gallery": a.gallery.status(), "face_model": "ArcFace MobileFaceNet 512D", "audio_cache_pending": a.prewarmer.pending.unfinished_tasks, "audio_cache_error": a.prewarmer.error, "busy": a.query_lock.locked(), "last_result": a.last_result}


class DeviceAction(BaseModel):
    enabled: bool


@app.post("/api/camera")
def camera(action: DeviceAction, request: Request):
    a = request.app.state.assistant
    if action.enabled:
        a.camera.start()
    else:
        a.voice.stop()
        a.camera.stop()
    return {"enabled": action.enabled}


@app.get("/api/frame")
def frame(request: Request):
    try:
        image, _ = request.app.state.assistant.camera.snapshot()
        ok, jpeg = cv2.imencode(".jpg", image)
        if not ok:
            raise ValueError("画面编码失败")
        return Response(jpeg.tobytes(), media_type="image/jpeg")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/voice")
def voice(action: DeviceAction, request: Request):
    a = request.app.state.assistant
    if action.enabled:
        try:
            a.camera.snapshot()
        except ValueError as exc:
            raise HTTPException(409, "请先启动摄像头并等待画面就绪") from exc
        try:
            a.voice.start()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    else:
        a.voice.stop()
    return {"enabled": action.enabled}


class Question(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    speak: bool = True
    mode: str = "adaptive"


@app.post("/api/ask")
def ask(question: Question, request: Request):
    try:
        return request.app.state.assistant.ask(question.text, speak=question.speak, mode=question.mode)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/gallery/sync")
def sync_gallery(request: Request):
    return request.app.state.assistant.gallery.sync_once()
