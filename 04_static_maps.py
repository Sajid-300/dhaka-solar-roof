"""
Step 4: publication maps (same look as the video).

    output/maps/01_thana_potential.png   where the roof power is (thana choropleth + ranking)
    output/maps/02_roof_by_roof.png      building-level close-up + "big roofs first" curve
    output/maps/03_people_vs_roofs.png   bivariate map: crowding vs rooftop solar
    output/maps/Dhaka_Solar_Roof_maps.pdf  all boards in one PDF (backup submission)

Run after 02_rooftop_solar.py. Each board is 2880 x 1620 px (16:9).
"""
import textwrap

import geopandas as gpd
import mapclassify
import matplotlib
import numpy as np
import pandas as pd
from shapely.geometry import box

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patheffects as pe
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

import common as C

C.use_style()
DPI = 150
FOCUS_THANA = None   # None = the thana with the largest average roof; or e.g. "Tejgaon Ind. Area"
MAPS = C.OUT / "maps"
MAPS.mkdir(parents=True, exist_ok=True)
STROKE = [pe.withStroke(linewidth=3.2, foreground=C.BG)]

if not C.RESULTS.exists():
    raise SystemExit("Run 02_rooftop_solar.py first.")
t = gpd.read_file(C.RESULTS, layer="thanas_solar").to_crs(C.UTM)
city = t.dissolve()
try:
    context = gpd.read_file(C.THANAS, layer="context_upazilas").to_crs(C.UTM)
except Exception:
    context = None
water = None
if C.WATER.exists():
    try:
        water = gpd.read_parquet(C.WATER).to_crs(C.UTM)
    except Exception:
        water = None
HAS_POP = "pop_per_km2" in t.columns


# ------------------------------------------------------------- helpers
def board(kicker, title, subtitle):
    fig = plt.figure(figsize=(19.2, 10.8), dpi=DPI)
    fig.text(0.04, 0.935, kicker.upper(), fontsize=14, color=C.MUTED)
    fig.text(0.04, 0.875, title, fontsize=38, weight="bold", color=C.INK)
    fig.text(0.04, 0.838, subtitle, fontsize=19, style="italic", color=C.MUTED)
    return fig


def footer(fig, *keys, note=""):
    fig.text(0.04, 0.03, C.credit(*keys) + (f"   |   {note}" if note else ""),
             fontsize=11.5, color=C.MUTED)


def base(ax, bounds, pad=1500):
    """Context upazilas, water and a soft city fill inside the given bounds."""
    x0, y0, x1, y1 = bounds
    frame = box(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    ax.set_facecolor(C.BG)
    ax.set_axis_off()
    if context is not None:
        ctx = context.clip(frame)
        if len(ctx):
            ctx.plot(ax=ax, color="#0F1638", edgecolor=C.GRID, linewidth=0.7, zorder=0)
    if water is not None:
        w = water.clip(frame)
        poly = w[w.geom_type.isin(["Polygon", "MultiPolygon"])]
        line = w[w.geom_type.isin(["LineString", "MultiLineString"])]
        if len(poly):
            poly.plot(ax=ax, color=C.WATER_FILL, linewidth=0, zorder=1)
        if len(line):
            line.plot(ax=ax, color=C.WATER_FILL, linewidth=1.2, zorder=1)
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_aspect("equal")


def north_scale(ax, km=5):
    ax.annotate("N", xy=(0.95, 0.965), xycoords="axes fraction", ha="center", fontsize=17,
                weight="bold", color=C.INK, zorder=9)
    ax.annotate("", xy=(0.95, 0.955), xytext=(0.95, 0.89), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=C.INK, lw=1.6), zorder=9)
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    sx, sy = x0 + 0.05 * (x1 - x0), y0 + 0.04 * (y1 - y0)
    ax.plot([sx, sx + km * 1000], [sy, sy], color=C.INK, lw=3, solid_capstyle="butt", zorder=9)
    ax.text(sx + km * 500, sy + 0.012 * (y1 - y0), f"{km:g} km", ha="center", fontsize=13,
            color=C.INK, zorder=9, path_effects=STROKE)


def label(ax, geom, text, size=13, color=None, weight="normal"):
    p = geom.representative_point()
    ax.text(p.x, p.y, text, ha="center", va="center", fontsize=size, color=color or C.INK,
            weight=weight, zorder=8, path_effects=STROKE)


