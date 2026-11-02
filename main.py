import os
import json
import uuid
import shutil
import asyncio
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = BASE_DIR / "processed"
UPLOAD_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Video Watermark Remover")

JOBS = {}

def run_cmd(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "Command failed")
    return p.stdout

def get_video_meta(path: str):
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path)
    ]
    meta = json.loads(run_cmd(cmd))
    v = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v:
        raise ValueError("Video stream tidak ditemukan atau format file rusak")
    fps_val = v.get("avg_frame_rate", "30/1")
    if "/" in fps_val:
        num, den = fps_val.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 30.0
    else:
        fps = float(fps_val) if fps_val else 30.0
    duration = float(v.get("duration") or meta.get("format", {}).get("duration") or 0.0)
    has_audio = any(s.get("codec_type") == "audio" for s in meta.get("streams", []))
    return {
        "width": int(v["width"]),
        "height": int(v["height"]),
        "fps": fps,
        "duration": duration,
        "has_audio": has_audio
    }

def process_watermark(job_id: str, input_path: str, output_path: str,
                      x: int, y: int, w: int, h: int, mode: str):
    try:
        JOBS[job_id]["status"] = "processing"
        meta = get_video_meta(input_path)
        vw, vh = meta["width"], meta["height"]

        # Clamp box agar tidak keluar frame
        x = max(1, min(x, vw - 2))
        y = max(1, min(y, vh - 2))
        w = max(2, min(w, vw - x - 1))
        h = max(2, min(h, vh - y - 1))

        if mode == "delogo":
            vf = f"delogo=x={x}:y={y}:w={w}:h={h}"
        elif mode == "blur":
            vf = f"split[a][b];[b]crop={w}:{h}:{x}:{y},boxblur=luma_radius=15:luma_power=3[clean];[a][clean]overlay={x}:{y}"
        elif mode == "pixelate":
            vf = f"split[a][b];[b]crop={w}:{h}:{x}:{y},scale=iw/16:ih/16,scale={w}:{h}:flags=neighbor[clean];[a][clean]overlay={x}:{y}"
        else:
            vf = f"delogo=x={x}:y={y}:w={w}:h={h}"

        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(input_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "faster", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart"
        ]
        if meta["has_audio"]:
            cmd += ["-c:a", "copy"]
        else:
            cmd += ["-an"]
        cmd += [str(output_path)]

        run_cmd(cmd)
        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["output"] = f"/processed/{os.path.basename(output_path)}"
    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in [".mp4", ".mov", ".webm", ".mkv", ".avi"]:
        ext = ".mp4"

    file_id = str(uuid.uuid4())[:8]
    raw_path = UPLOAD_DIR / f"{file_id}{ext}"
    thumb_path = UPLOAD_DIR / f"{file_id}_thumb.jpg"

    try:
        with open(raw_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)

        meta = get_video_meta(str(raw_path))

        # Ekstrak 1 frame (detik 0.1 atau 0.0) untuk kanvas UI
        seek_pos = "0.5" if meta["duration"] > 1.0 else "0.0"
        cmd_thumb = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", seek_pos, "-i", str(raw_path),
            "-vframes", "1", "-q:v", "2", str(thumb_path)
        ]
        run_cmd(cmd_thumb)

        return {
            "file_id": file_id,
            "filename": file.filename,
            "width": meta["width"],
            "height": meta["height"],
            "duration": round(meta["duration"], 2),
            "preview_url": f"/uploads/{file_id}_thumb.jpg",
            "video_url": f"/uploads/{file_id}{ext}"
        }
    except Exception as err:
        if raw_path.exists():
            raw_path.unlink()
        if thumb_path.exists():
            thumb_path.unlink()
        raise HTTPException(status_code=400, detail=f"Gagal memproses file: {str(err)}")

@app.post("/api/remove")
async def remove_watermark(
    background_tasks: BackgroundTasks,
    file_id: str = Form(...),
    x: int = Form(...),
    y: int = Form(...),
    w: int = Form(...),
    h: int = Form(...),
    mode: str = Form("delogo")
):
    matches = list(UPLOAD_DIR.glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="File video tidak ditemukan")
    src = matches[0]

    job_id = str(uuid.uuid4())[:8]
    out_file = PROCESSED_DIR / f"clean_{job_id}.mp4"

    JOBS[job_id] = {
        "status": "queued",
        "error": None,
        "output": None
    }

    background_tasks.add_task(
        process_watermark,
        job_id, str(src), str(out_file), x, y, w, h, mode
    )

    return {"job_id": job_id, "status": "queued"}

@app.get("/api/status/{job_id}")
async def job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return JOBS[job_id]

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/processed", StaticFiles(directory=str(PROCESSED_DIR)), name="processed")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.get("/", response_class=FileResponse)
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")
