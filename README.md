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
P=['person','chef hat','hairnet','cap','glove','face mask','mobile phone']
m=YOLOE('yoloe-11l-seg.pt'); m.set_classes(P, m.get_text_pe(P)); m.save('models/kitchen-yoloe.pt')"
```

Deployed on Vercel (root directory `dashboard`): plays the analysed clips in `dashboard/public/clips`;
uploading/analysing new clips only works locally, since Vercel can't run PyTorch.

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
