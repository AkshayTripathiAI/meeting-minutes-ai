export interface Item {
  text: string;
  timestamp: string | null;
}

export interface ActionItem extends Item {
  owner: string | null;
  due: string | null;
}

export interface Minutes {
  title: string;
  summary: string;
  participants: string[];
  key_points: Item[];
  decisions: Item[];
  action_items: ActionItem[];
  open_questions: Item[];
}

export interface Segment {
  start: number;
  end: number;
  text: string;
}

export interface Job {
  id: string;
  filename: string;
  status: "queued" | "running" | "done" | "error";
  step: string;
  progress: number;
  error: string | null;
  result: { minutes: Minutes; segments: Segment[] } | null;
}

export interface Config {
  max_upload_mb: number;
  max_audio_minutes: number;
  stt_backend: string;
  llm_model: string;
  jobs_per_hour: number;
  sample_available: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  config: () => request<Config>("/api/config"),
  upload: (file: Blob, filename: string, task: string, language: string) => {
    const form = new FormData();
    form.append("file", file, filename);
    form.append("task", task);
    if (language) form.append("language", language);
    return request<{ id: string }>("/api/jobs", { method: "POST", body: form });
  },
  sample: () => request<{ id: string }>("/api/jobs/sample", { method: "POST" }),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  downloadUrl: (id: string, fmt: "md" | "json" | "srt" | "txt") => `/api/jobs/${id}/download/${fmt}`,
  sampleUrl: "/sample.mp3",
};
