import json
from pathlib import Path

from minutes.audio import Chunk, fmt_ts, plan_chunks
from minutes.cli import read_transcript
from minutes.render import minutes_markdown, write_transcripts
from minutes.summarize import Minutes, ask, summarize, transcript_lines, windows
from minutes.transcribe import Segment, stitch


class FakeLLM:
    """Returns queued replies and records the prompts it received."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append((system, user))
        return self.replies.pop(0)


def minutes_json(**overrides):
    base = {
        "title": "Q3 launch sync",
        "summary": "The team agreed the launch date.",
        "participants": ["Priya", "Arjun"],
        "key_points": [{"text": "Beta feedback is positive", "timestamp": "00:00:05"}],
        "decisions": [{"text": "Launch on 15 Sept", "timestamp": "00:00:10"}],
        "action_items": [{"text": "Send the press note", "owner": "Priya", "due": "Friday", "timestamp": "00:00:10"}],
        "open_questions": [],
    }
    base.update(overrides)
    return json.dumps(base)


SEGMENTS = [
    Segment(5, 8, "Beta feedback has been positive."),
    Segment(10, 14, "Let's launch on 15 September. Priya, please send the press note by Friday."),
]


# --- audio / stitching -----------------------------------------------------------------

def test_fmt_ts():
    assert fmt_ts(3725.25) == "01:02:05"
    assert fmt_ts(3725.25, srt=True) == "01:02:05,250"


def test_plan_chunks_overlap_and_coverage():
    plans = plan_chunks(1500, chunk_seconds=600, overlap_seconds=15)
    assert plans == [(0.0, 0.0, 600.0), (585.0, 600.0, 1200.0), (1185.0, 1200.0, 1500.0)]


def test_stitch_keeps_boundary_sentence_once_and_shifts_timestamps():
    chunks = [Chunk(Path("a"), 0, 0, 600), Chunk(Path("b"), 585, 600, 1200)]
    results = [
        [(10, 12, "hello"), (595, 605, "cut sentence")],  # midpoint 600 -> belongs to chunk 2
        [(10, 20, "cut sentence"), (30, 35, "next")],      # absolute 595-605 and 615-620
    ]
    out = stitch(chunks, results)
    assert [s.text for s in out] == ["hello", "cut sentence", "next"]
    assert out[1].start == 595 and out[2].start == 615


def test_stitch_records_failed_chunk():
    out = stitch([Chunk(Path("a"), 0, 0, 600)], [RuntimeError("boom")])
    assert out[0].text == "[chunk 1 failed: boom]"


# --- summarization ---------------------------------------------------------------------

def test_windows_never_split_lines():
    lines = [f"[00:00:{i:02d}] " + "x" * 50 for i in range(10)]
    parts = windows(lines, max_chars=130)
    assert all(len(p) <= 130 for p in parts)
    assert sum(p.count("\n") + 1 for p in parts) == 10


def test_single_pass_summary():
    llm = FakeLLM(minutes_json())
    m = summarize(SEGMENTS, llm)
    assert len(llm.calls) == 1
    assert m.decisions[0].text == "Launch on 15 Sept"
    assert m.action_items[0].owner == "Priya"
    assert "[00:00:10]" in llm.calls[0][1]


def test_map_reduce_for_long_meetings():
    llm = FakeLLM(minutes_json(title="part 1"), minutes_json(title="part 2"), minutes_json(title="Final"))
    m = summarize(SEGMENTS, llm, max_chars=60)  # forces two windows
    assert len(llm.calls) == 3
    assert "Notes for part 2" in llm.calls[2][1]
    assert m.title == "Final"


def test_invented_timestamps_are_dropped():
    llm = FakeLLM(minutes_json(decisions=[{"text": "x", "timestamp": "01:59:59"}]))
    m = summarize(SEGMENTS, llm)
    assert m.decisions[0].timestamp is None
    assert m.action_items[0].timestamp == "00:00:10"


def test_invalid_json_gets_one_corrective_retry():
    llm = FakeLLM("not json", minutes_json())
    m = ask(llm, "sys", "user")
    assert m.title == "Q3 launch sync"
    assert "previous reply was invalid" in llm.calls[1][1]


def test_code_fenced_json_is_accepted():
    llm = FakeLLM("```json\n" + minutes_json() + "\n```")
    assert ask(llm, "s", "u").title == "Q3 launch sync"


def test_language_placeholder_is_filled_without_breaking_json_braces():
    llm = FakeLLM(minutes_json())
    summarize(SEGMENTS, llm, language="Hindi")
    system = llm.calls[0][0]
    assert "Write in Hindi." in system and '"title":' in system


def test_empty_transcript_needs_no_llm():
    llm = FakeLLM()
    assert "no recognisable speech" in summarize([], llm).summary
    assert llm.calls == []


def test_failed_chunks_are_not_sent_to_the_llm():
    lines = transcript_lines([Segment(0, 0, "[chunk 1 failed: boom]"), Segment(1, 2, "hi")])
    assert lines == ["[00:00:01] hi"]


# --- output ----------------------------------------------------------------------------

def test_markdown_minutes():
    md = minutes_markdown(Minutes.model_validate_json(minutes_json()), "standup.m4a")
    assert md.startswith("# Q3 launch sync")
    assert "| Send the press note | Priya | Friday | 00:00:10 |" in md
    assert "- Launch on 15 Sept `[00:00:10]`" in md


def test_transcript_roundtrip(tmp_path):
    base = tmp_path / "meeting"
    txt, srt, plain = write_transcripts(SEGMENTS, base)
    assert "00:00:05,000 --> 00:00:08,000" in srt.read_text(encoding="utf-8")
    back = read_transcript(txt)
    assert [(s.start, s.text) for s in back] == [(5, SEGMENTS[0].text), (10, SEGMENTS[1].text)]


# --- eval scorer ------------------------------------------------------------------------

def test_eval_scorer_counts_hits_and_invented_owners():
    from minutes.evaluate import score

    expected = {
        "decisions": [{"keywords": ["launch"]}],
        "action_items": [{"owner": "Priya", "keywords": ["press"]}, {"owner": "Arjun", "keywords": ["security"]}],
        "open_questions": [{"keywords": ["trial"]}],
    }
    m = Minutes.model_validate_json(minutes_json(
        action_items=[{"text": "Send the press note", "owner": "Priya", "timestamp": "00:00:10"},
                      {"text": "Security review", "owner": "Rahul", "timestamp": None}],
    ))
    r = score(m, expected, "Priya will send the press note. Arjun books the security review. Launch is set.")
    assert r["decisions"] == {"hits": 1, "total": 1}
    assert r["action_items"] == {"hits": 1, "total": 2}  # Arjun's item was attributed to Rahul
    assert r["invented_owners"] == ["Rahul"]
    assert r["open_questions"] == {"hits": 0, "total": 1}
