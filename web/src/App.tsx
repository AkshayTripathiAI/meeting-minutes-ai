import { AudioLines, Github, Lock, ShieldCheck, Split, Workflow } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import InputCard, { type Source } from "./components/InputCard";
import ProgressCard from "./components/ProgressCard";
import Results from "./components/Results";
import { api, type Config, type Job } from "./lib/api";

const REPO = "https://github.com/AkshayTripathiAI/meeting-minutes-ai";

const FEATURES = [
  { icon: Split, title: "Overlap-safe chunking", text: "Long recordings are split with overlap, so no sentence is lost or doubled at the seams." },
  { icon: Workflow, title: "Grounded minutes", text: "Map-reduce over the transcript, validated JSON, and timestamps checked against what was said." },
  { icon: ShieldCheck, title: "Private by design", text: "Audio is deleted after processing. Run it locally to keep recordings on your machine." },
];

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [audioUrl, setAudioUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const poll = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api.config().then((c) => !cancelled && setConfig(c)).catch(() => !cancelled && window.setTimeout(load, 4000));
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => () => {
    if (poll.current) window.clearInterval(poll.current);
  }, []);

  async function start(source: Source, task: string, language: string) {
    setError("");
    setBusy(true);
    try {
      const { id } = source.kind === "sample" ? await api.sample() : await api.upload(source.blob, source.name, task, language);
      setAudioUrl(source.kind === "sample" ? api.sampleUrl : URL.createObjectURL(source.blob));
      setJob({ id, filename: source.kind === "sample" ? "Weekly launch sync (sample)" : source.name, status: "queued", step: "Queued", progress: 0, error: null, result: null });
      poll.current = window.setInterval(async () => {
        try {
          const j = await api.job(id);
          setJob(j);
          if (j.status === "done" || j.status === "error") {
            window.clearInterval(poll.current!);
            if (j.status === "error") {
              setError(j.error ?? "Something went wrong.");
              setJob(null);
            }
          }
        } catch (e) {
          window.clearInterval(poll.current!);
          setError(e instanceof Error ? e.message : String(e));
          setJob(null);
        }
      }, 1200);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    if (audioUrl.startsWith("blob:")) URL.revokeObjectURL(audioUrl);
    setJob(null);
    setAudioUrl("");
    setError("");
  }

  const done = job?.status === "done" && job.result;

  return (
    <div className="mx-auto flex min-h-screen max-w-4xl flex-col px-4 sm:px-6">
      <header className="flex items-center justify-between gap-3 py-6">
        <button onClick={reset} className="flex items-center gap-3 text-left">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-sky-500 text-white shadow-lg shadow-brand-500/30">
            <AudioLines size={22} />
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-slate-900">
              Minutes<span className="text-brand-600">AI</span>
            </h1>
            <p className="text-xs text-slate-500">Meeting recording → minutes</p>
          </div>
        </button>
        <div className="flex items-center gap-2">
          <span className="hidden items-center gap-1.5 rounded-full bg-white/80 px-3 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200 sm:inline-flex">
            <Lock size={12} className="text-emerald-600" /> Audio deleted after processing
          </span>
          <a href={REPO} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700">
            <Github size={13} /> Source
          </a>
        </div>
      </header>

      <main className="flex-1 pb-12">
        {done ? (
          <Results job={job} audioUrl={audioUrl} onReset={reset} />
        ) : job ? (
          <div className="pt-10">
            <ProgressCard step={job.step} progress={job.progress} filename={job.filename} />
          </div>
        ) : (
          <div className="space-y-8">
            <div className="pt-4 text-center sm:pt-8">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700 ring-1 ring-inset ring-brand-100">
                Whisper large-v3 + open-weight LLMs on Groq
              </span>
              <h2 className="mx-auto mt-4 max-w-2xl text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
                Turn any meeting into <span className="bg-gradient-to-r from-brand-600 to-sky-500 bg-clip-text text-transparent">clear minutes</span>
              </h2>
              <p className="mx-auto mt-3 max-w-xl text-slate-600">
                Upload or record a meeting in Hindi, English or another Indian language. Get a summary, decisions,
                action items with owners and open questions, each linked to the moment it was said.
              </p>
            </div>

            <InputCard config={config} busy={busy} error={error} onStart={start} />

            <div className="grid gap-4 sm:grid-cols-3">
              {FEATURES.map(({ icon: Icon, title, text }) => (
                <div key={title} className="rounded-2xl bg-white/60 p-5 ring-1 ring-slate-200/70">
                  <Icon size={18} className="text-brand-600" />
                  <p className="mt-2 text-sm font-bold text-slate-900">{title}</p>
                  <p className="mt-1 text-sm text-slate-500">{text}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-slate-200/70 py-5 text-center text-xs text-slate-400">
        Built by{" "}
        <a href="https://akshaytripathiai.vercel.app" target="_blank" rel="noreferrer" className="font-medium text-slate-500 hover:text-brand-700">
          Akshay Tripathi
        </a>{" "}
        · FastAPI · React · Whisper · Groq
      </footer>
    </div>
  );
}
