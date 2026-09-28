"""Kitchen worker monitoring demo.

Per worker: head cover, gloves, shoes, mask, phone use, working/idle, attendance (time in kitchen,
breaks), entry/exit, uniform ID (ArUco).
Outputs: annotated video, events.csv, summary.json -> ../dashboard/public/clips/<clip>/.

  python monitor.py videos/kitchen.mp4
  python monitor.py 0                      # webcam
  python monitor.py in.mp4 --door 0.5,0,0.5,1   # vertical door line (normalised x1,y1,x2,y2)
  python monitor.py in.mp4 --require head,glove,shoes --away-after 180
  python monitor.py screen                 # LIVE: drag a box over the iVMS-4200 / Hik-Connect view
  python monitor.py screen --region 0,40,960,540 --name hob_live   # reuse the printed region
  python monitor.py screen --window iVMS   # capture the iVMS window itself: other windows may cover it
  python monitor.py in.mp4 --live          # replay a file at real-time speed, as a fake camera
Live runs update the dashboard every second; Ctrl+C ends and saves the session as a normal clip.
"""
import argparse, csv, json, time
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO, YOLOE

from faces import GALLERY, FaceID

HEAD = ["chef hat", "hairnet", "cap"]
SHOES_OK, SHOES_OPEN = ["shoe", "sneaker"], ["sandal", "slipper"]
PROMPTS = ["person", *HEAD, "glove", "face mask", "mobile phone", *SHOES_OK, *SHOES_OPEN]
KEY = {**{n: "head" for n in HEAD}, **{n: "shoes" for n in SHOES_OK}, **{n: "open shoes" for n in SHOES_OPEN}}
# ponytail: zero-shot thresholds picked by eye on stock clips; fine-tuned model replaces these.
# Footwear is strict: feet are tiny on CCTV and a wrong "sandals" alert is worse than "not visible".
CONF = {"person": 0.4, "head": 0.3, "glove": 0.35, "face mask": 0.35, "mobile phone": 0.35,
        "shoes": 0.35, "open shoes": 0.35}
WINDOW_S = 15       # PPE status = majority over the last N s: a supervisor watches, not glances
SETTLE_S = 5        # a worker must be tracked this long before we report on them
MIN_KNOWN = 5       # clear sightings needed before calling compliant/violation; fewer -> unknown
# camera switch = whole picture changes at once (mean abs change of a 64x36 grey thumbnail).
# Measured: CCTV motion < 10, handheld phone video < 40, iVMS camera switch >= 52.
CUT_DIFF = 45
# trained gear model (train.py): class -> (check, compliant?). Both sides are learned, so
# "no hairnet" is seen, not inferred from a missed detection; seeing neither -> unknown.
GEAR = {"hairnet": ("head", True), "no_hairnet": ("head", False), "glove": ("glove", True),
        "no_glove": ("glove", False), "mask": ("face mask", True), "no_mask": ("face mask", False),
        "incorrect_mask": ("face mask", False)}
GEAR_CONF = 0.4
IDLE_S = 10         # no hand/body motion for this long -> idle
MOTION_MIN = 4.0    # mean abs pixel change inside person box; tune per camera
LABEL = {"head": "head cover", "glove": "gloves", "face mask": "mask", "shoes": "proper shoes"}
TAG = {"head": "CAP", "glove": "GLOVES", "face mask": "MASK", "shoes": "SHOES"}

GREEN, RED, AMBER, WHITE = (60, 190, 60), (40, 40, 220), (0, 170, 255), (255, 255, 255)
ARUCO = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))


def inside(pt, box):
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def side(p, a, b):
    return np.sign((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))


def dur(s):
    s = int(round(s))
    return f"{s // 60}m {s % 60:02d}s" if s >= 60 else f"{s}s"


