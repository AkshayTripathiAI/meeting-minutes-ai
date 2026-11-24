import { FileAudio, Mic, PlayCircle, Sparkles, Square, Upload, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import type { Config } from "../lib/api";
import { clock } from "../lib/time";
import { useRecorder } from "../lib/useRecorder";

export type Source =
  | { kind: "file"; blob: Blob; name: string }
  | { kind: "sample" };

interface Props {
  config: Config | null;
  busy: boolean;
  error: string;
  onStart: (source: Source, task: string, language: string) => void;
}

const TABS = [
  { id: "upload", label: "Upload", icon: Upload },
  { id: "record", label: "Record", icon: Mic },
  { id: "sample", label: "Try a sample", icon: Sparkles },
] as const;

const LANGUAGES = [
  ["", "Detect automatically"], ["hi", "Hindi"], ["en", "English"], ["ta", "Tamil"], ["te", "Telugu"],
  ["mr", "Marathi"], ["bn", "Bengali"], ["gu", "Gujarati"], ["kn", "Kannada"], ["ml", "Malayalam"],
] as const;

export default function InputCard({ config, busy, error, onStart }: Props) {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [task, setTask] = useState("translate");
  const [language, setLanguage] = useState("");
  const [localError, setLocalError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const rec = useRecorder();
  const recordingUrl = useMemo(() => (rec.blob ? URL.createObjectURL(rec.blob) : ""), [rec.blob]);
  useEffect(() => () => {
    if (recordingUrl) URL.revokeObjectURL(recordingUrl);
  }, [recordingUrl]);
  const maxMb = config?.max_upload_mb ?? 25;

  function pick(f: File | undefined) {
    setLocalError("");
    if (!f) return;
    if (f.size > maxMb * 1024 * 1024) {
      setLocalError(`That file is ${(f.size / 1048576).toFixed(1)} MB; the limit is ${maxMb} MB.`);
      return;
    }
    setFile(f);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files?.[0]);
  }

  const source: Source | null =
    tab === "upload" && file
      ? { kind: "file", blob: file, name: file.name }
      : tab === "record" && rec.blob
        ? { kind: "file", blob: rec.blob, name: "recording.webm" }
        : tab === "sample"
          ? { kind: "sample" }
          : null;

  return (
    <div className="card">
      <div className="mb-5 inline-flex rounded-2xl bg-slate-100 p-1">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-sm font-semibold transition ${
              tab === id ? "bg-white text-brand-700 shadow-sm" : "text-slate-500 hover:text-slate-800"
            }`}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      {tab === "upload" &&
        (file ? (
          <div className="flex items-center gap-3 rounded-2xl border border-brand-200 bg-brand-50/60 p-4">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-brand-600 text-white">
              <FileAudio size={20} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold text-slate-900">{file.name}</p>
              <p className="text-xs text-slate-500">{(file.size / 1048576).toFixed(1)} MB</p>
            </div>
            <button className="btn-ghost px-2" onClick={() => setFile(null)} aria-label="Remove file">
              <X size={16} />
            </button>
          </div>
        ) : (
          <button
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${
              dragging ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:border-brand-300 hover:bg-brand-50/40"
            }`}
          >
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-100 text-brand-600">
              <Upload size={22} />
            </div>
            <p className="font-semibold text-slate-900">Drop a recording here, or click to browse</p>
            <p className="text-sm text-slate-500">mp3, m4a, wav, webm or mp4 · up to {maxMb} MB</p>
          </button>
        ))}
      <input
        ref={input}
        type="file"
        accept="audio/*,video/mp4,.m4a,.mp3,.wav,.webm,.ogg"
        className="hidden"
        onChange={(e) => pick(e.target.files?.[0])}
      />

      {tab === "record" && (
        <div className="flex flex-col items-center gap-4 rounded-2xl bg-slate-50 px-6 py-8 text-center sm:flex-row sm:text-left">
          {rec.state === "recording" ? (
            <button onClick={rec.stop} className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-red-500 text-white shadow-lg shadow-red-500/30 transition hover:bg-red-600" aria-label="Stop recording">
              <Square size={22} fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={rec.start}
              disabled={rec.state === "unsupported"}
              className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-brand-600 text-white shadow-lg shadow-brand-500/30 transition hover:bg-brand-700 disabled:opacity-40"
              aria-label="Start recording"
            >
              <Mic size={24} />
            </button>
          )}
          <div className="flex-1">
            {rec.state === "recording" && (
              <div className="flex items-center gap-3">
                <span className="flex h-6 items-end gap-0.5" aria-hidden="true">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <span key={i} className="w-1 origin-bottom animate-bar rounded-full bg-red-500" style={{ height: "100%", animationDelay: `${i * 0.12}s` }} />
                  ))}
                </span>
                <p className="font-mono text-lg font-semibold text-slate-900">{clock(rec.seconds)}</p>
                <p className="text-sm text-slate-500">Recording… press stop when the meeting ends</p>
              </div>
            )}
            {rec.state === "stopped" && rec.blob && (
              <div className="space-y-2">
                <p className="font-semibold text-slate-900">Recorded {clock(rec.seconds)}</p>
                <audio controls src={recordingUrl} className="w-full max-w-md" />
                <button onClick={rec.reset} className="text-xs font-semibold text-brand-700 hover:underline">Record again</button>
              </div>
            )}
            {rec.state === "idle" && (
              <>
                <p className="font-semibold text-slate-900">Record a meeting with your microphone</p>
                <p className="text-sm text-slate-500">Nothing is recorded until you press the button.</p>
              </>
            )}
            {rec.state === "denied" && <p className="text-sm text-red-600">Microphone access was blocked. Allow it in your browser, then try again.</p>}
            {rec.state === "unsupported" && <p className="text-sm text-slate-500">Recording isn't supported in this browser. Upload a file instead.</p>}
          </div>
        </div>
      )}

      {tab === "sample" && (
        <div className="flex flex-col gap-4 rounded-2xl bg-slate-50 p-5 sm:flex-row sm:items-center">
          <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-brand-100 text-brand-600">
            <PlayCircle size={24} />
          </div>
          <div className="flex-1">
            <p className="font-semibold text-slate-900">Weekly launch sync · 1 minute</p>
            <p className="text-sm text-slate-500">
              A synthetic stand-up (text-to-speech): beta feedback, a launch date, three action items and an open
              question about pricing.
            </p>
          </div>
          <audio controls preload="none" src="/sample.mp3" className="w-full sm:w-64" />
        </div>
      )}

      {tab !== "sample" && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Minutes language
            <select value={task} onChange={(e) => setTask(e.target.value)} className="field mt-1.5 w-full normal-case tracking-normal">
              <option value="translate">Any language → English</option>
              <option value="transcribe">Keep the spoken language</option>
            </select>
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Spoken language
            <select value={language} onChange={(e) => setLanguage(e.target.value)} className="field mt-1.5 w-full normal-case tracking-normal">
              {LANGUAGES.map(([code, label]) => (
                <option key={code} value={code}>{label}</option>
              ))}
            </select>
          </label>
        </div>
      )}

      <div className="mt-5 flex flex-col-reverse items-stretch gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-slate-500">
          {config
            ? `Demo limits: ${config.max_upload_mb} MB, ${config.max_audio_minutes} minutes, ${config.jobs_per_hour} meetings per hour. Audio is deleted after processing.`
            : "Connecting… the free server can take up to a minute to wake up."}
        </p>
        <button className="btn-primary px-6" disabled={!source || busy || !config} onClick={() => source && onStart(source, task, language)}>
          <Sparkles size={16} /> Create minutes
        </button>
      </div>
      {(localError || error) && <p className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">{localError || error}</p>}
    </div>
  );
}
