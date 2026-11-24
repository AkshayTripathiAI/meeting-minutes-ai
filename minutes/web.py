"""Web app: upload or record a meeting, watch progress, read the minutes.

    uvicorn minutes.web:app --port 8020

Jobs run in a small thread pool and are polled by the page. Uploaded audio is deleted as
soon as a job finishes, results are kept in memory for an hour, and nothing is written to a
database. Speech-to-text uses Groq by default (STT_BACKEND=local uses faster-whisper).
"""
import os
import shutil
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from .audio import fmt_ts, get_duration, split_audio
from .render import minutes_markdown
from .summarize import DEFAULT_MODEL, GroqLLM, Minutes, summarize
from .transcribe import GroqWhisper, LocalWhisper, Segment, transcribe

SAMPLE = Path(__file__).parent / "samples" / "sample-standup.mp3"
# The React app (web/) builds into web/dist; override with WEB_DIST for packaged installs.
WEB_DIST = Path(os.environ.get("WEB_DIST", Path(__file__).resolve().parent.parent / "web" / "dist"))
MAX_MB = float(os.environ.get("MAX_UPLOAD_MB", 25))
MAX_MINUTES = float(os.environ.get("MAX_AUDIO_MINUTES", 30))
JOBS_PER_HOUR = int(os.environ.get("JOBS_PER_HOUR", 6))
STT_BACKEND = os.environ.get("STT_BACKEND", "groq")
LLM_MODEL = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
JOB_TTL_SECONDS = 3600
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".webm", ".mp4", ".mpeg", ".mpga", ".flac", ".aac"}

app = FastAPI(title="meeting-minutes-ai")
_pool = ThreadPoolExecutor(max_workers=2)
_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_hits: dict[str, int] = defaultdict(int)


# Factories are module-level so tests can swap in fakes.
def make_engine(task: str, language: str | None):
    if STT_BACKEND == "local":
        return LocalWhisper(os.environ.get("WHISPER_MODEL", "small"), task, language)
    return GroqWhisper(task, language)


def make_llm():
    return GroqLLM(LLM_MODEL)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "?")


def _rate_limit(request: Request) -> None:
    if JOBS_PER_HOUR <= 0:
        return
    key = f"{_client_ip(request)}:{int(time.time() // 3600)}"
    if len(_hits) > 10000:
        _hits.clear()
    _hits[key] += 1
    if _hits[key] > JOBS_PER_HOUR:
        raise HTTPException(429, f"This demo allows {JOBS_PER_HOUR} meetings per hour. Please try again later.")


def _prune() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    with _lock:
        for job_id in [j for j, v in _jobs.items() if v["created"] < cutoff]:
            _jobs.pop(job_id, None)


def _update(job_id: str, **fields) -> None:
    with _lock:
        _jobs[job_id].update(fields)


