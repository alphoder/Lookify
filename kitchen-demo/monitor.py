"""Kitchen worker monitoring demo.

Per worker: head cover, gloves, mask, phone use, working/idle, entry/exit, uniform ID (ArUco).
Outputs: annotated video, events.csv, summary.json -> ../dashboard/public/clips/<clip>/.

  python monitor.py videos/kitchen.mp4
  python monitor.py 0                      # webcam
  python monitor.py in.mp4 --door 0.5,0,0.5,1   # vertical door line (normalised x1,y1,x2,y2)
"""
import argparse, csv, json, time
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLOE

HEAD = ["chef hat", "hairnet", "cap"]
PROMPTS = ["person", *HEAD, "glove", "face mask", "mobile phone"]
# ponytail: zero-shot thresholds picked by eye on stock clips; fine-tuned model replaces these
CONF = {"person": 0.4, "head": 0.3, "glove": 0.35, "face mask": 0.35, "mobile phone": 0.35}
WINDOW_S = 3        # PPE status = majority over last N seconds (kills flicker)
IDLE_S = 10         # no hand/body motion for this long -> idle
MOTION_MIN = 4.0    # mean abs pixel change inside person box; tune per camera

GREEN, RED, AMBER, WHITE = (60, 190, 60), (40, 40, 220), (0, 170, 255), (255, 255, 255)
ARUCO = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))


def inside(pt, box):
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def side(p, a, b):
    return np.sign((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))