def label_some(ax, rows, name_col="thana", n=6, min_gap=2200, size=12.5):
    """Label up to n features, skipping any closer than min_gap metres to one already placed."""
    placed = []
    for _, r in rows.iterrows():
        p = r.geometry.representative_point()
        if any(p.distance(q) < min_gap for q in placed):
            continue
        label(ax, r.geometry, short(r[name_col]), size=size)
        placed.append(p)
        if len(placed) >= n:
            break


def fmt(v):
    return f"{v:,.0f}" if v >= 10 else f"{v:,.1f}"


def short(name):
    return {"Tejgaon Ind. Area": "Tejgaon Ind.", "Sher-e-bangla Nagar": "Sher-e-Bangla"}.get(name, name)


boards = []

# ============================================================ 1. thana potential
fig = board("Rooftop solar potential by thana",
            "Where Dhaka's Roof Power Is",
            "Solar capacity that existing roofs could hold, per square kilometre of land")
ax = fig.add_axes([0.02, 0.08, 0.50, 0.74])
base(ax, city.total_bounds)
jenks = mapclassify.FisherJenks(t["mw_per_km2"].values, k=5)
t["cls"] = jenks.yb
t.plot(ax=ax, color=[C.SOLAR_CLASSES[i] for i in t["cls"]], edgecolor=C.BG, linewidth=0.9, zorder=3)
city.boundary.plot(ax=ax, color=C.CYAN, linewidth=1.6, zorder=4)
label_some(ax, t.sort_values("mw_per_km2", ascending=False), n=6)
north_scale(ax)

# legend
lo = [t["mw_per_km2"].min()] + list(jenks.bins[:-1])
lx, ly = 0.53, 0.70
fig.text(lx, ly + 0.045, "MW per km²", fontsize=15, color=C.MUTED)
for i, (a, b_) in enumerate(zip(lo, jenks.bins)):
    y = ly - i * 0.045
    fig.patches.append(Rectangle((lx, y), 0.022, 0.032, transform=fig.transFigure,
                                 color=C.SOLAR_CLASSES[i]))
    fig.text(lx + 0.03, y + 0.016, f"{a:,.1f} to {b_:,.1f}", fontsize=14, va="center", color=C.INK)

# headline numbers
tot_mw, tot_gwh = t["capacity_mw"].sum(), t["gen_gwh_yr"].sum()
fig.text(lx, 0.38, f"{tot_mw / 1000:,.1f} GW", fontsize=46, weight="bold", color=C.AMBER)
fig.text(lx, 0.345, f"citywide potential (range {t['capacity_mw_low'].sum() / 1000:,.1f} "
         f"to {t['capacity_mw_high'].sum() / 1000:,.1f} GW)", fontsize=14, color=C.MUTED)
fig.text(lx, 0.25, f"{tot_gwh / 1000:,.1f} TWh", fontsize=46, weight="bold", color=C.CYAN)
fig.text(lx, 0.215, "of electricity a year", fontsize=14, color=C.MUTED)

# ranking chart
axb = fig.add_axes([0.77, 0.10, 0.20, 0.70], facecolor=C.BG)
top = t.nlargest(12, "gen_gwh_yr").iloc[::-1]
axb.barh([short(n) for n in top["thana"]], top["gen_gwh_yr"],
         color=[C.SOLAR_CLASSES[i] for i in top["cls"]], height=0.72)
for i, v in enumerate(top["gen_gwh_yr"]):
    axb.text(v, i, f"  {v:,.0f}", va="center", fontsize=12.5, color=C.INK)
axb.set_title("Top 12 thanas, GWh per year", fontsize=15, color=C.MUTED, loc="left", pad=12)
for s in axb.spines.values():
    s.set_visible(False)
axb.tick_params(axis="y", labelsize=13.5, colors=C.INK, length=0)
axb.tick_params(axis="x", labelsize=11, length=0)
axb.set_xlim(0, top["gen_gwh_yr"].max() * 1.25)
axb.grid(axis="x", color=C.GRID, lw=0.7)
axb.set_axisbelow(True)
footer(fig, "overture", "gsa", "bounds",
       note=f"Central case: {C.USABLE_FRACTION:.0%} of roof usable, {C.KWP_PER_M2} kWp per m²")
