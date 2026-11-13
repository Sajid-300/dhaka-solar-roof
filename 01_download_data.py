"""
Step 1: download and prepare all input data.

Anything already in data/ is kept and skipped, so this is safe to re-run.
Each source is independent: if one fails, the others still run.
"""
import csv
import subprocess
import sys
import zipfile

import geopandas as gpd
import requests

from common import (BUILDINGS, DATA, EPOCHS, GHSL_DIR, NASA_CSV, THANAS, UTM,
                    VIEW, WATER, find_pvout, find_worldpop)

thanas = gpd.read_file(THANAS, layer="thanas")
W, S, E, N = thanas.total_bounds
print(f"Study area: {len(thanas)} thanas")


def download(url, dest, label):
    """Stream a file to disk; skip if it already exists."""
    if dest.exists() and dest.stat().st_size > 0:
        print(f"[skip] {label}: already have {dest.name}")
        return True
    print(f"[get ] {label} ...")
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        print(f"[ ok ] {label}: {dest.stat().st_size / 1e6:.1f} MB")
        return True
    except Exception as e:
        if dest.exists():
            dest.unlink()
        print(f"[FAIL] {label}: {e}")
        return False


def overture(kind, dest, bbox):
    """Download one Overture Maps theme for a bounding box as GeoParquet."""
    if dest.exists():
        print(f"[skip] Overture {kind}: already downloaded")
        return
    print(f"[get ] Overture {kind} (can take a few minutes) ...")
    b = ",".join(f"{v:.4f}" for v in bbox)
    args = ["download", f"--bbox={b}", "-f", "geoparquet", f"--type={kind}", "-o", str(dest)]
    r = subprocess.run([sys.executable, "-m", "overturemaps"] + args)
    if r.returncode != 0:
        r = subprocess.run(["overturemaps"] + args)
    print(f"[ ok ] Overture {kind}" if dest.exists() else f"[FAIL] Overture {kind}, see error above")


def section(name, fn):
    try:
        fn()
    except Exception as e:
        print(f"[FAIL] {name}: {e}")


# ----------------------------------------------------- 1. Buildings + water
# Overture buildings merge OpenStreetMap, Microsoft and Google footprints.
section("Buildings", lambda: overture("building", BUILDINGS, (W, S, E, N)))
# Rivers and water bodies, only for map context (drawn under the data).
section("Water", lambda: overture("water", WATER, VIEW))


# ------------------------------------------------ 2. NASA POWER (backup)
def nasa():
    if NASA_CSV.exists():
        print("[skip] NASA POWER: already downloaded")
        return
    print("[get ] NASA POWER GHI climatology ...")
    rows, cache = [], {}
    pts = thanas.to_crs(UTM).representative_point().to_crs(4326)
    for name, p in zip(thanas["thana"], pts):
        key = (round(p.y * 2) / 2, round(p.x * 1.6) / 1.6)  # POWER grid cell
        if key not in cache:
            url = ("https://power.larc.nasa.gov/api/temporal/climatology/point"
                   f"?parameters=ALLSKY_SFC_SW_DWN&community=RE"
                   f"&longitude={p.x:.4f}&latitude={p.y:.4f}&format=JSON")
            cache[key] = requests.get(url, timeout=60).json()[
                "properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
        m = cache[key]
        row = {"thana": name, "ghi_ann_kwh_m2_day": m["ANN"]}
        row.update({f"ghi_{k.lower()}": v for k, v in m.items() if k != "ANN"})
        rows.append(row)
    with open(NASA_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print("[ ok ] NASA POWER")


section("NASA POWER", nasa)


# ------------------------------------------------ 3. Global Solar Atlas
def gsa():
    if find_pvout():
        print(f"[skip] Global Solar Atlas: found {find_pvout().name}")
        return
    z = DATA / "bangladesh_gsa.zip"
    ok = download("https://api.globalsolaratlas.info/download/Bangladesh/"
                  "Bangladesh_GISdata_LTAy_YearlyMonthlyTotals_GlobalSolarAtlas-v2_GEOTIFF.zip",
                  z, "Global Solar Atlas")
    if ok:
        zipfile.ZipFile(z).extractall(DATA / "gsa")
    if not find_pvout():
        print("       Manual: https://globalsolaratlas.info/download/bangladesh > "
              "LTAym_YearlyMonthlyTotals (GeoTIFF), unzip into data/gsa/")


section("Global Solar Atlas", gsa)


# ------------------------------------------------------- 4. WorldPop
def worldpop():
    if find_worldpop():
        print(f"[skip] WorldPop: found {find_worldpop().name}")
        return
    download("https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/"
             "2020/BSGM/BGD/bgd_ppp_2020_UNadj_constrained.tif",
             DATA / "bgd_ppp_2020_UNadj_constrained.tif", "WorldPop 2020")


section("WorldPop", worldpop)

# --------------------------------------------- 5. GHSL built-up surface
# GHS-BUILT-S R2023A, 3 arc-second. Cell value = m2 of building footprint.
# The Dhaka tile is R7_C28. Each epoch is cropped to VIEW; zips are kept.
GHSL_DIR.mkdir(exist_ok=True)
BASE = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A"


def ghsl_name(year, r=7, c=28):
    return f"GHS_BUILT_S_E{year}_GLOBE_R2023A_4326_3ss_V1_0_R{r}_C{c}"


def ghsl_tif(z):
    """GDAL path to the .tif inside a zip (works with spaces in paths)."""
    inner = next(n for n in zipfile.ZipFile(z).namelist() if n.lower().endswith(".tif"))
    return f"/vsizip/{z.as_posix()}/{inner}"


def crop_epoch(year):
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    out = GHSL_DIR / f"built_s_{year}.tif"
    if out.exists():
        print(f"[skip] GHSL {year}: already cropped")
        return
    z = GHSL_DIR / f"{ghsl_name(year)}.zip"
    url = f"{BASE}/GHS_BUILT_S_E{year}_GLOBE_R2023A_4326_3ss/V1-0/tiles/{z.name}"
    if not download(url, z, f"GHSL {year}"):
        return
    with rasterio.open(ghsl_tif(z)) as src:
        win = from_bounds(*VIEW, transform=src.transform).round_offsets().round_lengths()
        a = src.read(1, window=win)
        nod = src.nodata if src.nodata is not None else 65535
        a = np.where(a == nod, 0, a).astype("uint16")
        prof = src.profile
        prof.update(driver="GTiff", height=a.shape[0], width=a.shape[1],
                    transform=src.window_transform(win), compress="deflate", nodata=None)
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(a, 1)
    print(f"[ ok ] GHSL {year} cropped to {a.shape[1]} x {a.shape[0]} cells")


for y in EPOCHS:
    section(f"GHSL {y}", lambda y=y: crop_epoch(y))

print("\nDone. Next: run 00_check_setup.py, then 02_rooftop_solar.py")
