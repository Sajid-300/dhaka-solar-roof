"""
Shared settings for every script in this project:
paths, analysis assumptions, colour palette and fonts.

Change a value here once and every map, chart and video follows.
"""
from pathlib import Path

import matplotlib
from matplotlib.colors import LinearSegmentedColormap

# ------------------------------------------------------------------ paths
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

THANAS = DATA / "dhaka_thanas.gpkg"
BUILDINGS = DATA / "buildings_overture.parquet"
WATER = DATA / "water_overture.parquet"
GHSL_DIR = DATA / "ghsl"
NASA_CSV = DATA / "nasa_power_ghi_thanas.csv"
RESULTS = OUT / "rooftop_solar.gpkg"

UTM = 32646  # WGS 84 / UTM zone 46N (metres) for all area calculations
EPOCHS = list(range(1975, 2031, 5))
LAST_OBSERVED = 2020  # GHSL 2025 and 2030 are projections
VIEW = (90.25, 23.62, 90.60, 23.98)  # map window: W, S, E, N

# ------------------------------------------------------- assumptions
# Technical potential. Report the central case; quote LOW to HIGH as a range.
MIN_ROOF_M2 = 20          # ignore sheds, kiosks and footprint noise
USABLE_FRACTION = 0.5     # central: roof share free of tanks, stair rooms, shade
USABLE_LOW, USABLE_HIGH = 0.3, 0.6
KWP_PER_M2 = 0.15         # installed kWp per usable m2, incl. row spacing
PERFORMANCE_RATIO = 0.75  # only for the NASA POWER fallback
# Residential electricity use per person (kWh/yr). Leave None until you have
# a cited figure (BPDB / DESCO / DPDC annual report).
RES_KWH_PER_PERSON = None

AUTHOR = ""  # e.g. "Your Name, IUT"  (shown on the video title card)


# ------------------------------------------------------ input finders
def find_pvout():
    """Yearly PVOUT raster from the Global Solar Atlas (kWh/kWp/yr)."""
    hits = sorted((DATA / "gsa").glob("**/PVOUT.tif")) or \
        sorted((DATA / "gsa").glob("**/PVOUT*.tif"))
    return hits[0] if hits else None


def find_worldpop():
    for name in ("worldpop_bgd_2020.tif", "bgd_ppp_2020_UNadj_constrained.tif"):
        if (DATA / name).exists():
            return DATA / name
    hits = sorted(DATA.glob("bgd_ppp_2020*.tif"))
    return hits[0] if hits else None


# ------------------------------------------------------------ palette
# Navy background; indigo > magenta > amber ramp for solar values.
BG = "#0A0F2C"
PANEL = "#121A40"
GRID = "#26305C"
INK = "#F7F4EC"
MUTED = "#A3ACCB"
AMBER = "#FFBE0B"
MAGENTA = "#F72585"
CYAN = "#4CC9F0"
WATER_FILL = "#16306B"

SOLAR = LinearSegmentedColormap.from_list(
    "solar", ["#0A0F2C", "#3A0CA3", "#7209B7", "#F72585", "#FF6D00", "#FFBE0B", "#FFF4B8"])
SOLAR_CLASSES = ["#3A0CA3", "#7209B7", "#F72585", "#FF6D00", "#FFBE0B"]  # 5-class version

# 3 x 3 bivariate palette, index [row = solar class][col = population class]
# low solar row first. Cyan axis = people, magenta axis = solar.
BIVAR = [
    ["#E8E8E8", "#ACE4E4", "#5AC8C8"],
    ["#DFB0D6", "#A5ADD3", "#5698B9"],
    ["#BE64AC", "#8C62AA", "#3B4994"],
]


def use_style():
    """Times New Roman, with metric-compatible serif fonts as fallbacks."""
    matplotlib.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Liberation Serif", "Nimbus Roman",
                       "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "text.color": INK,
        "axes.labelcolor": MUTED,
        "axes.edgecolor": GRID,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "figure.facecolor": BG,
        "axes.facecolor": BG,
        "savefig.facecolor": BG,
        "pdf.fonttype": 42,  # keep text editable in the PDF
    })


SOURCES = {
    "ghsl": "GHSL R2023A (EC JRC)",
    "overture": "Overture Maps",
    "gsa": "Global Solar Atlas (World Bank, Solargis)",
    "worldpop": "WorldPop 2020",
    "bounds": "geoBoundaries",
}


def credit(*keys):
    """Data credit line for the sources a graphic actually uses."""
    keys = keys or tuple(SOURCES)
    return "Data: " + " | ".join(SOURCES[k] for k in keys)