fig.savefig(MAPS / "01_thana_potential.png", dpi=DPI)
boards.append(fig)
print("Saved 01_thana_potential.png")

# ============================================================ 2. roof by roof
print("Reading buildings (this can take a minute) ...")
bld = gpd.read_file(C.RESULTS, layer="buildings_solar", columns=["thana", "roof_m2", "kwp"])
bld = bld.to_crs(C.UTM)

# citywide "big roofs first" curve
k = np.sort(bld["kwp"].values)[::-1]
cum = np.cumsum(k) / k.sum() * 100
share_b = np.arange(1, len(k) + 1) / len(k) * 100
top10 = float(np.interp(10, share_b, cum))

focus = FOCUS_THANA
if focus is None:
    big = t[t["buildings"] >= 300]
    focus = big.loc[big["mean_roof_m2"].idxmax(), "thana"]
fz = t[t["thana"] == focus]
fb = fz.total_bounds
frame = box(fb[0] - 400, fb[1] - 400, fb[2] + 400, fb[3] + 400)
near = bld[bld.intersects(frame)]
inside = near[near["thana"] == focus]
print(f"Focus thana: {focus} ({len(inside):,} buildings)")

fig = board(f"Building by building  |  {focus}",
            "Big Roofs First",
            f"Every footprint in {focus}, coloured by the solar capacity its roof could hold")
ax = fig.add_axes([0.02, 0.07, 0.56, 0.75])
base(ax, frame.bounds, pad=0)
near[near["thana"] != focus].plot(ax=ax, color="#2A3366", linewidth=0, zorder=2)
breaks = [0, 5, 20, 50, 150, np.inf]
cls = np.digitize(inside["kwp"], breaks[1:-1])
inside.plot(ax=ax, color=[C.SOLAR_CLASSES[i] for i in cls], linewidth=0, zorder=3)
fz.boundary.plot(ax=ax, color=C.CYAN, linewidth=1.8, zorder=4)
north_scale(ax, km=0.5)

lx = 0.60
fig.text(lx, 0.775, "kWp per roof", fontsize=15, color=C.MUTED)
names = ["under 5", "5 to 20", "20 to 50", "50 to 150", "150 or more"]
for i, nm in enumerate(names):
    y = 0.73 - i * 0.04
    fig.patches.append(Rectangle((lx, y), 0.02, 0.028, transform=fig.transFigure,
                                 color=C.SOLAR_CLASSES[i]))
    fig.text(lx + 0.027, y + 0.014, nm, fontsize=14, va="center", color=C.INK)
fr = t[t["thana"] == focus].iloc[0]
fig.text(lx + 0.15, 0.73, f"{fr['capacity_mw']:,.0f} MW", fontsize=40, weight="bold", color=C.AMBER)
fig.text(lx + 0.15, 0.70, f"on {int(fr['buildings']):,} roofs in {focus}", fontsize=14, color=C.MUTED)
fig.text(lx + 0.15, 0.62, f"{inside['kwp'].max():,.0f} kWp", fontsize=40, weight="bold", color=C.CYAN)
fig.text(lx + 0.15, 0.59, "on its single largest roof", fontsize=14, color=C.MUTED)

# inset: where the focus thana is
axi = fig.add_axes([0.475, 0.085, 0.095, 0.20], facecolor=C.BG)
city.plot(ax=axi, color=C.PANEL, edgecolor=C.MUTED, linewidth=0.5)
fz.plot(ax=axi, color=C.AMBER)
axi.set_xticks([])
axi.set_yticks([])
axi.set_xlabel("")
axi.set_ylabel("")
for sp in axi.spines.values():
    sp.set_color(C.GRID)
axi.set_aspect("equal")

# curve
axc = fig.add_axes([0.63, 0.12, 0.33, 0.34], facecolor=C.PANEL)
axc.plot(share_b, cum, color=C.AMBER, lw=3)
axc.plot([0, 100], [0, 100], color=C.MUTED, lw=1, ls=(0, (4, 4)))
axc.scatter([10], [top10], s=70, color=C.AMBER, zorder=5)
axc.annotate(f"The largest 10% of roofs\nhold {top10:.0f}% of the potential",
             xy=(10, top10), xytext=(40, 10), fontsize=14, color=C.INK,
             arrowprops=dict(arrowstyle="-", color=C.MUTED, lw=1))
