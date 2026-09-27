"use client";

import { useEffect, useRef, useState } from "react";
import type { Summary } from "@/lib/clips";
import { attendance, headcountAt } from "@/lib/attendance";
import { rank } from "@/lib/ranking";

const mmss = (t: number) => `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

const dur = (s: number) => (s >= 60 ? `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s` : `${Math.round(s)}s`);
const PLURAL = new Set(["gloves", "proper shoes"]);

function say(e: string) {
  const [, verb, what] = /^(\w+) (.+)$/.exec(e) ?? [, "", e];
  const item = `${PLURAL.has(what) ? "" : "a "}${what}`;
  if (verb === "missing") return { tone: "bad", text: `isn't wearing ${item}` };
  if (verb === "wearing") return { tone: "good", text: `put on ${item} ✓` };
  if (e === "left the kitchen") return { tone: "warn", text: "left the kitchen" };
  if (verb === "back") return { tone: "info", text: e.replace("back in the kitchen after", "is back in the kitchen, away") };
  if (e === "started using phone") return { tone: "bad", text: "is using a phone" };
  if (e === "stopped using phone") return { tone: "good", text: "put the phone away" };
  if (e === "started idle") return { tone: "warn", text: "has been idle for 10+ seconds" };
  if (e === "stopped idle") return { tone: "good", text: "is working again" };
  if (verb === "identified") return { tone: "info", text: e.endsWith("face") ? "recognised by face" : "identified from uniform badge" };
  if (e === "entered" || e === "exited") return { tone: "info", text: `${e} the kitchen` };
  return { tone: "info", text: e };
}
const DOT = { bad: "bg-red-500", good: "bg-emerald-500", warn: "bg-amber-400", info: "bg-sky-400" };

export default function ClipView({ clip, summary: initial }: { clip: string; summary: Summary }) {
  const video = useRef<HTMLVideoElement>(null);
  const [summary, setSummary] = useState(initial);
  const feed = useRef<HTMLUListElement>(null);
  const [now, setNow] = useState(0);
  const [reached, setReached] = useState(0); // furthest point played: jumping back keeps seen messages
  const [frameNo, setFrameNo] = useState(0);
  const live = summary.live === true;
  const lastLive = useRef(0); // engine clock at the last live update: keeps the feed full when replay takes over

  // live session: poll the engine's latest findings + frame; stops once the engine's final report lands
  useEffect(() => {
    if (!live) return;
    const id = setInterval(async () => {
      const s = await fetch(`/api/live/${clip}`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);
      if (s && !s.live) setReached(lastLive.current);
      if (s) setSummary(s);
      setFrameNo((n) => n + 1);
    }, 1000);
    return () => clearInterval(id);
  }, [clip, live]);

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

  const at = live ? (summary.t_now ?? 0) : now; // live: engine clock, replay: video position
  useEffect(() => {
    if (live) lastLive.current = at;
  }, [live, at]);
  const shown = summary.events.filter((e) => e.t <= (live ? at : reached));
  const current = summary.events.findLastIndex((e) => e.t <= at);
  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: "smooth" });
  }, [shown.length]);

  const board = rank(summary.events, summary.workers, at);
  const present = attendance(summary.workers, at);
  const inKitchen = present.filter((p) => p.status === "in").length; // matches the table: not yet left
  const visible = headcountAt(summary.headcount ?? [], at); // on camera this second (some may be hidden)
  const seek = (t: number) => {
    if (video.current) video.current.currentTime = t;
  };

  return (
    <div className="grid min-w-0 gap-4 xl:grid-cols-[1fr_340px]">
      <div className="min-w-0 space-y-4">
        {live ? (
          <div className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element -- raw per-second frames, nothing to optimise */}
            <img
              src={`/api/live/${clip}?f=frame&n=${frameNo}`}
              alt="Live camera with detections"
              className="max-h-[62vh] w-full rounded-xl border border-zinc-800 bg-black object-contain"
            />
            <span className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-red-600 px-2.5 py-1 text-xs font-semibold">
              <span className="size-1.5 animate-pulse rounded-full bg-white" /> LIVE
            </span>
          </div>
        ) : (
          <video
            ref={video}
            src={`/clips/${clip}/annotated.mp4`}
            controls
            muted
            playsInline
            className="max-h-[62vh] w-full rounded-xl border border-zinc-800 bg-black object-contain"
          />
        )}

        <section className="rounded-xl border border-zinc-800 bg-zinc-900/60">
          <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-zinc-800 px-4 py-3">
            <h2 className="font-medium">Attendance</h2>
            <span className="text-sm">
              <b className="text-lg">{inKitchen}</b> <span className="text-zinc-400">in kitchen · {visible} visible on camera now</span>
            </span>
          </header>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-zinc-500">
              <tr>
                <th className="px-4 py-2 font-normal">Worker</th>
                <th className="px-2 py-2 font-normal">Status</th>
                <th className="px-2 py-2 font-normal">In kitchen</th>
                <th className="px-4 py-2 text-right font-normal">Away (breaks)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {present.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-3 text-zinc-500">Nobody has arrived yet.</td></tr>
              )}
              {present.map((p) => (
                <tr key={p.worker}>
                  <td className="px-4 py-2 font-medium">{p.worker}</td>
                  <td className="px-2 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs ${
                      p.status === "in" ? "bg-emerald-500/15 text-emerald-300"
                        : p.status === "away" ? "bg-amber-400/15 text-amber-300" : "bg-zinc-700/60 text-zinc-300"
                    }`}>
                      {p.status === "in" ? "In" : p.status === "away" ? `Away since ${mmss(p.since)}` : `Left ${mmss(p.since)}`}
                    </span>
                  </td>
                  <td className="px-2 py-2 font-mono text-xs text-zinc-300">{dur(p.inS)}</td>
                  <td className="px-4 py-2 text-right font-mono text-xs text-zinc-400">
                    {dur(p.awayS)} ({p.breaks})
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

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
          <span className="ml-auto font-mono text-xs text-zinc-500">{mmss(at)}</span>
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
