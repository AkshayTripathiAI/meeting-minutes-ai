"""Meeting minutes with an LLM on Groq: map-reduce over the timestamped transcript.

Short meetings go to the model in one pass. Long ones are split into windows; each window
yields notes (map) and the notes are merged into the final minutes (reduce). Output is
JSON validated with pydantic; on invalid output the model gets the error and one retry.
Timestamps the model cites must exist in the transcript, otherwise they are dropped.
"""
import json
import logging
import os
import re
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

from .audio import fmt_ts
from .transcribe import Segment

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"
WINDOW_CHARS = 24_000  # ~6k tokens of transcript per map call

_TS = re.compile(r"^\d{2}:\d{2}:\d{2}$")


class Item(BaseModel):
    text: str
    timestamp: str | None = None

    @field_validator("timestamp")
    @classmethod
    def _ts(cls, v):
        return v if v and _TS.match(v) else None


class ActionItem(Item):
    owner: str | None = None
    due: str | None = None


class Minutes(BaseModel):
    title: str = "Meeting minutes"
    summary: str = ""
    participants: list[str] = Field(default_factory=list)
    key_points: list[Item] = Field(default_factory=list)
    decisions: list[Item] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    open_questions: list[Item] = Field(default_factory=list)


SCHEMA_HINT = """Return ONLY a JSON object with these keys:
{
  "title": "short descriptive title",
  "summary": "3-5 sentence overview",
  "participants": ["names mentioned or who spoke, only if stated"],
  "key_points": [{"text": "...", "timestamp": "HH:MM:SS"}],
  "decisions": [{"text": "what was decided", "timestamp": "HH:MM:SS"}],
  "action_items": [{"text": "task", "owner": "name or null", "due": "deadline as said, or null", "timestamp": "HH:MM:SS"}],
  "open_questions": [{"text": "unresolved question", "timestamp": "HH:MM:SS"}]
}"""

RULES = """Rules:
- Use only what is in the transcript. Never invent names, owners, dates or numbers.
- owner/due are null unless the transcript states them. A decision is something agreed, not merely discussed.
- timestamp is the [HH:MM:SS] of the transcript line where the item is said. Copy it exactly.
- Be concise and specific. Skip small talk.
- Write in {language}."""

MAP_SYSTEM = (
    "You take notes for one part of a longer meeting transcript. Extract the important content of THIS part only.\n"
    + SCHEMA_HINT + "\n" + RULES
)
FINAL_SYSTEM = "You write clear, accurate meeting minutes from a transcript.\n" + SCHEMA_HINT + "\n" + RULES
REDUCE_SYSTEM = (
    "You merge notes taken from consecutive parts of one meeting into final minutes. Remove duplicates, keep the "
    "timestamps from the notes, and write one overall title and summary.\n" + SCHEMA_HINT + "\n" + RULES
)


class LLM(Protocol):
    def complete_json(self, system: str, user: str) -> str: ...


class GroqLLM:
    """Groq through its OpenAI-compatible API (JSON mode)."""

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None):
        from openai import OpenAI

        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise SystemExit("Set GROQ_API_KEY (get one at https://console.groq.com/keys) or use --no-minutes.")
        self.client = OpenAI(base_url=GROQ_BASE_URL, api_key=key, max_retries=4, timeout=120)
        self.model = model

    def complete_json(self, system: str, user: str) -> str:
        r = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return r.choices[0].message.content or ""


def transcript_lines(segments: list[Segment]) -> list[str]:
    return [f"[{fmt_ts(s.start)}] {s.text}" for s in segments if s.text and not s.text.startswith("[chunk ")]


def windows(lines: list[str], max_chars: int = WINDOW_CHARS) -> list[str]:
    """Group transcript lines into windows under `max_chars`, never splitting a line."""
    out, buf, size = [], [], 0
    for line in lines:
        if buf and size + len(line) + 1 > max_chars:
            out.append("\n".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line) + 1
    if buf:
        out.append("\n".join(buf))
    return out


def _parse(raw: str) -> Minutes:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return Minutes.model_validate(json.loads(text))


def ask(llm: LLM, system: str, user: str) -> Minutes:
    """One LLM call with schema validation and a single corrective retry."""
    raw = llm.complete_json(system, user)
    try:
        return _parse(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Invalid JSON from model, retrying once: %s", exc)
        raw = llm.complete_json(system, f"{user}\n\nYour previous reply was invalid ({exc}). Return valid JSON only.")
        return _parse(raw)


def _drop_unknown_timestamps(m: Minutes, known: set[str]) -> Minutes:
    for group in (m.key_points, m.decisions, m.action_items, m.open_questions):
        for item in group:
            if item.timestamp and item.timestamp not in known:
                item.timestamp = None
    return m


def summarize(segments: list[Segment], llm: LLM, language: str = "English", max_chars: int = WINDOW_CHARS,
              progress=print) -> Minutes:
    lines = transcript_lines(segments)
    if not lines:
        return Minutes(summary="The recording contained no recognisable speech.")
    known = {line[1:9] for line in lines}
    # str.replace, not .format: the prompts contain literal JSON braces.
    final_sys, map_sys, reduce_sys = (p.replace("{language}", language) for p in (FINAL_SYSTEM, MAP_SYSTEM, REDUCE_SYSTEM))
    parts = windows(lines, max_chars)

    if len(parts) == 1:
        progress("Writing minutes...")
        minutes = ask(llm, final_sys, f"Transcript:\n{parts[0]}")
        return _drop_unknown_timestamps(minutes, known)

    notes = []
    for i, part in enumerate(parts, 1):
        progress(f"Taking notes on part {i} of {len(parts)}...")
        notes.append(ask(llm, map_sys, f"Transcript part {i} of {len(parts)}:\n{part}"))
    progress("Merging notes into minutes...")
    merged = "\n\n".join(f"Notes for part {i}:\n{n.model_dump_json()}" for i, n in enumerate(notes, 1))
    return _drop_unknown_timestamps(ask(llm, reduce_sys, merged), known)