def _run(job_id: str, audio: Path, task: str, language: str | None, workdir: Path, keep_audio: bool) -> None:
    try:
        _update(job_id, status="running", step="Preparing audio", progress=0.05)
        chunks = split_audio(audio, workdir, chunk_minutes=10, overlap_seconds=15)

        def stt_progress(message, done, total):
            _update(job_id, step=message, progress=0.1 + 0.6 * done / max(total, 1))

        segments = transcribe(chunks, make_engine(task, language), task, progress=stt_progress)
        if not any(s.text and not s.text.startswith("[chunk ") for s in segments):
            failed = next((s.text for s in segments if s.text.startswith("[chunk ")), "")
            raise RuntimeError(f"No speech could be transcribed. {failed}".strip())

        _update(job_id, step="Writing minutes", progress=0.75)
        minutes = summarize(segments, make_llm(), progress=lambda m: _update(job_id, step=m))
        _update(
            job_id, status="done", step="Done", progress=1.0,
            result={
                "minutes": minutes.model_dump(),
                "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in segments],
            },
        )
    except SystemExit as exc:  # missing API key etc.
        _update(job_id, status="error", error=str(exc))
    except Exception as exc:
        _update(job_id, status="error", error=f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        if not keep_audio:
            audio.unlink(missing_ok=True)


def _start(audio: Path, filename: str, task: str, language: str | None, keep_audio: bool = False) -> dict:
    _prune()
    job_id = uuid.uuid4().hex[:16]
    with _lock:
        _jobs[job_id] = {"id": job_id, "filename": filename, "status": "queued", "step": "Queued",
                         "progress": 0.0, "created": time.time(), "result": None, "error": None}
    workdir = Path(tempfile.mkdtemp(prefix="minutes_job_"))
    _pool.submit(_run, job_id, audio, task, language, workdir, keep_audio)
    return {"id": job_id}


def _validate_task(task: str, language: str | None) -> tuple[str, str | None]:
    if task not in ("translate", "transcribe"):
        raise HTTPException(422, "task must be 'translate' or 'transcribe'.")
    language = (language or "").strip().lower() or None
    if language and (len(language) > 5 or not language.isalpha()):
        raise HTTPException(422, "language must be a code like 'hi' or 'en'.")
    return task, language


@app.get("/api/config")
def config():
    return {"max_upload_mb": MAX_MB, "max_audio_minutes": MAX_MINUTES, "stt_backend": STT_BACKEND,
            "llm_model": LLM_MODEL, "jobs_per_hour": JOBS_PER_HOUR, "sample_available": SAMPLE.exists()}


@app.post("/api/jobs", status_code=202)
def create_job(request: Request, file: UploadFile = File(...), task: str = Form("translate"),
               language: str | None = Form(None)):
    task, language = _validate_task(task, language)
    suffix = Path(file.filename or "").suffix.lower() or ".webm"
    if suffix not in AUDIO_EXTENSIONS:
        raise HTTPException(415, f"Unsupported file type {suffix}. Use mp3, m4a, wav, webm, ogg or mp4.")
    data = file.file.read(int(MAX_MB * 1024 * 1024) + 1)
    if not data:
        raise HTTPException(400, "Empty file.")
    if len(data) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {MAX_MB:g} MB.")
    _rate_limit(request)
    fd, tmp = tempfile.mkstemp(prefix="minutes_upload_", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    audio = Path(tmp)
    try:
        minutes = get_duration(audio) / 60
    except Exception:
        audio.unlink(missing_ok=True)
        raise HTTPException(422, "Could not read this file as audio.")
    if minutes > MAX_MINUTES:
        audio.unlink(missing_ok=True)
        raise HTTPException(413, f"Recording is {minutes:.0f} minutes; the demo limit is {MAX_MINUTES:g}.")
    return _start(audio, file.filename or "recording", task, language)


@app.post("/api/jobs/sample", status_code=202)
def create_sample_job(request: Request):
    if not SAMPLE.exists():
        raise HTTPException(404, "No sample recording is bundled.")
    _rate_limit(request)
    return _start(SAMPLE, SAMPLE.name, "transcribe", "en", keep_audio=True)


def _job(job_id: str) -> dict:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found (results are kept for one hour).")
        return dict(job)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return _job(job_id)


@app.get("/api/jobs/{job_id}/download/{fmt}")
def download(job_id: str, fmt: str):
    job = _job(job_id)
    if job["status"] != "done":
        raise HTTPException(409, "The job has not finished yet.")
    minutes = Minutes.model_validate(job["result"]["minutes"])
    segments = [Segment(**s) for s in job["result"]["segments"]]
    stem = Path(job["filename"]).stem or "meeting"
    if fmt == "md":
        body, media = minutes_markdown(minutes, job["filename"]), "text/markdown"
    elif fmt == "json":
        body, media = minutes.model_dump_json(indent=2), "application/json"
    elif fmt == "srt":
        body = "".join(f"{i}\n{fmt_ts(s.start, True)} --> {fmt_ts(s.end, True)}\n{s.text}\n\n"
                       for i, s in enumerate(segments, 1))
        media = "application/x-subrip"
    elif fmt == "txt":
        body = "".join(f"[{fmt_ts(s.start)} - {fmt_ts(s.end)}] {s.text}\n" for s in segments)
        media = "text/plain"
    else:
        raise HTTPException(404, "Unknown format.")
    name = f"{stem}_{'minutes' if fmt in ('md', 'json') else 'transcript'}.{fmt}"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"


@app.get("/sample.mp3")
def sample_audio():
    if not SAMPLE.exists():
        raise HTTPException(404, "No sample recording is bundled.")
    return FileResponse(SAMPLE, media_type="audio/mpeg")


@app.get("/")
def index():
    page = WEB_DIST / "index.html"
    if not page.exists():
        return PlainTextResponse("UI not built. Run: cd web && npm install && npm run build", status_code=503)
    return FileResponse(page)


if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")
