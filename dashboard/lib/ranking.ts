export type Event = { t: number; worker: string; event: string };
export type Seen = { id: string; first_s: number; last_s: number };
export type Rank = {
  worker: string;
  mistakes: number;
  violationS: number;
  onCameraS: number;
  score: number;
  open: string[];
  offCamera: boolean;
};

const START = /^(?:missing|started) (.+)$/; // "missing gloves", "started using phone", "started idle"
const END = /^(?:wearing|stopped) (.+)$/;

// Replays events up to playback time `now`. Only workers already on camera are ranked.
// score = % of on-camera time with no violation at all (overlapping violations counted once).
// Higher score first; ties -> fewer mistakes.
export function rank(events: Event[], workers: Seen[], now: number): Rank[] {
  const acc = new Map<string, Rank & { spans: [number, number][]; end: number }>();
  for (const w of workers) {
    if (w.first_s > now) continue;
    const end = Math.min(now, w.last_s);
    acc.set(w.id, {
      worker: w.id, mistakes: 0, violationS: 0, onCameraS: Math.max(end - w.first_s, 0.1),
      score: 100, open: [], offCamera: now > w.last_s + 1, spans: [], end,
    });
  }

  const open = new Map<string, number>(); // "worker|check" -> start time
  for (const e of events) {
    if (e.t > now) break;
    const r = acc.get(e.worker);
    if (!r) continue; // short ghost track, dropped from the summary
    const s = START.exec(e.event), f = END.exec(e.event);
    if (s && !open.has(`${e.worker}|${s[1]}`)) {
      open.set(`${e.worker}|${s[1]}`, e.t);
      r.mistakes++;
    } else if (f && open.has(`${e.worker}|${f[1]}`)) {
      r.spans.push([open.get(`${e.worker}|${f[1]}`)!, e.t]);
      open.delete(`${e.worker}|${f[1]}`);
    }
  }
  for (const [key, t] of open) {
    const [w, check] = key.split("|");
    const r = acc.get(w)!;
    r.spans.push([t, Math.max(r.end, t)]); // stop counting once they leave camera
    if (!r.offCamera) r.open.push(check);
  }

  const out: Rank[] = [];
  for (const { spans, end, ...r } of acc.values()) {
    void end; // bookkeeping only, not part of Rank
    let covered = 0, reach = -Infinity; // union of violation spans
    for (const [a, b] of spans.sort((x, y) => x[0] - y[0])) {
      covered += Math.max(0, b - Math.max(a, reach));
      reach = Math.max(reach, b);
    }
    r.violationS = covered;
    r.score = Math.max(0, Math.round(100 - (100 * covered) / r.onCameraS));
    out.push(r);
  }
  return out.sort((a, b) => b.score - a.score || a.mistakes - b.mistakes);
}
