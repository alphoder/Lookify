// node lib/attendance.check.ts
import assert from "node:assert/strict";
import { attendance, headcountAt } from "./attendance.ts";

const w = { id: "W01", first_s: 10, last_s: 100, breaks: [[30, 50]] as [number, number][] };

assert.deepEqual(attendance([w], 5), []); // not arrived yet
assert.deepEqual(attendance([w], 20), [{ worker: "W01", status: "in", since: 10, inS: 10, awayS: 0, breaks: 0 }]);
// mid-break: 20 s worked (10->30), away 30->40 so far
assert.deepEqual(attendance([w], 40), [{ worker: "W01", status: "away", since: 30, inS: 20, awayS: 10, breaks: 1 }]);
// back: 10->60 = 50 s minus 20 s break
assert.deepEqual(attendance([w], 60), [{ worker: "W01", status: "in", since: 10, inS: 30, awayS: 20, breaks: 1 }]);
// gone for good after last sighting at 100: time stops counting there
assert.deepEqual(attendance([w], 200), [{ worker: "W01", status: "left", since: 100, inS: 70, awayS: 20, breaks: 1 }]);

const hc: [number, number][] = [[0, 1], [4, 3], [9, 2]];
assert.equal(headcountAt(hc, 5), 3);
assert.equal(headcountAt(hc, 9), 2);
assert.equal(headcountAt([], 5), 0);
console.log("attendance ok");
