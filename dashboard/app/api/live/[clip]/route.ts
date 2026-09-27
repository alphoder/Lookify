import { readFile } from "node:fs/promises";
import path from "node:path";
import { OUTPUT_DIR, SAFE_NAME } from "@/lib/clips";

// Live session files, rewritten by the engine every second: ?f=frame -> latest.jpg, else summary.json.
// Served here (not as static files) so nothing gets cached.
export async function GET(req: Request, ctx: RouteContext<"/api/live/[clip]">) {
  const { clip } = await ctx.params;
  if (!SAFE_NAME.test(clip)) return new Response("bad clip", { status: 400 });
  const frame = new URL(req.url).searchParams.get("f") === "frame";
  const file = path.join(OUTPUT_DIR, clip, frame ? "latest.jpg" : "summary.json");
  const body = await readFile(file).catch(() => null);
  if (!body) return new Response("not found", { status: 404 });
  return new Response(body, {
    headers: { "Content-Type": frame ? "image/jpeg" : "application/json", "Cache-Control": "no-store" },
  });
}
