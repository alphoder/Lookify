import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

// Python engine lives next door (local only); it writes one folder per analysed video into
// public/clips, so videos are served as static files and clips ship with the deployment.
export const ENGINE_DIR = path.resolve(process.cwd(), "../kitchen-demo");
export const OUTPUT_DIR = path.join(process.cwd(), "public/clips");
// the engine needs Python + PyTorch, which Vercel can't run: uploads are a local-only feature
export const CAN_ANALYZE = !process.env.VERCEL;
export const SAFE_NAME = /^[\w-]+$/;

export type Summary = {
  source: string;
  analysed_fps: number;
  headcount: [number, number][];
  live?: boolean; // engine still running: dashboard polls /api/live
  t_now?: number | null;
  workers: {
    id: string;
    on_camera_s: number;
    first_s: number;
    last_s: number;
    in_kitchen_s: number;
    away_s: number;
    breaks: [number, number][];
    compliance: Record<string, number | null>; // null = never visible (e.g. feet hidden)
    phone_s: number;
    idle_s: number;
  }[];
  events: { t: number; worker: string; event: string }[];
};

const TITLES: Record<string, string> = {
  client_cam04: "HOB kitchen · Camera 04",
  client_cam2: "HOB kitchen · Camera 2",
  client_cam03: "HOB kitchen · Camera 03",
  revlight_cctv: "Real CCTV · restaurant counter",
  sim_uniform_ids: "Uniform ID badges (simulated)",
  pexels_3768941: "Restaurant kitchen · 2 chefs",
  pexels_36197582: "Wok station · hairnet",
  pexels_4253333: "Prep counter · close-up",
};
export const title = (name: string) => TITLES[name] ?? name.replace(/[_-]+/g, " ");

export async function listClips() {
  const dirs = await readdir(OUTPUT_DIR, { withFileTypes: true }).catch(() => []);
  const names = dirs.filter((d) => d.isDirectory() && SAFE_NAME.test(d.name)).map((d) => d.name);
  // the client's own kitchen first, then other real CCTV, then the ID demo, then the rest
  const order = (n: string) =>
    ["client_cam04", "client_cam2", "client_cam03", "revlight_cctv", "sim_uniform_ids"].indexOf(n) >>> 0;
  return names.sort((a, b) => order(a) - order(b) || a.localeCompare(b));
}

export async function getClip(name: string): Promise<Summary | null> {
  if (!SAFE_NAME.test(name)) return null;
  try {
    return JSON.parse(await readFile(path.join(OUTPUT_DIR, name, "summary.json"), "utf8"));
  } catch {
    return null;
  }
}
