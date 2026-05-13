"""
OmniDub FastAPI app.

Endpoints:
  POST /api/dub         — upload video + options, returns {job_id}
  GET  /api/stream/{id} — SSE stream of progress events
  GET  /api/download/{id} — final MP4
  GET  /                 — static web UI
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pipeline.orchestrator import DubJob, run_dub, LANG_NAMES

load_dotenv()

app = FastAPI(title="OmniDub", version="1.0.0")

JOBS_DIR = Path(os.getenv("OMNIDUB_WORKDIR", "/tmp/omnidub"))
JOBS_DIR.mkdir(parents=True, exist_ok=True)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

JOBS: dict[str, dict] = {}  # job_id -> {"events": asyncio.Queue, "workdir": Path, "status": str}


@app.post("/api/dub")
async def start_dub(
    video: UploadFile = File(...),
    target_lang: str = Form("id"),
    burn_subtitles: bool = Form(False),
    voice_mode: str = Form("clone"),  # "clone" | "builtin"
    builtin_voice: str = Form("Chloe"),
):
    if target_lang not in LANG_NAMES:
        raise HTTPException(400, f"unsupported target_lang {target_lang}")

    job_id = uuid.uuid4().hex[:12]
    workdir = JOBS_DIR / job_id
    workdir.mkdir(parents=True, exist_ok=True)

    src_path = workdir / (video.filename or "input.mp4")
    with src_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    queue: asyncio.Queue = asyncio.Queue()
    JOBS[job_id] = {"queue": queue, "workdir": workdir, "status": "running", "output": None}

    job = DubJob(
        src_video=src_path,
        target_lang=target_lang,
        workdir=workdir,
        burn_subtitles=burn_subtitles,
        built_in_voice=builtin_voice if voice_mode == "builtin" else None,
    )

    async def _run():
        try:
            async for evt in run_dub(job):
                await queue.put(evt)
                if evt["stage"] == "done":
                    JOBS[job_id]["status"] = "done"
                    JOBS[job_id]["output"] = evt["output"]
                elif evt["stage"] == "error":
                    JOBS[job_id]["status"] = "error"
        except Exception as exc:
            await queue.put({"stage": "error", "reason": str(exc)})
            JOBS[job_id]["status"] = "error"
        finally:
            await queue.put(None)  # sentinel

    asyncio.create_task(_run())
    return {"job_id": job_id}


@app.get("/api/stream/{job_id}")
async def stream(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")

    async def gen():
        while True:
            evt = await job["queue"].get()
            if evt is None:
                break
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/download/{job_id}")
async def download(job_id: str):
    job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "not ready")
    return FileResponse(job["output"], filename="omnidub_output.mp4", media_type="video/mp4")


@app.get("/api/health")
async def health():
    return {"ok": True, "base_url": os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"), "has_key": bool(os.getenv("MIMO_API_KEY"))}


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), reload=False)
