export type Presence = { id: string; first_s: number; last_s: number; breaks: [number, number][] };
export type Attendance = { worker: string; status: "in" | "away" | "left"; since: number; inS: number; awayS: number; breaks: number };

// Attendance as of playback time `now`: who's in the kitchen, how long they've been in it,
// and breaks taken so far (only breaks that have started count; an ongoing one counts up to now).
export function attendance(workers: Presence[], now: number): Attendance[] {
  const out: Attendance[] = [];
  for (const w of workers) {
    if (w.first_s > now) continue; // not arrived yet
    const started = w.breaks.filter(([s]) => s <= now);
    const awayS = started.reduce((sum, [s, e]) => sum + Math.min(e, now) - s, 0);
    const current = started.find(([, e]) => now < e);
    const left = !current && now > w.last_s + 1;
    const end = left ? w.last_s : now;
    out.push({
      worker: w.id,
      status: current ? "away" : left ? "left" : "in",
      since: current ? current[0] : left ? w.last_s : w.first_s,
      inS: Math.max(0, end - w.first_s - awayS),
      awayS,
      breaks: started.length,
    });
  }
  return out;
}

// people in the kitchen at `now`, from the engine's [time, count] change points
export const headcountAt = (hc: [number, number][], now: number) => hc.findLast(([t]) => t <= now)?.[1] ?? 0;