axc.set_xlim(0, 100)
axc.set_ylim(0, 102)
axc.set_xlabel("Share of Dhaka's buildings, largest roofs first (%)", fontsize=13)
axc.set_ylabel("Share of citywide potential (%)", fontsize=13)
axc.tick_params(labelsize=12, length=0)
axc.grid(color=C.GRID, lw=0.7)
for s in axc.spines.values():
    s.set_visible(False)
footer(fig, "overture", "gsa", "bounds")
fig.savefig(MAPS / "02_roof_by_roof.png", dpi=DPI)
boards.append(fig)
print("Saved 02_roof_by_roof.png")

# ============================================================ 3. bivariate
if HAS_POP:
    fig = board("People and roofs",
                "Who Has Sun to Share?",
                "Thanas compared on crowding (people per km²) and rooftop solar (MW per km²)")
    ax = fig.add_axes([0.02, 0.07, 0.50, 0.75])
    base(ax, city.total_bounds)
    px = pd.qcut(t["pop_per_km2"].rank(method="first"), 3, labels=False).astype(int)
    sy = pd.qcut(t["mw_per_km2"].rank(method="first"), 3, labels=False).astype(int)
    t["bi_x"], t["bi_y"] = px.values, sy.values
    t.plot(ax=ax, color=[C.BIVAR[y][x] for x, y in zip(t["bi_x"], t["bi_y"])],
           edgecolor=C.BG, linewidth=0.9, zorder=3)
    city.boundary.plot(ax=ax, color=C.INK, linewidth=1.2, zorder=4)
    north_scale(ax)

    # 3 x 3 legend
    lg = fig.add_axes([0.545, 0.47, 0.13, 0.23])
    for x in range(3):
        for y in range(3):
            lg.add_patch(Rectangle((x, y), 0.96, 0.96, color=C.BIVAR[y][x]))
    lg.set_xlim(-0.05, 3)
    lg.set_ylim(-0.05, 3)
    lg.set_aspect("equal")
    lg.set_axis_off()
    fig.text(0.545, 0.445, "More people  →", fontsize=14, color=C.MUTED)
    fig.text(0.532, 0.47, "More roof solar  →", fontsize=14, color=C.MUTED, rotation=90,
             va="bottom")

    groups = [
        ((2, 2), "Dense and roof-rich",
         "Plenty of people and plenty of roof: start community solar here."),
        ((0, 2), "Roof-rich, fewer residents",
         "More roof than residents need: surplus power could go to the grid."),
        ((2, 0), "Crowded and roof-poor",
         "Little roof per person: needs shared or off-site solar."),
    ]
    y = 0.74
    for (bx, by), head, body in groups:
        members = t[(t["bi_x"] == bx) & (t["bi_y"] == by)]["thana"].map(short).tolist()
        fig.patches.append(Rectangle((0.71, y - 0.004), 0.016, 0.03, transform=fig.transFigure,
                                     color=C.BIVAR[by][bx]))
        fig.text(0.733, y + 0.011, head, fontsize=19, weight="bold", color=C.INK, va="center")
        fig.text(0.71, y - 0.032, body, fontsize=14, color=C.MUTED)
        shown = members[:8] + ([f"and {len(members) - 8} more"] if len(members) > 8 else [])
        fig.text(0.71, y - 0.058, textwrap.fill(", ".join(shown) or "none", 62), fontsize=14,
                 style="italic", color=C.AMBER, va="top", linespacing=1.3)
        y -= 0.19
    footer(fig, "overture", "gsa", "worldpop", "bounds",
           note="Classes are thirds (terciles) of the 41 thanas")
    fig.savefig(MAPS / "03_people_vs_roofs.png", dpi=DPI)
    boards.append(fig)
    print("Saved 03_people_vs_roofs.png")
else:
    print("Skipped the bivariate map: WorldPop not found")

with PdfPages(MAPS / "Dhaka_Solar_Roof_maps.pdf") as pdf:
    for f in boards:
        pdf.savefig(f)
print(f"Saved Dhaka_Solar_Roof_maps.pdf ({len(boards)} pages) in {MAPS}")
