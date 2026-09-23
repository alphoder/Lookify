"""Printable worker ID badges (ArUco 4x4). Print at 100% scale on A4.

  python badges.py 1 12     # badges for workers W01..W12 -> badges/
"""
import sys
from pathlib import Path

import cv2
import numpy as np

DPI = 300
MARKER_CM = 12  # ~30px at 4-5 m on 1080p CCTV; see README
px = lambda cm: int(cm / 2.54 * DPI)
DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def badge(wid):
    m = px(MARKER_CM)
    pad = px(1.5)  # white quiet zone around the code is required for detection
    card = np.full((m + 2 * pad + px(3), m + 2 * pad), 255, np.uint8)
    card[pad:pad + m, pad:pad + m] = cv2.aruco.generateImageMarker(DICT, wid, m)
    txt = f"W{wid:02d}"
    (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 5, 12)
    cv2.putText(card, txt, ((card.shape[1] - tw) // 2, m + pad + px(2.3)), cv2.FONT_HERSHEY_SIMPLEX, 5, 0, 12)
    return cv2.copyMakeBorder(card, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=180)  # cut line


def main(first=1, last=6):
    out = Path("badges")
    out.mkdir(exist_ok=True)
    for i in range(first, last + 1):  # one 12 cm badge per portrait A4 page
        c = badge(i)
        sheet = np.full((px(29.7), px(21.0)), 255, np.uint8)
        y, x = (sheet.shape[0] - c.shape[0]) // 2, (sheet.shape[1] - c.shape[1]) // 2
        sheet[y:y + c.shape[0], x:x + c.shape[1]] = c
        f = out / f"badge_W{i:02d}.png"
        cv2.imwrite(str(f), sheet)
        print(f)


if __name__ == "__main__":
    main(*map(int, sys.argv[1:3])) if len(sys.argv) > 2 else main()
