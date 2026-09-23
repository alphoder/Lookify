// node lib/ranking.check.ts
import assert from "node:assert/strict";
import { rank } from "./ranking.ts";

const ev = [
  { t: 2, worker: "W02", event: "missing gloves" },
  { t: 3, worker: "W01", event: "missing head cover" },
  { t: 5, worker: "W01", event: "wearing head cover" },
  { t: 6, worker: "W02", event: "started using phone" },
  { t: 7, worker: "ghost", event: "missing gloves" }, // not in summary -> ignored
];
const seen = [
  { id: "W01", first_s: 1, last_s: 11 },
  { id: "W02", first_s: 2, last_s: 8 }, // leaves camera at 8
  { id: "W03", first_s: 20, last_s: 30 }, // not on camera yet at 10
];

const at10 = rank(ev, seen, 10);
assert.deepEqual(at10.map((r) => r.worker), ["W01", "W02"]); // W03 not ranked before appearing
// W01: on camera 1->10 = 9 s, head cover missing 3->5 = 2 s -> 100 - 22.2 = 78
assert.deepEqual(at10[0], { worker: "W01", mistakes: 1, violationS: 2, onCameraS: 9, score: 78, open: [], offCamera: false });
// W02: on camera 2->8; gloves 2->8 and phone 6->8 overlap -> union 6 s of 6 -> 0; left camera, nothing "now"
assert.deepEqual(at10[1], { worker: "W02", mistakes: 2, violationS: 6, onCameraS: 6, score: 0, open: [], offCamera: true });

const at7 = rank(ev, seen, 7); // mid-playback: W02 still on camera with both violations open
assert.deepEqual(at7[1].open.sort(), ["gloves", "using phone"]);
assert.equal(at7[1].violationS, 5); // overlap 2->7 counted once, not 5 + 1
assert.equal(rank(ev, seen, 25).length, 3); // W03 appears once playback reaches 20 s
console.log("ranking ok");
