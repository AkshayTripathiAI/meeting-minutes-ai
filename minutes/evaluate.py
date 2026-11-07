"""Score generated minutes against reference minutes.

    python -m minutes.evaluate                      # runs Groq on evals/standup_transcript.txt
    python -m minutes.evaluate --minutes x.json --expected y.json

Recall of decisions, action items (owner must match when the reference names one) and open
questions, plus two hallucination checks: owners that never appear in the transcript, and
timestamps that don't exist in it (the summarizer already drops those, so this should be 0).
"""
import argparse
import json
from pathlib import Path

from .cli import read_transcript
from .summarize import DEFAULT_MODEL, GroqLLM, Minutes, summarize

HERE = Path(__file__).resolve().parent.parent / "evals"


def _hit(expected: dict, items, owner_required: bool) -> bool:
    for item in items:
        text = item.text.lower()
        if not any(k in text for k in expected["keywords"]):
            continue
        if owner_required and expected.get("owner"):
            if (getattr(item, "owner", None) or "").lower() != expected["owner"].lower():
                continue
        return True
    return False


def score(minutes: Minutes, expected: dict, transcript_text: str) -> dict:
    def recall(key, owner_required=False):
        refs = expected.get(key, [])
        hits = sum(_hit(r, getattr(minutes, key), owner_required) for r in refs)
        return {"hits": hits, "total": len(refs)}

    lower = transcript_text.lower()
    invented_owners = [a.owner for a in minutes.action_items if a.owner and a.owner.lower() not in lower]
    return {
        "decisions": recall("decisions"),
        "action_items": recall("action_items", owner_required=True),
        "open_questions": recall("open_questions"),
        "invented_owners": invented_owners,
        "action_items_with_timestamp": sum(bool(a.timestamp) for a in minutes.action_items),
        "action_items_total": len(minutes.action_items),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", type=Path, default=HERE / "standup_transcript.txt")
    ap.add_argument("--expected", type=Path, default=HERE / "standup_expected.json")
    ap.add_argument("--minutes", type=Path, help="score an existing *_minutes.json instead of calling Groq")
    ap.add_argument("--llm-model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    if args.minutes:
        minutes = Minutes.model_validate_json(args.minutes.read_text(encoding="utf-8"))
    else:
        minutes = summarize(read_transcript(args.transcript), GroqLLM(args.llm_model))
    result = score(minutes, expected, args.transcript.read_text(encoding="utf-8"))

    def fmt(r):
        return f"{r['hits']}/{r['total']}"

    print(f"Decisions recalled:      {fmt(result['decisions'])}")
    print(f"Action items recalled:   {fmt(result['action_items'])}  (owner must match)")
    print(f"Open questions recalled: {fmt(result['open_questions'])}")
    print(f"Invented owners:         {result['invented_owners'] or 'none'}")
    print(f"Action items with a timestamp: {result['action_items_with_timestamp']}/{result['action_items_total']}")


if __name__ == "__main__":
    main()
