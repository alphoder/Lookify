// "How trained is the model?" panel. Numbers from kitchen-demo/runs/gear/results.csv (per pass),
// the held-out test split, and a human-checked review of client CCTV (review.py). Static on purpose:
// they change only when the model is retrained.
const PASSES = [0.364, 0.389, 0.44, 0.449, 0.509, 0.508, 0.548, 0.575, 0.587, 0.594, 0.611, 0.62];

const TEST = [
  { item: "Hairnet", precision: 87, recall: 63 },
  { item: "No hairnet", precision: 80, recall: 55 },
  { item: "Gloves", precision: 77, recall: 59 },
  { item: "Bare hands", precision: 66, recall: 56 },
];

export default function ModelCard() {
  const max = 1; // score scale is 0..1; keep the true baseline so growth isn't exaggerated
  return (
    <section className="mt-10 rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-400">Model status</p>
      <h2 className="mt-1 text-xl font-semibold">How trained is the model?</h2>
      <p className="mt-1 max-w-3xl text-sm text-zinc-400">
        Hairnet and glove checks use our own model, trained for 12 passes (10 hours) on 12,600 real kitchen photos from
        the public Kitchen Hygiene Gear dataset (31,371 images, CC BY 4.0). Next step: tuning on the client&apos;s own
        kitchen footage.
      </p>

      <div className="mt-5 grid gap-6 lg:grid-cols-[1fr_1fr_1fr]">
        <figure>
          <figcaption className="text-sm font-medium">Accuracy score after each training pass</figcaption>
          <p className="text-xs text-zinc-500">mAP50 on unseen photos, 0 to 1. Higher is better.</p>
          <div className="mt-3 flex h-36 items-end gap-0.5 border-b border-zinc-700" role="img"
               aria-label={`Score rose from ${PASSES[0]} after pass 1 to ${PASSES.at(-1)} after pass 12`}>
            {PASSES.map((v, i) => (
              <div key={i} className="group relative flex h-full flex-1 items-end">
                <div className="w-full rounded-t bg-amber-400/80 transition group-hover:bg-amber-300"
                     style={{ height: `${(v / max) * 100}%` }} />
                <span className="pointer-events-none absolute -top-7 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-100 group-hover:block">
                  Pass {i + 1}: {v.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-1 flex justify-between text-xs text-zinc-500">
            <span>Pass 1 · 0.36</span>
            <span>Pass 12 · <b className="text-zinc-200">0.62</b></span>
          </div>
        </figure>

        <div>
          <p className="text-sm font-medium">On 3,028 photos it never saw</p>
          <p className="text-xs text-zinc-500">Precision: when it says X, how often X is right. Recall: how much of X it finds.</p>
          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-xs text-zinc-500">
              <tr><th className="pb-1 font-normal">Item</th><th className="pb-1 text-right font-normal">Precision</th><th className="pb-1 text-right font-normal">Recall</th></tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {TEST.map((r) => (
                <tr key={r.item}>
                  <td className="py-1.5">{r.item}</td>
                  <td className="py-1.5 text-right font-mono">{r.precision}%</td>
                  <td className="py-1.5 text-right font-mono text-zinc-400">{r.recall}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <p className="text-sm font-medium">On the client&apos;s own CCTV</p>
          <p className="text-xs text-zinc-500">Checked against the kitchen&apos;s own facts: hairnets on, no gloves, slippers.</p>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between"><dt>Full-screen camera checks</dt><dd className="font-mono"><b className="text-emerald-400">11</b> of 12 right</dd></div>
            <div className="flex justify-between"><dt>Wrong answers</dt><dd className="font-mono text-emerald-400">0</dd></div>
            <div className="flex justify-between"><dt>Small 4-camera grid: false alerts</dt><dd className="font-mono">108 → 1</dd></div>
          </dl>
          <p className="mt-3 text-xs text-zinc-500">
            When a head, hand or foot isn&apos;t clearly visible it says &quot;not visible&quot; instead of guessing. Far or
            tiny views stay mostly &quot;not visible&quot; until tuned on the client&apos;s footage.
          </p>
        </div>
      </div>
    </section>
  );
}
