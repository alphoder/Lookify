"use client";

import { useEffect, useRef, useState } from "react";
import type { Summary } from "@/lib/clips";
import { rank } from "@/lib/ranking";

const mmss = (t: number) => `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

function say(e: string) {
  const [, verb, what] = /^(\w+) (.+)$/.exec(e) ?? [, "", e];
  if (verb === "missing") return { tone: "bad", text: `isn't wearing ${what === "gloves" ? "" : "a "}${what}` };
  if (verb === "wearing") return { tone: "good", text: `put on ${what === "gloves" ? "" : "a "}${what} ✓` };
  if (e === "started using phone") return { tone: "bad", text: "is using a phone" };
  if (e === "stopped using phone") return { tone: "good", text: "put the phone away" };
  if (e === "started idle") return { tone: "warn", text: "has been idle for 10+ seconds" };
  if (e === "stopped idle") return { tone: "good", text: "is working again" };
  if (verb === "identified") return { tone: "info", text: "identified from uniform badge" };
  if (e === "entered" || e === "exited") return { tone: "info", text: `${e} the kitchen` };
  return { tone: "info", text: e };
}
const DOT = { bad: "bg-red-500", good: "bg-emerald-500", warn: "bg-amber-400", info: "bg-sky-400" };

export default function ClipView({ clip, summary }: { clip: string; summary: Summary }) {
  const video = useRef<HTMLVideoElement>(null);
  const feed = useRef<HTMLUListElement>(null);
  const [now, setNow] = useState(0);
  const [reached, setReached] = useState(0); // furthest point played: jumping back keeps seen messages

  // follow playback: rAF gives smoother reveal than timeupdate (~4 Hz)
  useEffect(() => {
    let id = 0;
    const tick = () => {
      if (video.current) {
        const t = video.current.currentTime;
        setNow(t);
        setReached((r) => Math.max(r, t));
      }
      id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, []);

  const shown = summary.events.filter((e) => e.t <= reached);
  const current = summary.events.findLastIndex((e) => e.t <= now);
  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: "smooth" });
  }, [shown.length]);

  const board = rank(summary.events, summary.workers, now);
  const seek = (t: number) => {
    if (video.current) video.current.currentTime = t;
  };

  return (
    <div className="grid min-w-0 gap-4 xl:grid-cols-[1fr_340px]">
      <div className="min-w-0 space-y-4">
        <video
          ref={video}
          src={`/clips/${clip}/annotated.mp4`}
          controls
          muted
          playsInline
          className="max-h-[62vh] w-full rounded-xl border border-zinc-800 bg-black object-contain"
        />

        <section className="rounded-xl border border-zinc-800 bg-zinc-900/60">
          <header className="flex items-baseline justify-between border-b border-zinc-800 px-4 py-3">
            <h2 className="font-medium">Worker ranking</h2>
            <span className="text-xs text-zinc-500">score = % of on-camera time compliant · live</span>
          </header>
          <ol className="divide-y divide-zinc-800">
            {board.map((r, i) => (
              <li key={r.worker} className="grid grid-cols-[2rem_1fr_auto] items-center gap-3 px-4 py-3">
                <span className={`text-lg font-semibold ${i === 0 ? "text-amber-400" : "text-zinc-500"}`}>#{i + 1}</span>
                <div className="min-w-0">
                  <p className="font-medium">{r.worker}</p>
                  <p className="truncate text-xs text-zinc-400">
                    {r.offCamera ? "Off camera" : r.open.length ? `Now: ${r.open.join(", ")}` : r.mistakes ? "Currently compliant" : "No issues"}
                  </p>
                </div>
                <div className="text-right">
                  <p className={`text-lg font-semibold ${r.score >= 80 ? "text-emerald-400" : r.score >= 50 ? "text-amber-400" : "text-red-400"}`}>
                    {r.score}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {r.mistakes} mistake{r.mistakes === 1 ? "" : "s"} · {r.onCameraS.toFixed(0)}s seen
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <section className="flex max-h-[calc(62vh+14rem)] min-h-80 flex-col rounded-xl border border-zinc-800 bg-zinc-900/60">
        <header className="flex items-center gap-2 border-b border-zinc-800 px-4 py-3">
          <span className="size-2 animate-pulse rounded-full bg-red-500" />
          <h2 className="font-medium">Kitchen monitor</h2>
          <span className="ml-auto font-mono text-xs text-zinc-500">{mmss(now)}</span>
        </header>
        <ul ref={feed} className="flex-1 space-y-2 overflow-y-auto p-3">
          {shown.length === 0 && (
            <li className="p-2 text-sm text-zinc-500">Press play. Findings will appear here as the model sees them.</li>
          )}
          {shown.map((e, i) => {
            const m = say(e.event);
            return (
              <li key={i}>
                <button
                  onClick={() => seek(e.t)}
                  className={`w-full rounded-2xl rounded-tl-sm px-3 py-2 text-left text-sm transition hover:bg-zinc-800 ${
                    i === current ? "bg-zinc-800 ring-1 ring-amber-400/60" : "bg-zinc-800/80"
                  } ${e.t > now ? "opacity-40" : ""}`}
                >
                  <span className="flex items-center gap-2 text-xs text-zinc-500">
                    <span className={`size-1.5 rounded-full ${DOT[m.tone as keyof typeof DOT]}`} />
                    {mmss(e.t)}
                  </span>
                  <span className="mt-0.5 block">
                    <b>{e.worker}</b> {m.text}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
