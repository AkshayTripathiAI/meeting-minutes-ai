# meeting-minutes-ai

[![CI](https://github.com/AkshayTripathiAI/meeting-minutes-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/AkshayTripathiAI/meeting-minutes-ai/actions/workflows/ci.yml)

Turn a meeting recording into a timestamped transcript **and** structured minutes: summary, decisions,
action items (owner, due date) and open questions, each linked to the moment it was said.
Speech-to-text runs locally with Whisper, so the audio never leaves your machine; only the text transcript goes
to an LLM on Groq. Hindi (and other) meetings are translated to English on the way.

```
recording.m4a ──► ffmpeg: overlapping 16 kHz chunks ──► Whisper (local or OpenAI) ──► stitched transcript
                                                                                        │
              minutes.md / minutes.json ◄── Groq LLM: map-reduce, validated JSON ◄──────┘
```

## Example

The format, shown with the hand-written **reference** minutes the eval uses for a one-minute synthetic stand-up
(`evals/standup_transcript.txt`; the audio was generated with text-to-speech and transcribed by local Whisper):

```markdown
## Decisions
- Launch on 15 September `[00:00:33]`

## Action items
| Task | Owner | Due | When |
|---|---|---|---|
| Book the security review with the InfoSec team | Arjun | Wednesday | 00:00:36 |
| Fix the slow export button | Priya | Before launch | 00:00:41 |
| Send the press note to marketing | _unassigned_ | Friday | 00:00:45 |

## Open questions
- Should the first month include a free trial? `[00:00:49]`
```

## Install

```bash
# ffmpeg:  Windows: winget install ffmpeg | macOS: brew install ffmpeg | Linux: sudo apt install ffmpeg
python -m venv .venv
.venv/Scripts/activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY=...         # PowerShell: $env:GROQ_API_KEY="..."   (https://console.groq.com/keys)
```

## Use

```bash
python -m minutes meeting.m4a                      # English transcript + minutes
python -m minutes meeting.mp3 --language hi        # Hindi audio, English minutes
python -m minutes meeting.mp3 --task transcribe    # keep the spoken language in the transcript
python -m minutes meeting.mp3 --model small        # faster local model (default: medium)
python -m minutes meeting.mp3 --backend openai     # OpenAI Whisper API instead (needs OPENAI_API_KEY)
python -m minutes meeting.mp3 --no-minutes         # transcript only, no LLM
python -m minutes --from-transcript meeting_transcript.txt   # minutes for an existing transcript
```

Outputs next to the recording: `_transcript.txt` (timestamped), `_transcript.srt` (subtitles), `_plain.txt`,
`_minutes.md` and `_minutes.json`.

## How it works

- **Overlapping chunks.** Long recordings are cut into 10-minute, 16 kHz mono chunks (~5 MB, under the OpenAI
  25 MB limit). Each chunk starts 15 s early, and a segment is kept only by the chunk whose window contains its
  midpoint, so a sentence cut at a boundary appears exactly once with correct timestamps.
- **Map-reduce minutes.** Short meetings go to the model in one call. Longer transcripts are split into windows of
  ~6k tokens; each window yields notes, which are merged into the final minutes.
- **Validated output.** The LLM answers in JSON mode and the result is validated with pydantic; invalid output gets
  one corrective retry. Timestamps the model cites that don't exist in the transcript are dropped, and the prompt
  forbids inventing owners or dates.
- **Resilient.** One failed chunk is recorded and skipped, not fatal; a missing API key fails before any audio work.

## Evaluate

```bash
python -m minutes.evaluate        # summarise evals/standup_transcript.txt with Groq and score it
```

It reports recall of reference decisions, action items (the owner must match) and open questions, plus
hallucination checks: owners that never appear in the transcript, and action items without a valid timestamp.
`pytest` covers chunk planning and overlap de-duplication, windowing, map-reduce, JSON retries, timestamp checks,
rendering and transcript round-trips with a fake LLM (no key needed).

## Project layout

```
minutes/
  audio.py        ffmpeg probing and overlapping chunking
  transcribe.py   local / OpenAI Whisper backends, stitching with overlap de-duplication
  summarize.py    Groq LLM, map-reduce prompts, pydantic schema, validation
  render.py       transcript (.txt/.srt) and minutes (.md/.json) writers
  cli.py          command line
  evaluate.py     minutes scoring against reference minutes
evals/            synthetic stand-up transcript + reference minutes
tests/
```

## Roadmap

- Speaker diarization ("who said what") so owners can be inferred from the speaker
- Larger eval set with public meeting recordings
- Calendar/task export (ICS, Todoist, Jira) for action items
