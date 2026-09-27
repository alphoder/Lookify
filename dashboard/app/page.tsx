import Link from "next/link";
import { CAN_ANALYZE, getClip, listClips, title } from "@/lib/clips";
import ClipView from "./clip-view";
import ModelCard from "./model-card";
import Upload from "./upload";

const STEPS = [
  ["Camera", "Existing CCTV, sampled at 5 fps"],
  ["Detect", "People, caps, hairnets, gloves, shoes, phones"],
  ["Track", "Same person followed frame to frame"],
  ["Identify", "Uniform badge → worker ID (no face data)"],
  ["Rules", "Kitchen SOP: what's required, what's a violation"],
  ["Report", "Alerts, attendance and breaks, compliance per worker"],
];

export default async function Page(props: PageProps<"/">) {
  const clips = await listClips();
  const q = (await props.searchParams).clip;
  const active = typeof q === "string" && clips.includes(q) ? q : clips[0];
  const summary = active ? await getClip(active) : null;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-400">House of Biryani · Demo</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Kitchen Compliance Monitor</h1>
          <p className="mt-1 text-sm text-zinc-400">Who is working, who is following hygiene rules, and when, from the cameras you already have.</p>
        </div>
      </header>

      <ol className="mb-8 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {STEPS.map(([name, desc], i) => (
          <li key={name} className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
            <p className="text-xs text-zinc-500">0{i + 1}</p>
            <p className="font-medium">{name}</p>
            <p className="mt-0.5 text-xs leading-snug text-zinc-400">{desc}</p>
          </li>
        ))}
      </ol>

      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <aside className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Camera clips</p>
          <nav className="flex gap-2 overflow-x-auto lg:flex-col">
            {clips.map((c) => (
              <Link
                key={c}
                href={`/?clip=${c}`}
                className={`shrink-0 rounded-lg border px-3 py-2 text-sm transition ${
                  c === active ? "border-amber-400/60 bg-amber-400/10 text-amber-200" : "border-zinc-800 hover:border-zinc-600"
                }`}
              >
                {title(c)}
              </Link>
            ))}
          </nav>
          {CAN_ANALYZE && <Upload />}
        </aside>

        {summary && active ? (
          <ClipView key={active} clip={active} summary={summary} />
        ) : (
          <p className="text-zinc-400">No analysed clips yet. Upload one to start.</p>
        )}
      </div>

      <ModelCard />
    </div>
  );
}
