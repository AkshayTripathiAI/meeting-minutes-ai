"""Command line: recording -> transcript -> minutes.

    python -m minutes meeting.m4a                        # local Whisper, English minutes via Groq
    python -m minutes meeting.mp3 --language hi          # Hindi audio
    python -m minutes meeting.mp3 --task transcribe      # keep the original language in the transcript
    python -m minutes meeting.mp3 --backend openai       # OpenAI Whisper API instead of local
    python -m minutes meeting.mp3 --no-minutes           # transcript only, no LLM
    python -m minutes --from-transcript notes_transcript.txt   # minutes for an existing transcript
"""
import argparse
import logging
import re
import shutil
import sys
import tempfile
from pathlib import Path

from .audio import require_ffmpeg, split_audio
from .render import write_minutes, write_transcripts
from .summarize import DEFAULT_MODEL, GroqLLM, summarize
from .transcribe import LocalWhisper, OpenAIWhisper, Segment, transcribe

_LINE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})(?: - (\d{2}):(\d{2}):(\d{2}))?\]\s*(.*)$")


def read_transcript(path: Path) -> list[Segment]:
    """Parse a *_transcript.txt written by this tool ([HH:MM:SS - HH:MM:SS] text)."""
    segments = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _LINE.match(line.strip())
        if not m:
            continue
        g = m.groups()
        start = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2])
        end = int(g[3]) * 3600 + int(g[4]) * 60 + int(g[5]) if g[3] else start
        segments.append(Segment(start, end, g[6]))
    return segments


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="minutes", description="Turn a meeting recording into a transcript and minutes.")
    ap.add_argument("audio", type=Path, nargs="?", help="audio/video file (mp3, m4a, wav, mp4...)")
    ap.add_argument("--from-transcript", type=Path, help="skip audio; summarise an existing *_transcript.txt")
    ap.add_argument("--backend", choices=["local", "openai"], default="local", help="speech-to-text backend")
    ap.add_argument("--task", choices=["translate", "transcribe"], default="translate",
                    help="translate = English transcript; transcribe = keep the spoken language")
    ap.add_argument("--language", help="spoken language code, e.g. hi, en, ta (auto-detect if omitted)")
    ap.add_argument("--model", default="medium", help="local Whisper model: tiny, base, small, medium, large-v3")
    ap.add_argument("--chunk-minutes", type=float, default=10)
    ap.add_argument("--overlap-seconds", type=float, default=15, help="audio overlap between chunks")
    ap.add_argument("--keep-chunks", action="store_true", help="keep the split audio files")
    ap.add_argument("--no-minutes", action="store_true", help="transcript only (no LLM call)")
    ap.add_argument("--llm-model", default=DEFAULT_MODEL, help=f"Groq model (default {DEFAULT_MODEL})")
    ap.add_argument("--minutes-language", default="English", help="language to write the minutes in")
    ap.add_argument("-v", "--verbose", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    if args.from_transcript:
        if not args.from_transcript.exists():
            sys.exit(f"File not found: {args.from_transcript}")
        segments = read_transcript(args.from_transcript)
        base = args.from_transcript.with_name(args.from_transcript.stem.removesuffix("_transcript"))
        written: list[Path] = []
        source = args.from_transcript.name
    else:
        if not args.audio or not args.audio.exists():
            sys.exit(f"File not found: {args.audio}")
        require_ffmpeg()
        llm = None if args.no_minutes else GroqLLM(args.llm_model)  # fail fast on a missing key

        work = Path(tempfile.mkdtemp(prefix="minutes_chunks_"))
        if args.keep_chunks:
            work = args.audio.with_name(args.audio.stem + "_chunks")
            work.mkdir(exist_ok=True)
        print(f"Splitting {args.audio.name} into {args.chunk_minutes:g}-minute chunks "
              f"({args.overlap_seconds:g}s overlap)...")
        chunks = split_audio(args.audio, work, args.chunk_minutes, args.overlap_seconds)
        print(f"  -> {len(chunks)} chunks")

        engine = (LocalWhisper(args.model, args.task, args.language) if args.backend == "local"
                  else OpenAIWhisper(args.task, args.language))
        segments = transcribe(chunks, engine, args.task)
        if not args.keep_chunks:
            shutil.rmtree(work, ignore_errors=True)

        base = args.audio.with_suffix("")
        written = write_transcripts(segments, base)
        source = args.audio.name

    if not args.no_minutes:
        llm = GroqLLM(args.llm_model) if args.from_transcript else llm
        minutes = summarize(segments, llm, language=args.minutes_language)
        written += write_minutes(minutes, base, source)
        print(f"\n{minutes.title}: {len(minutes.decisions)} decisions, {len(minutes.action_items)} action items")

    print("\nFiles written:")
    for p in written:
        print("  ", p)


if __name__ == "__main__":
    main()
