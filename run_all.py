"""
Run the whole pipeline in order:
    check > download > analysis > time-lapse > maps

    python run_all.py            everything
    python run_all.py --from 2   start at step 2 (skip check and download)
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    ("00_check_setup.py", "Check environment and data"),
    ("01_download_data.py", "Download and prepare data"),
    ("02_rooftop_solar.py", "Rooftop solar per building and thana"),
    ("03_timelapse.py", "Time-lapse video 1975 to 2030"),
    ("04_static_maps.py", "Map boards and PDF"),
]

ap = argparse.ArgumentParser()
ap.add_argument("--from", dest="start", type=int, default=0, help="first step number (0 to 4)")
args = ap.parse_args()

for i, (script, label) in enumerate(STEPS):
    if i < args.start:
        continue
    print(f"\n{'=' * 70}\nStep {i}: {label}  ({script})\n{'=' * 70}", flush=True)
    r = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT)
    if r.returncode != 0 and i >= 2:
        sys.exit(f"\nStep {i} failed. Fix the error above, then run: python run_all.py --from {i}")

print("\nAll done. Results are in the output folder.")
