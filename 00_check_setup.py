"""
Step 0: check that the Python environment and the data are ready.
Run it first, or whenever a later step reports a missing file.
"""
import importlib
import sys

OK, BAD = "[ ok ]", "[MISS]"
problems = 0

print(f"Python {sys.version.split()[0]}  ({sys.executable})")
if sys.version_info < (3, 10):
    print(f"{BAD} Python 3.10 or newer is needed")
    problems += 1

print("\nPackages")
for mod in ["numpy", "pandas", "scipy", "shapely", "pyogrio", "pyarrow", "geopandas",
            "rasterio", "rasterstats", "mapclassify", "matplotlib", "imageio",
            "imageio_ffmpeg", "requests", "overturemaps"]:
    try:
        m = importlib.import_module(mod)
        print(f"{OK} {mod} {getattr(m, '__version__', '')}")
    except Exception as e:
        print(f"{BAD} {mod}: {e}")
        problems += 1

try:
    import imageio_ffmpeg
    print(f"{OK} ffmpeg for video: {imageio_ffmpeg.get_ffmpeg_exe()}")
except Exception as e:
    print(f"{BAD} ffmpeg: {e}")
    problems += 1

print("\nFont")
try:
    from matplotlib import font_manager
    f = font_manager.findfont("Times New Roman", fallback_to_default=False)
    print(f"{OK} Times New Roman: {f}")
except Exception:
    print(f"{BAD} Times New Roman not found; maps will use a similar serif font")

print("\nData")
from common import (BUILDINGS, GHSL_DIR, THANAS, WATER, EPOCHS, NASA_CSV,
                    find_pvout, find_worldpop)

checks = [
    ("Thana boundaries", THANAS.exists(), THANAS.name),
    ("Solar Atlas PVOUT", find_pvout() is not None, find_pvout()),
    ("WorldPop 2020", find_worldpop() is not None, find_worldpop()),
    ("Overture buildings", BUILDINGS.exists(), "run 01_download_data.py"),
    ("Overture water (optional)", WATER.exists(), "run 01_download_data.py"),
    ("NASA POWER (optional backup)", NASA_CSV.exists(), "run 01_download_data.py"),
]
crops = [GHSL_DIR / f"built_s_{y}.tif" for y in EPOCHS]
zips = list(GHSL_DIR.glob("*_R7_C28.zip"))
checks.append(("GHSL 12 epochs (cropped)", all(c.exists() for c in crops),
               f"{sum(c.exists() for c in crops)}/12 cropped, {len(zips)} zips waiting"))
for label, ok, note in checks:
    optional = "optional" in label
    print(f"{OK if ok else ('[ -- ]' if optional else BAD)} {label}: {note if not ok else 'found'}")
    if not ok and not optional:
        problems += 1

print("\n" + ("All set. Next: 01_download_data.py (if anything is missing) then 02, 03, 04."
              if problems == 0 else f"{problems} item(s) to fix above."))
