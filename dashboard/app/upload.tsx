"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function Upload() {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "busy" | string>("idle");

  async function onChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setState("busy");
    const body = new FormData();
    body.set("video", file);
    const res = await fetch("/api/analyze", { method: "POST", body }).catch(() => null);
    const data = await res?.json().catch(() => null);
    if (!res?.ok || !data?.clip) return setState(data?.error ?? "Analysis failed");
    setState("idle");
    router.push(`/?clip=${data.clip}`);
    router.refresh();
  }

  return (
    <div className="pt-4">
      <label
        className={`block cursor-pointer rounded-lg border border-dashed border-zinc-700 px-3 py-4 text-center text-sm hover:border-amber-400/60 ${
          state === "busy" ? "pointer-events-none opacity-60" : ""
        }`}
      >
        {state === "busy" ? "Analysing… (about 1 min per 30 s of video)" : "+ Analyse a new clip"}
        <input type="file" accept="video/*" className="sr-only" onChange={onChange} disabled={state === "busy"} />
      </label>
      {state !== "idle" && state !== "busy" && <p className="mt-2 text-xs text-red-400">{state}</p>}
    </div>
  );
}