def window_grabber(name, region):
    """grab() -> BGR frame of one app window, read even while other windows cover it (it must
    stay on screen, not minimised). Uses Apple's `screencapture -l`; needs Screen Recording
    permission for the terminal. region = x,y,w,h in window pixels; omitted -> drag a box."""
    import subprocess, tempfile
    import Quartz
    wins = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    match = [w for w in wins if w.get("kCGWindowLayer") == 0 and name.lower() in
             f"{w.get('kCGWindowOwnerName', '')} {w.get('kCGWindowName') or ''}".lower()]
    if not match:
        raise SystemExit(f'no open window matching "{name}": open it (not minimised) and allow Screen Recording '
                         "for your terminal in System Settings > Privacy & Security")
    win = max(match, key=lambda w: w["kCGWindowBounds"]["Width"] * w["kCGWindowBounds"]["Height"])
    tmp = Path(tempfile.gettempdir()) / f"kitchen_window_{win['kCGWindowNumber']}.jpg"
    cmd = ["screencapture", "-x", "-o", "-l", str(win["kCGWindowNumber"]), "-t", "jpg", str(tmp)]

    def full():
        if subprocess.run(cmd, capture_output=True).returncode or (img := cv2.imread(str(tmp))) is None:
            raise SystemExit("window capture failed: allow Screen Recording for your terminal, then rerun")
        return img

    shot = full()
    print(f'capturing window: {win.get("kCGWindowOwnerName")} ({shot.shape[1]}x{shot.shape[0]})')
    if region:
        x, y, w, h = (int(float(v)) for v in region.split(","))
    else:
        k = min(1.0, 1280 / shot.shape[1])
        box = cv2.selectROI("Drag over the camera view, then press Enter", cv2.resize(shot, None, fx=k, fy=k))
        cv2.destroyAllWindows()
        x, y, w, h = (int(v / k) for v in box)
        print(f"region: --region {x},{y},{w},{h}")
    if not (w and h):
        raise SystemExit("no region selected")
    return lambda: np.ascontiguousarray(full()[y:y + h, x:x + w])


def screen_grabber(region):
    """Returns grab() -> BGR frame of a screen area. No --region: drag a box on a screenshot."""
    import mss  # only needed for the screen source
    sct = mss.MSS()
    mon = sct.monitors[1]
    if region:
        x, y, w, h = (int(float(v)) for v in region.split(","))
    else:
        shot = np.array(sct.grab(mon))[:, :, :3]
        k = 1280 / shot.shape[1]  # show a laptop-sized preview; map the box back to screen points
        box = cv2.selectROI("Drag over the camera view, then press Enter", cv2.resize(shot, None, fx=k, fy=k))
        cv2.destroyAllWindows()
        pts = mon["width"] / shot.shape[1] / k  # preview px -> screen points (Retina-safe)
        x, y, w, h = (int(v * pts) for v in box)
        print(f"region: --region {x},{y},{w},{h}")
    if not (w and h):
        raise SystemExit("no screen region selected")
    area = {"left": mon["left"] + x, "top": mon["top"] + y, "width": w, "height": h}
    if np.array(sct.grab(area))[:, :, :3].max() < 10:
        print("warning: capture is black; allow Screen Recording for your terminal in System Settings")
    return lambda: np.ascontiguousarray(np.array(sct.grab(area))[:, :, :3])


def gear_check(gear, full, scale, people):
    """Close-up look at each person: crop them from the full-res frame (with margin), run the
    trained gear model on all crops in one batch. -> {tid: {check: True/False}} (missing = unsure)."""
    crops, tids = [], []
    for tid, b in people:
        x1, y1, x2, y2 = (v * scale for v in b)
        pw, ph = x2 - x1, y2 - y1
        X1, Y1 = max(0, int(x1 - 0.15 * pw)), max(0, int(y1 - 0.15 * ph))
        X2, Y2 = min(full.shape[1], int(x2 + 0.15 * pw)), min(full.shape[0], int(y2 + 0.05 * ph))
        if X2 - X1 > 8 and Y2 - Y1 > 8:
            crops.append(np.ascontiguousarray(full[Y1:Y2, X1:X2]))
            tids.append(tid)
    out = defaultdict(dict)
    for tid, r in zip(tids, gear.predict(crops, imgsz=640, conf=GEAR_CONF, verbose=False) if crops else []):
        best = defaultdict(lambda: {True: 0.0, False: 0.0})
        ch = r.orig_shape[0]
        for c, p, bx in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
            check, ok = GEAR.get(r.names[int(c)], (None, None))
            if check == "head" and (bx[1] + bx[3]) / 2 > 0.6 * ch:
                continue  # "hairnet" near the waist is something else
            if check:
                best[check][ok] = max(best[check][ok], p)
        for check, conf in best.items():  # stronger evidence wins
            out[tid][check] = conf[True] >= conf[False]
    return out


