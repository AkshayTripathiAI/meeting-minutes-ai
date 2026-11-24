import {
  CheckCircle2,
  ClipboardList,
  Download,
  FileText,
  HelpCircle,
  Lightbulb,
  ListChecks,
  RotateCcw,
  UserRound,
  Users,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, type Item, type Job } from "../lib/api";
import { clock, tsToSeconds } from "../lib/time";

interface Props {
  job: Job;
  audioUrl: string;
  onReset: () => void;
}

function Stamp({ ts, onSeek }: { ts: string | null; onSeek: (s: number) => void }) {
  if (!ts) return null;
  return (
    <button className="ts shrink-0" onClick={() => onSeek(tsToSeconds(ts))} title="Play from here">
      ▶ {ts.startsWith("00:") ? ts.slice(3) : ts}
    </button>
  );
}

function Section({ icon, title, tone, count, children }: { icon: ReactNode; title: string; tone: string; count: number; children: ReactNode }) {
  return (
    <section className="card">
      <h3 className="mb-4 flex items-center gap-2.5 text-base font-bold text-slate-900">
        <span className={`grid h-8 w-8 place-items-center rounded-lg ${tone}`}>{icon}</span>
        {title}
        <span className="ml-auto rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">{count}</span>
      </h3>
      {children}
    </section>
  );
}

function ItemList({ items, onSeek, empty }: { items: Item[]; onSeek: (s: number) => void; empty: string }) {
  if (items.length === 0) return <p className="text-sm text-slate-400">{empty}</p>;
  return (
    <ul className="space-y-2.5">
      {items.map((it, i) => (
        <li key={i} className="flex items-start gap-3 text-sm leading-relaxed text-slate-700">
          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-300" />
          <span className="flex-1">{it.text}</span>
          <Stamp ts={it.timestamp} onSeek={onSeek} />
        </li>
      ))}
    </ul>
  );
}

export default function Results({ job, audioUrl, onReset }: Props) {
  const [tab, setTab] = useState<"minutes" | "transcript">("minutes");
  const [now, setNow] = useState(0);
  const player = useRef<HTMLAudioElement>(null);
  const activeLine = useRef<HTMLButtonElement>(null);
  const { minutes: m, segments } = job.result!;

  function seek(seconds: number) {
    const el = player.current;
    if (!el) return;
    el.currentTime = seconds;
    el.play().catch(() => {});
  }

  useEffect(() => {
    if (tab === "transcript") activeLine.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [now, tab]);

  const activeIndex = segments.findIndex((s) => now >= s.start && now < s.end + 0.3);

  return (
    <div className="space-y-5">
      <div className="card sticky top-3 z-10 flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <audio ref={player} src={audioUrl} controls className="w-full sm:flex-1" onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)} />
        <div className="flex flex-wrap items-center gap-1.5">
          <Download size={14} className="text-slate-400" />
          {(["md", "json", "srt", "txt"] as const).map((fmt) => (
            <a key={fmt} href={api.downloadUrl(job.id, fmt)} className="rounded-lg px-2.5 py-1.5 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-brand-700">
              .{fmt}
            </a>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="inline-flex rounded-2xl bg-white p-1 shadow-soft ring-1 ring-slate-200/80">
          {([["minutes", "Minutes", ClipboardList], ["transcript", "Transcript", FileText]] as const).map(([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition ${
                tab === id ? "bg-brand-600 text-white shadow-sm" : "text-slate-500 hover:text-slate-800"
              }`}
            >
              <Icon size={15} /> {label}
            </button>
          ))}
        </div>
        <button onClick={onReset} className="btn-ghost ml-auto">
          <RotateCcw size={15} /> New meeting
        </button>
      </div>

      {tab === "minutes" ? (
        <div className="space-y-5">
          <section className="card bg-gradient-to-br from-white to-brand-50/40">
            <p className="text-xs font-semibold uppercase tracking-wider text-brand-600">Meeting minutes</p>
            <h2 className="mt-1 text-2xl font-extrabold tracking-tight text-slate-900">{m.title}</h2>
            {m.participants.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <Users size={14} className="text-slate-400" />
                {m.participants.map((p) => (
                  <span key={p} className="rounded-full bg-white px-2.5 py-0.5 text-xs font-medium text-slate-700 ring-1 ring-slate-200">{p}</span>
                ))}
              </div>
            )}
            <p className="mt-4 leading-relaxed text-slate-700">{m.summary}</p>
          </section>

          <Section icon={<ListChecks size={16} />} title="Action items" tone="bg-sky-50 text-sky-600" count={m.action_items.length}>
            {m.action_items.length === 0 ? (
              <p className="text-sm text-slate-400">No action items were assigned.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {m.action_items.map((a, i) => (
                  <li key={i} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center">
                    <p className="flex-1 text-sm font-medium text-slate-800">{a.text}</p>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${a.owner ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-500"}`}>
                        <UserRound size={12} /> {a.owner ?? "Unassigned"}
                      </span>
                      {a.due && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700 ring-1 ring-inset ring-amber-100">Due {a.due}</span>}
                      <Stamp ts={a.timestamp} onSeek={seek} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <div className="grid gap-5 md:grid-cols-2">
            <Section icon={<CheckCircle2 size={16} />} title="Decisions" tone="bg-emerald-50 text-emerald-600" count={m.decisions.length}>
              <ItemList items={m.decisions} onSeek={seek} empty="No decisions were recorded." />
            </Section>
            <Section icon={<HelpCircle size={16} />} title="Open questions" tone="bg-amber-50 text-amber-600" count={m.open_questions.length}>
              <ItemList items={m.open_questions} onSeek={seek} empty="Nothing left open." />
            </Section>
          </div>

          <Section icon={<Lightbulb size={16} />} title="Key points" tone="bg-brand-50 text-brand-600" count={m.key_points.length}>
            <ItemList items={m.key_points} onSeek={seek} empty="No key points." />
          </Section>
          <p className="text-center text-xs text-slate-400">AI-generated minutes. Check important details against the transcript.</p>
        </div>
      ) : (
        <section className="card">
          <p className="mb-3 text-xs text-slate-500">Click a line to play it. The current line follows the audio.</p>
          <div className="max-h-[60vh] space-y-0.5 overflow-y-auto pr-1">
            {segments.map((s, i) => (
              <button
                key={i}
                ref={i === activeIndex ? activeLine : undefined}
                onClick={() => seek(s.start)}
                className={`flex w-full gap-3 rounded-lg px-3 py-2 text-left text-sm transition ${
                  i === activeIndex ? "bg-brand-50 text-slate-900 ring-1 ring-brand-100" : "text-slate-700 hover:bg-slate-50"
                }`}
              >
                <span className="w-14 shrink-0 pt-0.5 font-mono text-xs text-slate-400">{clock(s.start)}</span>
                <span className="flex-1 leading-relaxed">{s.text}</span>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
