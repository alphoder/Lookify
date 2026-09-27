"""Accuracy review sheets: every person in a folder of frames, cropped and labelled with the
model's per-frame verdict (head cover / gloves), tiled into contact sheets a human can check.

  .venv/bin/python review.py data/snapshots/hob_live            # -> data/review/hob_live/sheet_*.jpg
  .venv/bin/python review.py data/snapshots/hob_live --gear none # zero-shot only, for before/after

Also writes verdicts.csv (sheet, tile, frame, head, gloves) so a reviewer can note which tiles are wrong.
"""
import argparse, csv
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO, YOLOE

from monitor import CONF, KEY, PROMPTS, gear_check

TILE, COLS, ROWS = 256, 6, 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames")
    ap.add_argument("--gear", default="models/gear.pt", help='trained close-up model, or "none"')
    ap.add_argument("--model", default="models/kitchen-yoloe-v2.pt")
    a = ap.parse_args()

    det = YOLOE(a.model)
    gear = None if a.gear == "none" or not Path(a.gear).exists() else YOLO(a.gear)
    out = Path("data/review") / (Path(a.frames).name + ("" if gear else "_zeroshot"))
    out.mkdir(parents=True, exist_ok=True)
    tiles, rows = [], []
    for f in sorted(Path(a.frames).glob("*.jpg")):
        full = cv2.imread(str(f))
        frame = cv2.resize(full, None, fx=1280 / full.shape[1], fy=1280 / full.shape[1]) if full.shape[1] > 1280 else full
        r = det.predict(frame, conf=0.2, verbose=False)[0]
        people, items = [], []
        for i, (b, c, p) in enumerate(zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist())):
            key = KEY.get(PROMPTS[int(c)], PROMPTS[int(c)])
            if p >= CONF[key]:
                (people if key == "person" else items).append((i, b) if key == "person" else (key, b))
        scale = full.shape[1] / frame.shape[1]
        close = gear_check(gear, full, scale, people) if gear else {}
        for pid, b in people:
            if gear:
                v = close.get(pid, {})
                head, glove = v.get("head"), v.get("glove")
            else:  # zero-shot: present in zone = ok, absent = violation (the old behaviour)
                x1, y1, x2, y2 = b
                hz = (x1, y1 - 0.15 * (y2 - y1), x2, y1 + 0.5 * (y2 - y1))
                c = lambda ib: ((ib[0] + ib[2]) / 2, (ib[1] + ib[3]) / 2)
                inz = lambda pt, z: z[0] <= pt[0] <= z[2] and z[1] <= pt[1] <= z[3]
                head = any(k == "head" and inz(c(ib), hz) for k, ib in items)
                glove = any(k == "glove" and inz(c(ib), b) for k, ib in items)
            x1, y1, x2, y2 = (int(v * scale) for v in b)
            crop = full[max(0, y1):y2, max(0, x1):x2]
            if crop.size == 0:
                continue
            k = TILE / max(crop.shape[:2])
            tile = np.zeros((TILE, TILE, 3), np.uint8)
            small = cv2.resize(crop, None, fx=k, fy=k)
            tile[:small.shape[0], :small.shape[1]] = small
            label = lambda v: "?" if v is None else "ok" if v else "NO"
            txt = f"#{len(tiles) % (COLS * ROWS)} CAP {label(head)} GLV {label(glove)}"
            cv2.rectangle(tile, (0, TILE - 22), (TILE, TILE), (0, 0, 0), -1)
            cv2.putText(tile, txt, (4, TILE - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            rows.append([len(tiles) // (COLS * ROWS), len(tiles) % (COLS * ROWS), f.name, label(head), label(glove)])
            tiles.append(tile)
    for s in range(0, len(tiles), COLS * ROWS):
        page = tiles[s:s + COLS * ROWS]
        page += [np.zeros_like(tiles[0])] * (COLS * ROWS - len(page))
        cv2.imwrite(str(out / f"sheet_{s // (COLS * ROWS):02d}.jpg"),
                    np.vstack([np.hstack(page[r * COLS:(r + 1) * COLS]) for r in range(ROWS)]))
    with open(out / "verdicts.csv", "w", newline="") as fh:
        csv.writer(fh).writerows([["sheet", "tile", "frame", "head", "gloves"], *rows])
    print(f"{len(tiles)} people from {len(list(Path(a.frames).glob('*.jpg')))} frames -> {out}")


if __name__ == "__main__":
    main()
