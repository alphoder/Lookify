"""Fine-tune the hygiene-gear detector (glove / no_glove / hairnet / no_hairnet / mask...).

Data: "kitchen hygiene gear" v5, 31k images, CC BY 4.0, doi:10.5281/zenodo.16329852
      unzipped to data/kitchen_hygiene/ (see README).

  .venv/bin/python train.py            # fresh run
  .venv/bin/python train.py --resume   # continue after a stop/crash
Best weights land in runs/gear/weights/best.pt; copy to models/gear.pt when happy.
"""
import sys
from pathlib import Path

from ultralytics import YOLO

HERE = Path(__file__).parent.resolve()
last = HERE / "runs/gear/weights/last.pt"
# the dataset yaml needs an absolute path: point it at this checkout (project may move between Macs)
yaml = HERE / "data/kitchen_hygiene/data.yaml"
lines = [l for l in yaml.read_text().splitlines() if not l.startswith("path:")]
yaml.write_text("\n".join([f"path: {yaml.parent}", *lines]) + "\n")

if "--resume" in sys.argv and last.exists():
    YOLO(last).train(resume=True)
else:
    YOLO("yolo11s.pt").train(
        data=str(HERE / "data/kitchen_hygiene/data.yaml"),
        # ponytail: half the data, 12 epochs = ~5-6 h on an M3 GPU; full data / more epochs on a cloud GPU
        fraction=0.5, epochs=12, imgsz=640, batch=16, device="mps", workers=4,
        project=str(HERE / "runs"), name="gear", exist_ok=True,
        save_period=1, plots=True, patience=100,
    )
