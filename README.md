# Kitchen Compliance Monitor (demo)

Camera-based hygiene and activity monitoring for House of Biryani kitchens.

```
kitchen-demo/   Python engine: detection, tracking, uniform-badge IDs, rules -> output/<clip>/
dashboard/      Next.js UI: clips, annotated video, event timeline, per-worker compliance, upload
```

## Run the demo

```bash
npm run dev --prefix dashboard        # http://localhost:3000
```

Upload a clip from the sidebar to analyse it live (about 1 min per 30 s of video on an M3).

## Engine setup (not in git: model 71 MB, videos, venv)

```bash
cd kitchen-demo
uv venv -p 3.12 .venv && uv pip install -p .venv ultralytics opencv-contrib-python lap "git+https://github.com/ultralytics/CLIP.git"
mkdir -p models && .venv/bin/python -c "
from ultralytics import YOLOE
P=['person','chef hat','hairnet','cap','glove','face mask','mobile phone','shoe','sneaker','sandal','slipper']
m=YOLOE('yoloe-11l-seg.pt'); m.set_classes(P, m.get_text_pe(P)); m.save('models/kitchen-yoloe-v2.pt')"
```

Deployed on Vercel (root directory `dashboard`): plays the analysed clips in `dashboard/public/clips`;
uploading/analysing new clips only works locally, since Vercel can't run PyTorch.

## Live demo on HOB's cameras (from our office, via Hik-Connect)

1. Install **iVMS-4200** (Hikvision, Mac/Windows), sign in with the Hik-Connect account: the NVR and its cameras appear.
2. Open a camera in **Live View** (full screen or one tile of a grid).
3. Run the dashboard (`npm run dev --prefix dashboard`) and, in another terminal:
   ```bash
   cd kitchen-demo && .venv/bin/python monitor.py screen --require head,glove --away-after 120
   ```
   Drag a box over the camera picture and press Enter (it prints `--region ...` to reuse next time).
   First run: macOS asks for **Screen Recording** permission for the terminal; allow it and rerun.
4. Open http://localhost:3000/?clip=hob_live: live frame, findings chat, attendance and ranking update every second.
5. Ctrl+C ends the session; it's saved as a normal replayable clip. `hob_*` clips are git-ignored: HOB footage
   stays local and never reaches GitHub/Vercel.

Covered-window mode (dashboard can sit on top of iVMS): `monitor.py screen --window iVMS` captures that app's
window directly via macOS `screencapture -l` (window must stay open, not minimised). Also works with
`--window "iPhone Mirroring"` for the Hik-Connect phone app.

Rehearse without their cameras: `monitor.py videos/revlight_cctv.mp4 --live --name hob_rehearsal`.

## Worker identity: face recognition

OpenCV YuNet (MIT) + SFace (Apache-2.0), fully local. **Consent first** (India DPDP Act): enrol only workers
who were told and agreed in writing.

1. Per worker, 5-10 photos (phone is fine) in `kitchen-demo/data/faces/<Name>/`: face the camera, a little
   left/right, **with the hairnet on**, good light, one face per photo.
2. `cd kitchen-demo && .venv/bin/python faces.py enroll` -> `data/faces/gallery.npz` (fingerprints only;
   the photos can then be deleted). Check a photo: `.venv/bin/python faces.py test photo.jpg`.
3. `monitor.py` picks the gallery up automatically. A name sticks after 3+ agreeing face matches; faces
   under 80 px need a stronger match; otherwise the worker stays "Person N" (unknown, never guessed).
   Tested: 2 enrolled people recognised, 0 of 12 CCTV strangers mislabelled.
   A worker leaves: delete their folder, re-run enroll.

## Engine directly

```bash
cd kitchen-demo
.venv/bin/python monitor.py videos/clip.mp4                 # -> output/clip/
.venv/bin/python monitor.py 0                               # live webcam window, q to quit
.venv/bin/python monitor.py clip.mp4 --door 0.5,0,0.5,1     # count entries/exits across a line
.venv/bin/python monitor.py clip.mp4 --require head,glove,mask
.venv/bin/python monitor.py clip.mp4 --ignore 0,0,0.47,0.28      # skip people standing in an area (customers)
.venv/bin/python badges.py 1 12                             # printable badges W01..W12 -> badges/
```

## What it detects

| Check | How |
|---|---|
| Cap / hairnet, gloves, mask | YOLOE open-vocabulary detector, text prompts, **no training yet** |
| Shoes | Footwear prompts in the foot zone; "not visible" when feet are hidden or cut off. Unreliable on overhead CCTV until fine-tuned: best checked by an entrance camera |
| Attendance | Headcount, time in kitchen per worker, breaks: unseen on every camera for `--away-after` s (demo 15 s, production 2 to 5 min) = left. Needs uniform badges to link a returning worker |
| Phone use | Same detector ("mobile phone") inside a worker's box |
| Working vs idle | Pixel motion inside the worker's box; idle after 10 s still |
| Worker ID | ArUco badge on uniform (`badges.py`); no face data |
| Entry / exit | Worker crosses a configurable line (`--door`) |

## Demo caveats (say these in the meeting)

- Zero-shot model: accuracy is good on clear shots, weaker on small/far workers. Fine-tuning on
  their own footage (plus the CC-BY 31k-image kitchen dataset, doi:10.5281/zenodo.16329852) is phase 2.
- `sim_uniform_ids` has badges pasted on digitally. For a real test, print a badge from
  `kitchen-demo/badges/`, tape it to a shirt, record 30 s on a phone, upload it.
- Ultralytics YOLOE is AGPL-3.0: fine for a demo; production needs a commercial licence or an
  Apache-licensed detector (RT-DETR / YOLOX).
- Videos: Pexels (free licence). `revlight_cctv` is Revlight Security's YouTube demo
  (youtube.com/watch?v=DBl7MmHlQK0, standard YouTube licence): internal testing only unless
  Revlight agrees; otherwise tell HOB it's a public sample clip.
- Real CCTV notes: analysed at 5 fps, overlay repainted on every frame for smooth playback;
  `tracker.yaml` keeps IDs through counter occlusions; customers at the counter can still be
  counted as staff (not an issue for HOB's delivery-only kitchens).
