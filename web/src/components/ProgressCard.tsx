import { Check, Loader2 } from "lucide-react";

const STEPS = [
  { id: "audio", label: "Prepare audio", until: 0.1 },
  { id: "stt", label: "Transcribe", until: 0.72 },
  { id: "llm", label: "Write minutes", until: 1 },
];

export default function ProgressCard({ step, progress, filename }: { step: string; progress: number; filename: string }) {
  const pct = Math.round(Math.max(0.03, progress) * 100);
  return (
    <div className="card mx-auto max-w-xl text-center">
      <div className="mx-auto flex h-12 items-end justify-center gap-1" aria-hidden="true">
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <span key={i} className="w-1.5 origin-bottom animate-bar rounded-full bg-gradient-to-t from-brand-600 to-sky-400" style={{ height: "100%", animationDelay: `${i * 0.1}s` }} />
        ))}
      </div>
      <h2 className="mt-5 text-xl font-bold text-slate-900">Working on your meeting</h2>
      <p className="mt-1 truncate text-sm text-slate-500">{filename}</p>

      <div className="mt-6 h-2 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-gradient-to-r from-brand-600 to-sky-500 transition-all duration-700" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-sm font-medium text-slate-700">{step}</p>

      <ol className="mt-6 grid grid-cols-3 gap-2 text-left">
        {STEPS.map((s, i) => {
          const prev = i === 0 ? 0 : STEPS[i - 1].until;
          const done = progress >= s.until;
          const active = !done && progress >= prev;
          return (
            <li key={s.id} className={`flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold ${
              done ? "bg-emerald-50 text-emerald-700" : active ? "bg-brand-50 text-brand-700" : "bg-slate-50 text-slate-400"
            }`}>
              {done ? <Check size={14} /> : active ? <Loader2 size={14} className="animate-spin" /> : <span className="h-3.5 w-3.5 rounded-full border-2 border-current opacity-50" />}
              {s.label}
            </li>
          );
        })}
      </ol>
      <p className="mt-5 text-xs text-slate-400">A one-hour meeting takes about a minute. If the free server was asleep, the first run is slower.</p>
    </div>
  );
}
