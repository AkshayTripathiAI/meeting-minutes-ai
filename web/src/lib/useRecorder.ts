import { useEffect, useRef, useState } from "react";

export type RecorderState = "idle" | "recording" | "stopped" | "unsupported" | "denied";

/** Record from the microphone with MediaRecorder; returns the audio as a Blob. */
export function useRecorder() {
  const [state, setState] = useState<RecorderState>(
    typeof window !== "undefined" && "MediaRecorder" in window ? "idle" : "unsupported",
  );
  const [seconds, setSeconds] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current) window.clearInterval(timer.current);
      recorder.current?.stream.getTracks().forEach((t) => t.stop());
    },
    [],
  );

  async function start() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = () => {
        setBlob(new Blob(chunks, { type: rec.mimeType || "audio/webm" }));
        stream.getTracks().forEach((t) => t.stop());
      };
      recorder.current = rec;
      rec.start(1000);
      setBlob(null);
      setSeconds(0);
      setState("recording");
      timer.current = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    } catch {
      setState("denied");
    }
  }

  function stop() {
    recorder.current?.stop();
    if (timer.current) window.clearInterval(timer.current);
    setState("stopped");
  }

  function reset() {
    setBlob(null);
    setSeconds(0);
    setState("idle");
  }

  return { state, seconds, blob, start, stop, reset };
}
