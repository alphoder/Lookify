import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { CAN_ANALYZE, ENGINE_DIR } from "@/lib/clips";

// Upload a clip -> run the Python engine on it -> return the new clip name.
// ponytail: blocks until done, one job at a time; add a job queue if this leaves demo use.
export async function POST(req: Request) {
  if (!CAN_ANALYZE) return Response.json({ error: "Analysis runs on the local demo machine only" }, { status: 501 });
  const file = (await req.formData()).get("video");
  if (!(file instanceof File) || !file.type.startsWith("video/"))
    return Response.json({ error: "Upload a video file" }, { status: 400 });

  const clip = `upload_${Date.now()}`;
  const dir = path.join(ENGINE_DIR, "videos", "uploads");
  await mkdir(dir, { recursive: true });
  const input = path.join(dir, `${clip}${path.extname(file.name).toLowerCase() || ".mp4"}`);
  await writeFile(input, Buffer.from(await file.arrayBuffer()));

  const code = await new Promise<number | null>((resolve) => {
    const p = spawn(path.join(ENGINE_DIR, ".venv/bin/python"), ["monitor.py", input], {
      cwd: ENGINE_DIR,
      stdio: "inherit",
    });
    p.on("close", resolve);
    p.on("error", () => resolve(-1));
  });
  if (code !== 0) return Response.json({ error: "Analysis failed, check server logs" }, { status: 500 });
  return Response.json({ clip });
}
