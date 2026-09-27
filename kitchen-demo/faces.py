"""Face recognition for worker identity (OpenCV YuNet detector, MIT + SFace recognizer, Apache-2.0).

Enrol: put 5-10 photos per worker in data/faces/<Name>/ (front + a bit left/right, with the
hairnet on, good light), then
  .venv/bin/python faces.py enroll            # -> data/faces/gallery.npz (face fingerprints only)
  .venv/bin/python faces.py test photo.jpg    # who does it think this is?
After enrolling, the photos can be deleted: monitor.py only needs gallery.npz.

Privacy (India DPDP Act): enrol only workers who were told and gave written consent; keep all of
data/faces local (git-ignored); delete a worker's folder + re-enrol when they leave.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent
FACES = HERE / "data/faces"
GALLERY = FACES / "gallery.npz"
# SFace cosine similarity: its authors' same-person threshold is 0.363; we ask for more, plus a
# clear lead over the next-best worker, and answer "unknown" otherwise.
MATCH, MARGIN = 0.42, 0.08
MATCH_SMALL, SMALL = 0.55, 80  # faces under 80 px (typical CCTV) must match more strongly
MIN_FACE = 36  # px: smaller faces are too blurry to trust


class FaceID:
    def __init__(self, gallery=GALLERY):
        self.det = cv2.FaceDetectorYN.create(str(HERE / "models/face_yunet.onnx"), "", (320, 320), 0.8)
        self.rec = cv2.FaceRecognizerSF.create(str(HERE / "models/face_sface.onnx"), "")
        self.names, self.embs = [], np.zeros((0, 128), np.float32)
        if Path(gallery).exists():
            g = np.load(gallery)
            self.names, self.embs = list(g["names"]), g["embs"]

    def faces(self, img):
        """All faces in img, biggest first: (box x,y,w,h, 128-d unit fingerprint)."""
        h, w = img.shape[:2]
        self.det.setInputSize((w, h))
        _, found = self.det.detect(img)
        out = []
        for f in [] if found is None else sorted(found, key=lambda f: -f[2] * f[3]):
            if min(f[2], f[3]) < MIN_FACE:
                continue
            e = self.rec.feature(self.rec.alignCrop(img, f)).flatten()
            out.append((f[:4].astype(int), e / np.linalg.norm(e)))
        return out

    def who(self, emb, size=SMALL):
        """(name or None, score): best worker, only if clearly the best and above threshold.
        size = face width in px: small blurry faces must clear a higher bar."""
        if not self.names:
            return None, 0.0
        sims = self.embs @ emb
        per = {}
        for n, s in zip(self.names, sims):
            per[n] = max(per.get(n, -1.0), float(s))
        ranked = sorted(per.items(), key=lambda kv: -kv[1])
        best, score = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else -1.0
        bar = MATCH if size >= SMALL else MATCH_SMALL
        return (best, score) if score >= bar and score - second >= MARGIN else (None, score)


def enroll():
    fid = FaceID(gallery="/nonexistent")
    names, embs = [], []
    for d in sorted(p for p in FACES.iterdir() if p.is_dir()):
        ok = 0
        for f in sorted(d.iterdir()):
            img = cv2.imread(str(f))
            if img is None:
                continue
            if max(img.shape[:2]) > 1600:  # phone photos: detector works best around this size
                img = cv2.resize(img, None, fx=1600 / max(img.shape[:2]), fy=1600 / max(img.shape[:2]))
            found = fid.faces(img)
            if len(found) != 1:
                print(f"  skip {f.name}: {'no clear face' if not found else 'more than one face'}")
                continue
            names.append(d.name)
            embs.append(found[0][1])
            ok += 1
        print(f"{d.name}: {ok} usable photos" + ("  <- need at least 3" if ok < 3 else ""))
    np.savez(GALLERY, names=np.array(names), embs=np.array(embs, np.float32).reshape(-1, 128))
    print(f"saved {len(embs)} fingerprints for {len(set(names))} workers -> {GALLERY}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["enroll"]:
        enroll()
    elif sys.argv[1:2] == ["test"]:
        fid = FaceID()
        for box, e in fid.faces(cv2.imread(sys.argv[2])):
            print(box.tolist(), *fid.who(e, box[2]))
    else:
        print(__doc__)