class Worker:
    def __init__(self, win):
        # True/False per analysed frame; shoes also None = feet not visible in this frame
        self.hist = {k: deque(maxlen=win) for k in ("head", "glove", "face mask", "mobile phone", "shoes")}
        self.aruco = None
        self.cand = defaultdict(int)
        self.face = defaultdict(int)  # face-match votes: name -> sightings ("?" = unrecognised)
        self.name = None
        self.last_active = None
        self.side = 0
        self.seen = 0

    def ok(self, k):
        """True/False by majority over the window; None if never checkable (feet hidden)."""
        known = [v for v in self.hist[k] if v is not None]
        return sum(known) / len(known) >= 0.5 if len(known) >= MIN_KNOWN else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--fps", type=float, default=5, help="frames analysed per second")
    ap.add_argument("--out", default=str(Path(__file__).parent.parent / "dashboard/public/clips"),
                    help="one folder per clip; default lands in the dashboard so it ships with it")
    ap.add_argument("--door", help="x1,y1,x2,y2 normalised door line for entry/exit")
    ap.add_argument("--require", default="head,glove", help="required: head,glove,shoes,mask")
    ap.add_argument("--away-after", type=float, default=30,
                    help="seconds unseen on camera before a worker counts as out of the kitchen")
    ap.add_argument("--ignore", action="append", default=[], metavar="x1,y1,x2,y2",
                    help="normalised area to skip, e.g. customer seating (repeatable); tested on feet")
    ap.add_argument("--model", default="models/kitchen-yoloe-v2.pt", help="YOLOE with PROMPTS baked in")
    ap.add_argument("--faces", default=str(GALLERY), help="enrolled face fingerprints (faces.py enroll); skipped if missing")
    ap.add_argument("--gear", default="models/gear.pt",
                    help="trained hairnet/glove model for close-up checks (skipped if the file is missing)")
    ap.add_argument("--live", action="store_true", help="treat a video file as a live camera (real-time pace)")
    ap.add_argument("--region", help="screen source: x,y,w,h in screen points (omit to pick with the mouse)")
    ap.add_argument("--window", help='screen source: capture this app window even when covered, e.g. "iVMS"')
    ap.add_argument("--name", help="clip name in the dashboard (default: file name / hob_live / webcam)")
    ap.add_argument("--snapshots", type=float, metavar="SECONDS",
                    help="save a clean frame every N s to data/snapshots/<name>/ (local, git-ignored) for eval/training")
    a = ap.parse_args()

    screen = a.source == "screen"
    src = int(a.source) if a.source.isdigit() else a.source
    live = screen or isinstance(src, int) or a.live
    if screen:
        grab = window_grabber(a.window, a.region) if a.window else screen_grabber(a.region)
    else:
        cap = cv2.VideoCapture(src)
    src_fps = a.fps if screen else cap.get(cv2.CAP_PROP_FPS) or 30
    step = 1 if live else max(1, round(src_fps / a.fps))  # live: pace by the clock instead
    fps = a.fps if live else src_fps / step
    required = {"head": "head", "glove": "glove", "mask": "face mask", "shoes": "shoes"}
    required = [required[r] for r in a.require.split(",") if r]
    ignore = [[float(v) for v in r.split(",")] for r in a.ignore]

    model = YOLOE(a.model)
    assert list(model.names.values()) == PROMPTS, "model classes don't match PROMPTS"
    gear = YOLO(a.gear) if Path(a.gear).exists() else None
    fid = FaceID(a.faces) if Path(a.faces).exists() else None
    print("face recognition:", f"{len(set(fid.names))} enrolled workers" if fid else "off (no gallery)")
    print("close-up gear model:", a.gear if gear else "none (zero-shot only)")

    name = a.name or ("hob_live" if screen else "webcam" if isinstance(src, int) else Path(src).stem)
    out = Path(a.out) / name
    out.mkdir(parents=True, exist_ok=True)
    writer, prev_gray = None, None
    workers = defaultdict(lambda: Worker(max(1, int(WINDOW_S * fps))))
    events, counts, headcount = [], {"in": 0, "out": 0}, []
    recent = deque(maxlen=max(1, int(WINDOW_S * fps)))  # people per frame, for a steady headcount
    # keyed by worker ID, not track: a re-tracked W01 stays one row / one alert stream
    stats = defaultdict(lambda: {"seen": 0, "bad": defaultdict(int), "checked": defaultdict(int),
                                 "first": None, "last": 0, "out": False, "muted": False, "breaks": []})
    logged = {}

    def log(t, w, e):
        events.append((t, w, e))

    i, t0, written, last_report, last_snap = -1, time.time(), 0, 0.0, -1e9
    prev_thumb, id_base, max_tid, last_cut = None, 0, 0, -1e9
    snap_dir = Path(__file__).parent / "data/snapshots" / name
    if a.snapshots:
        snap_dir.mkdir(parents=True, exist_ok=True)
    try:
      while True:
        if live:  # pace to --fps by the wall clock; a live source never waits on us
            time.sleep(max(0.0, t0 + (i + 1) / fps - time.time()))
            if screen:
                okf, frame = True, grab()
            else:
                if a.live:  # file as fake camera: drop frames we're too slow for
                    behind = int((time.time() - t0) * cap.get(cv2.CAP_PROP_FPS)) - int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                    for _ in range(max(0, behind)):
                        cap.grab()
                okf, frame = cap.read()
        else:
            okf, frame = cap.read()
        if not okf:
            break
        i += 1
        full = frame  # full resolution, for close-up crops
        if frame.shape[1] > 1280:  # 4K phone video -> keep it fast
            s = 1280 / frame.shape[1]
            frame = cv2.resize(frame, None, fx=s, fy=s)
        if i % step:
            # between analysed frames: repaint the last overlay so playback stays smooth
            if writer is not None:
                frame[mask] = overlay[mask]
                writer.write(frame)
            continue
        t = time.time() - t0 if live else i / src_fps
        raw = frame.copy()
        if a.snapshots and t - last_snap >= a.snapshots:
            cv2.imwrite(str(snap_dir / f"{time.strftime('%Y%m%d-%H%M%S')}_{t:07.1f}.jpg"), raw)
            last_snap = t
        H, W = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if a.door:
            d = [float(v) for v in a.door.split(",")]
            pa, pb = (d[0] * W, d[1] * H), (d[2] * W, d[3] * H)

        # camera switched (iVMS / screen capture): new view, new people. Reset tracking instead of
        # reporting everyone as "left the kitchen"; keep IDs unique across views with an offset.
        thumb = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
        if prev_thumb is not None and float(np.abs(thumb - prev_thumb).mean()) > CUT_DIFF:
            if getattr(model, "predictor", None) and getattr(model.predictor, "trackers", None):
                model.predictor.trackers[0].reset()
            id_base = max_tid
            for st in stats.values():
                if not st["out"]:
                    st["out"] = st["muted"] = True  # not in view any more, but they didn't walk out
            recent.clear()
            prev_gray = None
            if t - last_cut > 2:  # one message per switch (it spans a black + a grey frame)
                log(t, "Camera", "camera changed")
            last_cut = t
        prev_thumb = thumb

        r = model.track(frame, persist=True, tracker=str(Path(__file__).with_name("tracker.yaml")), conf=0.2, verbose=False)[0]
        people, items = [], []
        for box, c, p, tid in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist(),
                                  (r.boxes.id.tolist() if r.boxes.id is not None else [None] * len(r.boxes))):
            name = PROMPTS[int(c)]
            key = KEY.get(name, name)
            if p < CONF[key]:
                continue
            if key == "person":
                feet = ((box[0] + box[2]) / 2 / W, box[3] / H)
                if tid is not None and not any(inside(feet, r) for r in ignore):
                    people.append((int(tid) + id_base, box))
                    max_tid = max(max_tid, int(tid) + id_base)
            else:
                items.append((key, box))
        recent.append(len(people))
        n = int(np.median(recent))  # one missed detection shouldn't dip the count
        if not headcount or headcount[-1][1] != n:
            headcount.append((round(t, 1), n))

        sc = full.shape[1] / frame.shape[1]  # analysis frame -> full-res frame
        close = gear_check(gear, full, sc, people) if gear else {}

        corners, ids, _ = ARUCO.detectMarkers(gray)
        markers = [] if ids is None else [(int(m), c[0].mean(0)) for m, c in zip(ids.flatten(), corners)]

        for tid, b in people:
            w = workers[tid]
            w.seen += 1
            x1, y1, x2, y2 = map(int, b)
            h = y2 - y1
            head_zone = (x1, y1 - 0.15 * h, x2, y1 + 0.5 * h)
            foot_zone = (x1, y2 - 0.25 * h, x2, y2 + 0.05 * h)
            found = defaultdict(bool)
            for key, ib in items:
                ctr = ((ib[0] + ib[2]) / 2, (ib[1] + ib[3]) / 2)
                zone = head_zone if key == "head" else foot_zone if key in ("shoes", "open shoes") else b
                found[key] |= inside(ctr, zone)
            for k in ("head", "glove", "face mask"):  # trained close-up check if we have it
                w.hist[k].append(close[tid].get(k) if gear else found[k])
            if gear and found["head"] and w.hist["head"][-1] is not True:
                # trained model knows hairnets only; the zero-shot detector also sees caps / chef hats.
                # Either positively seeing a cover counts; a violation still needs a trained "no hairnet".
                w.hist["head"][-1] = True
            w.hist["mobile phone"].append(found["mobile phone"])
            # feet cut off by the frame edge or no footwear seen -> unknown, not a violation
            feet_visible = y2 < 0.97 * H
            w.hist["shoes"].append(False if feet_visible and found["open shoes"]
                                   else True if feet_visible and found["shoes"] else None)
            for m, ctr in markers:
                if inside(ctr, b) and w.aruco != m:
                    w.cand[m] += 1
                    if w.cand[m] >= 2:  # 2 sightings: one-off pattern matches are noise
                        w.aruco = m
                        if (m, "id") not in logged:  # re-tracks of a known worker aren't news
                            logged[m, "id"] = True
                            log(t, f"W{m:02d}", "identified by uniform badge")
            if fid:  # look for a face in the upper body, at full resolution
                fx1, fy1 = max(0, int((x1 - 0.1 * (x2 - x1)) * sc)), max(0, int((y1 - 0.1 * h) * sc))
                fx2, fy2 = min(full.shape[1], int((x2 + 0.1 * (x2 - x1)) * sc)), min(full.shape[0], int((y1 + 0.55 * h) * sc))
                for fb, emb in fid.faces(np.ascontiguousarray(full[fy1:fy2, fx1:fx2]))[:1] if fx2 > fx1 and fy2 > fy1 else []:
                    who, _ = fid.who(emb, fb[2])
                    w.face[who or "?"] += 1
                    fx, fy = (fx1 + fb[0]) / sc, (fy1 + fb[1]) / sc
                    cv2.rectangle(frame, (int(fx), int(fy)), (int(fx + fb[2] / sc), int(fy + fb[3] / sc)), WHITE, 1)
                known = {n: c for n, c in w.face.items() if n != "?"}
                if known:  # a name sticks only after 3+ matches that agree (>= 70%): one slip can't label anyone
                    top, c = max(known.items(), key=lambda kv: kv[1])
                    if c >= 3 and c >= 0.7 * sum(known.values()) and w.name != top:
                        w.name = top
                        if (top, "face") not in logged:
                            logged[top, "face"] = True
                            log(t, top, "identified by face")
            wid = w.name or (f"W{w.aruco:02d}" if w.aruco is not None else f"Person {tid}")
            st = stats[wid]
            if st["out"]:  # was away from every camera long enough to count as a break
                if not st["muted"]:  # muted = only out of view because the camera switched
                    st["breaks"].append((st["last"], t))
                    log(t, wid, f"back in the kitchen after {dur(t - st['last'])}")
                st["out"] = st["muted"] = False
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
            phone = bool(w.ok("mobile phone"))

            status = {k: w.ok(k) for k in required}
            status["phone"] = phone
            status["idle"] = idle
            for k, v in status.items():
                if v is None:  # can't see it (e.g. feet hidden): neither compliant nor a violation
                    continue
                bad = (v is False) if k in required else v
                st["checked"][k] += 1
                if bad:
                    st["bad"][k] += 1
                # log once the window has settled: initial violations, then every change
                if w.seen > int(SETTLE_S * fps) and bad != logged.get((wid, k), False):
                    logged[wid, k] = bad
                    if k in required:
                        log(t, wid, f"{'missing' if bad else 'wearing'} {LABEL[k]}")
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
            viol = [k for k in required if status[k] is False] + [k for k in ("phone", "idle") if status[k]]
            col = GREEN if not viol else (AMBER if viol == ["idle"] else RED)
            cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
            tags = [TAG[k] + {True: " ok", False: " NO", None: " ?"}[status[k]] for k in required]
            tags.append("PHONE" if phone else "IDLE" if idle else "WORKING")
            lines = [wid, " | ".join(tags)]
            for j, txt in enumerate(lines):
                (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
                yy = max(th + 6, y1) - 8 - (len(lines) - 1 - j) * (th + 8)
                cv2.rectangle(frame, (x1, yy - th - 4), (x1 + tw + 6, yy + 4), col, -1)
                cv2.putText(frame, txt, (x1 + 3, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 1, cv2.LINE_AA)

        # attendance: unseen on camera for --away-after seconds -> left the kitchen (at last sighting)
        for wid, st in stats.items():
            if not st["out"] and t - st["last"] > a.away_after:
                st["out"] = True
                log(st["last"], wid, "left the kitchen")

        for key, ib in items:
            if key in ("mobile phone", "open shoes"):
                cv2.rectangle(frame, tuple(map(int, ib[:2])), tuple(map(int, ib[2:])), RED, 1)
        if markers:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
        for r in ignore:
            cv2.rectangle(frame, (int(r[0] * W), int(r[1] * H)), (int(r[2] * W), int(r[3] * H)), (120, 120, 120), 1)
            cv2.putText(frame, "ignored", (int(r[0] * W) + 10, int(r[3] * H) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1)
        if a.door:
            cv2.line(frame, tuple(map(int, pa)), tuple(map(int, pb)), AMBER, 2)
        hud = f"{time.strftime('%H:%M:%S', time.gmtime(t))}  in kitchen: {headcount[-1][1]}"
        if a.door:
            hud += f"  in: {counts['in']}  out: {counts['out']}"
        cv2.rectangle(frame, (0, 0), (W, 30), (30, 30, 30), -1)
        cv2.putText(frame, hud, (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 1, cv2.LINE_AA)

        if writer is None:
            writer = cv2.VideoWriter(str(out / "annotated.mp4"), cv2.VideoWriter_fourcc(*"avc1"), fps if live else src_fps, (W, H))
        if live:
            # keep the saved video in real time: repeat this frame for every slot it covered
            slots = max(1, int(t * fps) + 1 - written)
            for _ in range(slots):
                writer.write(frame)
            written += slots
            cv2.imwrite(str(out / "latest.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if t - last_report >= 1:  # dashboard polls this
                report(out, stats, events, headcount, required, fps, a.source, t_now=t)
                last_report = t
        else:
            writer.write(frame)
        mask, overlay = (frame != raw).any(axis=2), frame
        prev_gray = gray
        if isinstance(src, int):
            cv2.imshow("kitchen monitor (q to quit)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    except KeyboardInterrupt:  # Ctrl+C ends a live session; everything below still saves it
        pass

    if not screen:
        cap.release()
    writer and writer.release()
    cv2.destroyAllWindows()
    report(out, stats, events, headcount, required, fps, a.source)
    print(f"done -> {out}/annotated.mp4, events.csv, summary.json")


def report(out, stats, events, headcount, required, fps, source, t_now=None):
    events.sort(key=lambda e: e[0])  # "left the kitchen" is logged late, at the last sighting
    workers = []
    for wid, st in sorted(stats.items()):
        seen, bad, checked = st["seen"], st["bad"], st["checked"]
        if seen < 3 * fps:  # drop ghost / passing-through tracks
            continue
        away = sum(e - s for s, e in st["breaks"])
        workers.append({
            "id": wid,
            "on_camera_s": round(seen / fps, 1),
            "first_s": round(st["first"], 1),
            "last_s": round(st["last"], 1),
            "in_kitchen_s": round(st["last"] - st["first"] - away, 1),
            "away_s": round(away, 1),
            "breaks": [[round(s, 1), round(e, 1)] for s, e in st["breaks"]],
            # None = never checkable from this camera (e.g. feet always hidden)
            "compliance": {LABEL[k]: round(100 - 100 * bad[k] / checked[k]) if checked[k] else None
                           for k in required},
            "phone_s": round(bad["phone"] / fps, 1),
            "idle_s": round(bad["idle"] / fps, 1),
        })
    kept = {w["id"] for w in workers}
    events = [e for e in events if e[1] in kept or e[1] == "Camera"]  # drop ghost tracks, keep switches
    with open(out / "events.csv", "w", newline="") as f:
        cw = csv.writer(f)
        cw.writerow(["time_s", "worker", "event"])
        cw.writerows([f"{t:.1f}", w, e] for t, w, e in events)
    (out / "summary.json").write_text(json.dumps({
        "source": str(source),
        "analysed_fps": round(fps, 1),
        "live": t_now is not None,  # dashboard polls while true; a final report flips it off
        "t_now": round(t_now, 1) if t_now is not None else None,
        "headcount": headcount,
        "workers": workers,
        "events": [{"t": round(t, 1), "worker": w, "event": e} for t, w, e in events],
    }, indent=2))


if __name__ == "__main__":
    main()
