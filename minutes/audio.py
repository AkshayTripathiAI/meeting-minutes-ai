"""Audio helpers: probe duration and cut overlapping 16 kHz mono chunks with ffmpeg."""
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    path: Path
    start: float          # where this chunk's audio actually starts (includes the overlap)
    window_start: float   # the part of the timeline this chunk is responsible for
    window_end: float


def fmt_ts(seconds: float, srt: bool = False) -> str:
    """00:12:30 (or 00:12:30,250 for SRT)."""
    ms = int(round(max(seconds, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}" if srt else f"{h:02}:{m:02}:{s:02}"


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit(
            "ffmpeg/ffprobe not found. Install ffmpeg first "
            "(Windows: winget install ffmpeg | macOS: brew install ffmpeg | Linux: apt install ffmpeg)."
        )


def get_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def plan_chunks(duration: float, chunk_seconds: float, overlap_seconds: float) -> list[tuple[float, float, float]]:
    """(audio_start, window_start, window_end) per chunk.

    Each chunk owns a fixed window of the timeline but its audio starts `overlap_seconds`
    earlier, so a sentence cut at a boundary is heard in full by the next chunk.
    """
    plans = []
    window_start = 0.0
    while window_start < duration - 0.5:
        window_end = min(window_start + chunk_seconds, duration)
        audio_start = max(0.0, window_start - overlap_seconds)
        plans.append((audio_start, window_start, window_end))
        window_start = window_end
    return plans


def split_audio(src: Path, out_dir: Path, chunk_minutes: float = 10, overlap_seconds: float = 15) -> list[Chunk]:
    """Cut `src` into overlapping mono 16 kHz MP3 chunks (~5 MB per 10 minutes)."""
    duration = get_duration(src)
    chunks = []
    for i, (audio_start, w_start, w_end) in enumerate(plan_chunks(duration, chunk_minutes * 60, overlap_seconds)):
        path = out_dir / f"chunk_{i:03d}.mp3"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{audio_start:.3f}", "-t", f"{w_end - audio_start:.3f}", "-i", str(src),
             "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(path)],
            check=True,
        )
        chunks.append(Chunk(path, audio_start, w_start, w_end))
    return chunks
