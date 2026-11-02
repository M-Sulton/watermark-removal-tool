import os
import json
import uuid
import subprocess
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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

def build_filter_chain(boxes: list, mode: str, vw: int, vh: int) -> str:
    # Build filter for single or multiple boxes
    # Supported modes: blur, delogo, pixelate
    clamped = []
    for b in boxes:
        x = max(1, min(int(b["x"]), vw - 2))
        y = max(1, min(int(b["y"]), vh - 2))
        w = max(2, min(int(b["w"]), vw - x - 1))
        h = max(2, min(int(b["h"]), vh - y - 1))
        clamped.append({"x": x, "y": y, "w": w, "h": h})

    if not clamped:
        return ""

    if mode == "delogo":
        # Chain multiple delogos: delogo=x=..:y=..:w=..:h=..,delogo=...
        return ",".join([f"delogo=x={b['x']}:y={b['y']}:w={b['w']}:h={b['h']}" for b in clamped])

    # For blur and pixelate, chain using split and overlays
    # [in]split=N+1[main][c1][c2]... then overlay iteratively
    n = len(clamped)
    splits = "".join([f"[c{i}]" for i in range(n)])
    filters = [f"split={n+1}[base]{splits}"]

    current_base = "base"
    for i, b in enumerate(clamped):
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        if mode == "pixelate":
            process = f"crop={w}:{h}:{x}:{y},scale=iw/16:ih/16,scale={w}:{h}:flags=neighbor"
        else: # blur
            process = f"crop={w}:{h}:{x}:{y},boxblur=luma_radius=15:luma_power=3"

        out_name = f"out{i}"
        filters.append(f"[c{i}]{process}[clean{i}]")
        filters.append(f"[{current_base}][clean{i}]overlay={x}:{y}[{out_name}]")
        current_base = out_name

    # Last output alias is final stream, but ffmpeg takes last unnamed output, strip the last bracket or map
    # Simplest: connect final out to clean
    filter_graph = ";".join(filters)
    return filter_graph

def process_watermark(job_id: str, input_path: str, output_path: str, boxes: list, mode: str):
    try:
        JOBS[job_id]["status"] = "processing"
        meta = get_video_meta(input_path)
        vw, vh = meta["width"], meta["height"]

        vf = build_filter_chain(boxes, mode, vw, vh)

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

class RemoveRequest(BaseModel):
    file_id: str
    boxes: list # list of dict {x, y, w, h}
    mode: str = "blur"

@app.post("/api/remove")
async def remove_watermark(payload: RemoveRequest, background_tasks: BackgroundTasks):
    matches = list(UPLOAD_DIR.glob(f"{payload.file_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="File video tidak ditemukan")
    src = matches[0]

    if not payload.boxes:
        raise HTTPException(status_code=400, detail="Minimal tandai 1 kotak watermark")

    # Batasi maksimal 2 watermark sesuai request
    boxes = payload.boxes[:2]

    job_id = str(uuid.uuid4())[:8]
    out_file = PROCESSED_DIR / f"clean_{job_id}.mp4"

    JOBS[job_id] = {
        "status": "queued",
        "error": None,
        "output": None
    }

    background_tasks.add_task(
        process_watermark,
        job_id, str(src), str(out_file), boxes, payload.mode
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
