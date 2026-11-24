"""Speech-to-text backends (local faster-whisper or the OpenAI API) and chunk stitching."""
import logging
from dataclasses import dataclass
from typing import Protocol

from .audio import Chunk, fmt_ts

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    start: float
    end: float
    text: str


class Engine(Protocol):
    def run(self, path) -> list[tuple[float, float, str]]: ...


class LocalWhisper:
    """faster-whisper on this machine: free and private."""

    def __init__(self, model: str, task: str, language: str | None):
        from faster_whisper import WhisperModel

        logger.info("Loading local Whisper model '%s' (the first run downloads it)", model)
        self.model = WhisperModel(model, device="auto", compute_type="auto")
        self.task, self.language = task, language

    def run(self, path):
        segments, _info = self.model.transcribe(
            str(path), task=self.task, language=self.language, vad_filter=True, beam_size=5
        )
        return [(s.start, s.end, s.text.strip()) for s in segments]


class OpenAIWhisper:
    """OpenAI's hosted Whisper: fast, paid. Needs OPENAI_API_KEY."""

    def __init__(self, task: str, language: str | None):
        from openai import OpenAI

        self.client = OpenAI()
        self.task, self.language = task, language
        if task == "translate" and language:
            # The translations endpoint has no language parameter; it auto-detects the source.
            logger.warning("--language is ignored by the OpenAI translate endpoint (it auto-detects).")

    def run(self, path):
        with open(path, "rb") as f:
            if self.task == "translate":
                r = self.client.audio.translations.create(model="whisper-1", file=f, response_format="verbose_json")
            else:
                kw = {"language": self.language} if self.language else {}
                r = self.client.audio.transcriptions.create(
                    model="whisper-1", file=f, response_format="verbose_json", **kw
                )
        return [(s.start, s.end, s.text.strip()) for s in (r.segments or [])]


class GroqWhisper:
    """Whisper large-v3 on Groq: fast, free tier, no GPU needed. Needs GROQ_API_KEY.

    Used by the hosted web app, where running Whisper locally won't fit a small instance.
    """

    def __init__(self, task: str, language: str | None, api_key: str | None = None):
        import os

        from openai import OpenAI

        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise SystemExit("Set GROQ_API_KEY to use the Groq speech-to-text backend.")
        self.client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key, max_retries=4, timeout=300)
        self.task, self.language = task, language

    def run(self, path):
        with open(path, "rb") as f:
            if self.task == "translate":
                # Groq's translation endpoint supports whisper-large-v3 (not the turbo variant).
                r = self.client.audio.translations.create(
                    model="whisper-large-v3", file=f, response_format="verbose_json"
                )
            else:
                kw = {"language": self.language} if self.language else {}
                r = self.client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo", file=f, response_format="verbose_json", **kw
                )
        segments = getattr(r, "segments", None) or []
        out = []
        for s in segments:
            get = s.get if isinstance(s, dict) else lambda k, s=s: getattr(s, k)
            out.append((float(get("start")), float(get("end")), str(get("text")).strip()))
        return out


def stitch(chunks: list[Chunk], results: list[list[tuple[float, float, str]] | Exception]) -> list[Segment]:
    """Shift chunk-relative timestamps to the full timeline and drop overlap duplicates.

    A segment belongs to the chunk whose window contains its midpoint, so a sentence that
    straddles a boundary is kept exactly once (from the chunk that heard it whole).
    """
    out: list[Segment] = []
    for i, (chunk, result) in enumerate(zip(chunks, results), 1):
        if isinstance(result, Exception):
            out.append(Segment(chunk.window_start, chunk.window_start, f"[chunk {i} failed: {result}]"))
            continue
        last = i == len(chunks)
        for s, e, text in result:
            start, end = s + chunk.start, e + chunk.start
            mid = (start + end) / 2
            in_window = chunk.window_start <= mid < chunk.window_end or (last and mid >= chunk.window_start)
            if text and in_window:
                out.append(Segment(start, end, text))
    return out


def transcribe(chunks: list[Chunk], engine: Engine, task: str = "translate", progress=None) -> list[Segment]:
    results: list[list[tuple[float, float, str]] | Exception] = []
    verb = "Translating" if task == "translate" else "Transcribing"
    for i, chunk in enumerate(chunks, 1):
        message = f"{verb} part {i} of {len(chunks)} ({fmt_ts(chunk.window_start)}-{fmt_ts(chunk.window_end)})"
        if progress:
            progress(message, i - 1, len(chunks))
        else:
            print(f"[{i}/{len(chunks)}] {message}")
        try:
            results.append(engine.run(chunk.path))
        except Exception as exc:  # keep going: one bad chunk shouldn't lose the meeting
            logger.warning("Chunk %d failed: %s", i, exc)
            results.append(exc)
    return stitch(chunks, results)