class Worker:
    def __init__(self, win):
        self.hist = {k: deque(maxlen=win) for k in ("head", "glove", "face mask", "mobile phone")}
        self.aruco = None
        self.cand = defaultdict(int)
        self.last_active = None
        self.side = 0
        self.seen = 0

    def ok(self, k):
        h = self.hist[k]
        return sum(h) / len(h) >= 0.4 if h else False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--fps", type=float, default=5, help="frames analysed per second")
    ap.add_argument("--out", default=str(Path(__file__).parent.parent / "dashboard/public/clips"),
                    help="one folder per clip; default lands in the dashboard so it ships with it")
    ap.add_argument("--door", help="x1,y1,x2,y2 normalised door line for entry/exit")
    ap.add_argument("--require", default="head,glove", help="PPE required: head,glove,mask")
    ap.add_argument("--ignore", action="append", default=[], metavar="x1,y1,x2,y2",
                    help="normalised area to skip, e.g. customer seating (repeatable); tested on feet")
    ap.add_argument("--model", default="models/kitchen-yoloe.pt", help="YOLOE with PROMPTS baked in")
    a = ap.parse_args()

    src = int(a.source) if a.source.isdigit() else a.source
    cap = cv2.VideoCapture(src)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(src_fps / a.fps))
    fps = src_fps / step
    required = {"head": "head", "glove": "glove", "mask": "face mask"}
    required = [required[r] for r in a.require.split(",") if r]
    ignore = [[float(v) for v in r.split(",")] for r in a.ignore]

    model = YOLOE(a.model)
    assert list(model.names.values()) == PROMPTS, "model classes don't match PROMPTS"

    out = Path(a.out) / (Path(str(a.source)).stem if isinstance(src, str) else "webcam")
    out.mkdir(parents=True, exist_ok=True)
    writer, prev_gray = None, None
    workers = defaultdict(lambda: Worker(max(1, int(WINDOW_S * fps))))
    events, counts = [], {"in": 0, "out": 0}
    # keyed by worker ID, not track: a re-tracked W01 stays one row / one alert stream
    stats = defaultdict(lambda: {"seen": 0, "bad": defaultdict(int), "first": None, "last": 0})
    logged = {}
    efile = open(out / "events.csv", "w", newline="")
    ew = csv.writer(efile)
    ew.writerow(["time_s", "worker", "event"])

    def log(t, w, e):
        events.append((t, w, e))
        ew.writerow([f"{t:.1f}", w, e])

    i, t0 = -1, time.time()
    while True:
        okf, frame = cap.read()
        if not okf:
            break
        i += 1
        if frame.shape[1] > 1280:  # 4K phone video -> keep it fast
            s = 1280 / frame.shape[1]
            frame = cv2.resize(frame, None, fx=s, fy=s)
        if i % step:
            # between analysed frames: repaint the last overlay so playback stays smooth
            if writer is not None:
                frame[mask] = overlay[mask]
                writer.write(frame)
            continue
        t = i / src_fps if isinstance(src, str) else time.time() - t0
        raw = frame.copy()
        H, W = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if a.door:
            d = [float(v) for v in a.door.split(",")]
            pa, pb = (d[0] * W, d[1] * H), (d[2] * W, d[3] * H)

        r = model.track(frame, persist=True, tracker=str(Path(__file__).with_name("tracker.yaml")), conf=0.2, verbose=False)[0]
        people, items = [], []
        for box, c, p, tid in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist(),
                                  (r.boxes.id.tolist() if r.boxes.id is not None else [None] * len(r.boxes))):
            name = PROMPTS[int(c)]
            key = "head" if name in HEAD else name
            if p < CONF[key]:
                continue
            if key == "person":
                feet = ((box[0] + box[2]) / 2 / W, box[3] / H)
                if tid is not None and not any(inside(feet, r) for r in ignore):
                    people.append((int(tid), box))
            else:
                items.append((key, box))

        corners, ids, _ = ARUCO.detectMarkers(gray)
        markers = [] if ids is None else [(int(m), c[0].mean(0)) for m, c in zip(ids.flatten(), corners)]

        for tid, b in people:
            w = workers[tid]
            w.seen += 1
            x1, y1, x2, y2 = map(int, b)
            head_zone = (x1, y1 - 0.15 * (y2 - y1), x2, y1 + 0.5 * (y2 - y1))
            found = defaultdict(bool)
            for key, ib in items:
                ctr = ((ib[0] + ib[2]) / 2, (ib[1] + ib[3]) / 2)
                zone = head_zone if key == "head" else b
                found[key] |= inside(ctr, zone)
            for k in w.hist:
                w.hist[k].append(found[k])
            for m, ctr in markers:
                if inside(ctr, b) and w.aruco != m:
                    w.cand[m] += 1
                    if w.cand[m] >= 2:  # 2 sightings: one-off pattern matches are noise
                        w.aruco = m
                        if (m, "id") not in logged:  # re-tracks of a known worker aren't news
                            logged[m, "id"] = True
                            log(t, f"W{m:02d}", "identified by uniform badge")
            wid = f"W{w.aruco:02d}" if w.aruco is not None else f"Person {tid}"
            st = stats[wid]
            st["seen"] += 1
            st["first"] = t if st["first"] is None else st["first"]
            st["last"] = t

            # activity: pixel change inside the box since last analysed frame
            if prev_gray is not None:
                roi = (slice(max(0, y1), y2), slice(max(0, x1), x2))
                motion = float(cv2.absdiff(gray[roi], prev_gray[roi]).mean()) if y2 > y1 and x2 > x1 else 0
                if motion > MOTION_MIN or w.last_active is None:
                    w.last_active = t
            idle = w.last_active is not None and t - w.last_active > IDLE_S
            phone = w.ok("mobile phone")

            status = {k: w.ok(k) for k in required}
            status["phone"] = phone
            status["idle"] = idle
            for k, v in status.items():
                bad = (not v) if k in required else v
                if bad:
                    stats[wid]["bad"][k] += 1
                # log once the window has settled: initial violations, then every change
                if w.seen > int(WINDOW_S * fps) and bad != logged.get((wid, k), False):
                    logged[wid, k] = bad
                    label = {"head": "head cover", "glove": "gloves", "face mask": "mask"}.get(k, k)
                    if k in required:
                        log(t, wid, f"{'missing' if bad else 'wearing'} {label}")
                    else:
                        log(t, wid, f"{'started' if bad else 'stopped'} {'using phone' if k == 'phone' else 'idle'}")

            if a.door:
                s = side(((x1 + x2) / 2, y2), pa, pb)
                if w.side and s and s != w.side:
                    counts["in" if s > 0 else "out"] += 1
                    log(t, wid, "entered" if s > 0 else "exited")
                if s:
                    w.side = s

            # draw
            viol = [k for k in required if not status[k]] + [k for k in ("phone", "idle") if status[k]]
            col = GREEN if not viol else (AMBER if viol == ["idle"] else RED)
            cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
            tags = [("CAP" if k == "head" else "GLOVES" if k == "glove" else "MASK") + (" ok" if status[k] else " NO")
                    for k in required]
            tags.append("PHONE" if phone else "IDLE" if idle else "WORKING")
            lines = [wid, " | ".join(tags)]
            for j, txt in enumerate(lines):
                (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
                yy = max(th + 6, y1) - 8 - (len(lines) - 1 - j) * (th + 8)
                cv2.rectangle(frame, (x1, yy - th - 4), (x1 + tw + 6, yy + 4), col, -1)
                cv2.putText(frame, txt, (x1 + 3, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 1, cv2.LINE_AA)

        for key, ib in items:
            if key == "mobile phone":
                cv2.rectangle(frame, tuple(map(int, ib[:2])), tuple(map(int, ib[2:])), RED, 1)
        if markers:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
        for r in ignore:
            cv2.rectangle(frame, (int(r[0] * W), int(r[1] * H)), (int(r[2] * W), int(r[3] * H)), (120, 120, 120), 1)
            cv2.putText(frame, "ignored", (int(r[0] * W) + 10, int(r[3] * H) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1)
        if a.door:
            cv2.line(frame, tuple(map(int, pa)), tuple(map(int, pb)), AMBER, 2)
        hud = f"{time.strftime('%H:%M:%S', time.gmtime(t))}  people: {len(people)}"
        if a.door:
            hud += f"  in: {counts['in']}  out: {counts['out']}"
        cv2.rectangle(frame, (0, 0), (W, 30), (30, 30, 30), -1)
        cv2.putText(frame, hud, (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 1, cv2.LINE_AA)

        if writer is None:
            writer = cv2.VideoWriter(str(out / "annotated.mp4"), cv2.VideoWriter_fourcc(*"avc1"), src_fps, (W, H))
        writer.write(frame)
        mask, overlay = (frame != raw).any(axis=2), frame
        prev_gray = gray
        if not isinstance(src, str):
            cv2.imshow("kitchen monitor (q to quit)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    writer and writer.release()
    efile.close()
    cv2.destroyAllWindows()
    report(out, stats, events, required, fps, a.source)
    print(f"done -> {out}/annotated.mp4, events.csv, summary.json")


def report(out, stats, events, required, fps, source):
    names = {"head": "head cover", "glove": "gloves", "face mask": "mask"}
    workers = []
    for wid, st in sorted(stats.items()):
        seen, bad = st["seen"], st["bad"]
        if seen < 3 * fps:  # drop ghost / passing-through tracks
            continue
        workers.append({
            "id": wid,
            "on_camera_s": round(seen / fps, 1),
            "first_s": round(st["first"], 1),
            "last_s": round(st["last"], 1),
            "compliance": {names[k]: round(100 - 100 * bad[k] / seen) for k in required},
            "phone_s": round(bad["phone"] / fps, 1),
            "idle_s": round(bad["idle"] / fps, 1),
        })
    (out / "summary.json").write_text(json.dumps({
        "source": str(source),
        "analysed_fps": round(fps, 1),
        "workers": workers,
        "events": [{"t": round(t, 1), "worker": w, "event": e} for t, w, e in events],
    }, indent=2))


if __name__ == "__main__":
    main()
