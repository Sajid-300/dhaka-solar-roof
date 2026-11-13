"""
Step 3: "Dhaka's Growing Solar Roof" time-lapse, 1975 to 2030.

Sequence (about 24 s at 30 fps):
    title card (fade in) > crossfade to map > 1975 to 2020 observed growth >
    pause on 2020 > 2020 to 2030 GHSL projection > crossfade to summary card

GHSL has one map every 5 years. Between epochs each cell follows a monotone
cubic curve (PCHIP), so growth never overshoots or reverses. The clock eases
in and out at the start and end of each segment.

Outputs (output/timelapse/):
    dhaka_solar_roof.mp4    1920 x 1080 video for the StoryMap
    dhaka_solar_roof.gif    lighter 800 x 450 version (optional)
    swipe_1975.png ...      map-only stills for a StoryMap Swipe block
    epoch_stats.csv         the numbers behind the video
"""
import geopandas as gpd
import imageio.v2 as imageio
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from rasterio.features import geometry_mask
from scipy.interpolate import PchipInterpolator
from shapely.geometry import box

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patheffects as pe

import common as C

C.use_style()

# ------------------------------------------------------------- settings
FPS = 30
SEC = dict(title_in=0.8, title_hold=2.2, to_map=1.0, observed=9.0, hold_2020=1.4,
           projected=3.2, hold_end=0.8, to_outro=1.2, outro=4.5)
MAKE_GIF = True
SWIPE_YEARS = [1975, 1990, 2005, 2020, 2030]
SUBTITLE = "Fifty-five years of urban growth, read as a solar resource"
TAGLINE = "Dhaka's next power plant may already be built. It is on the roofs."

OUTDIR = C.OUT / "timelapse"
OUTDIR.mkdir(parents=True, exist_ok=True)
STROKE = [pe.withStroke(linewidth=3, foreground=C.BG)]
CREDIT_KEYS = ("ghsl", "gsa", "bounds")

# ------------------------------------------------------------- data
layers = []
for y in C.EPOCHS:
    f = C.GHSL_DIR / f"built_s_{y}.tif"
    if not f.exists():
        raise SystemExit(f"Missing {f.name}. Run 01_download_data.py first.")
    with rasterio.open(f) as src:
        layers.append(src.read(1).astype("float32"))
        transform, crs, bounds = src.transform, src.crs, src.bounds
stack = np.clip(np.stack(layers), 0, None)       # (epochs, rows, cols), m2 of roof
_, H, W = stack.shape
EXT = (bounds.left, bounds.right, bounds.bottom, bounds.top)

thanas = gpd.read_file(C.THANAS, layer="thanas").to_crs(crs)
city = thanas.dissolve()
inside = ~geometry_mask(city.geometry, (H, W), transform)


def optional_layer(layer):
    try:
        return gpd.read_file(C.THANAS, layer=layer).to_crs(crs)
    except Exception:
        return None


context = optional_layer("context_upazilas")
places = optional_layer("places")
water = None
if C.WATER.exists():
    try:
        water = gpd.read_parquet(C.WATER).to_crs(crs).clip(C.VIEW)
    except Exception as e:
        print(f"Water layer skipped: {e}")
if water is not None:
    CREDIT_KEYS = ("ghsl", "gsa", "overture", "bounds")

# cell size changes with latitude on a geographic grid
lat = transform.f + (np.arange(H) + 0.5) * transform.e
cell_m2 = ((transform.a * 111_320 * np.cos(np.radians(lat))) *
           (abs(transform.e) * 111_320))[:, None] * np.ones((1, W))
cell_ha = cell_m2 / 1e4
VIEW_KM2 = cell_m2.sum() / 1e6
LAT0 = float(lat.mean())


def specific_yield():
    pv = C.find_pvout()
    if pv:
        with rasterio.open(pv) as s:
            w = s.window(*city.to_crs(s.crs).total_bounds)
            v = s.read(1, window=w, masked=True).astype(float)
        y = float(v.mean())
        return (y * 365 if y < 20 else y), "Global Solar Atlas"
    if C.NASA_CSV.exists():
        g = pd.read_csv(C.NASA_CSV)["ghi_ann_kwh_m2_day"].mean()
        return g * 365 * C.PERFORMANCE_RATIO, "NASA POWER"
    print("WARNING: no solar data found, using a placeholder yield")
    return 1300.0, "placeholder"


YIELD, YIELD_SRC = specific_yield()
print(f"Specific yield {YIELD:.0f} kWh/kWp/yr ({YIELD_SRC})")

curve = PchipInterpolator(C.EPOCHS, stack, axis=0)  # monotone between epochs


def roof_at(t):
    return np.clip(curve(np.clip(t, C.EPOCHS[0], C.EPOCHS[-1])), 0, None)


def gw(m2, frac=C.USABLE_FRACTION):
    return m2 * frac * C.KWP_PER_M2 / 1e6        # kWp -> GW


def twh(g):
    return g * YIELD / 1000                      # GW x kWh/kWp -> TWh


def totals(a):
    return a.sum() / 1e6, a[inside].sum() / 1e6  # km2: whole map, city


def density(a):
    d = a * C.USABLE_FRACTION * C.KWP_PER_M2 / cell_ha   # kWp per hectare
    return np.ma.masked_less(d, 2.0)


# numbers per epoch (saved for the StoryMap text)
rows = []
for y, a in zip(C.EPOCHS, stack):
    area_all, area_city = totals(a)
    rows.append(dict(year=y, projected=y > C.LAST_OBSERVED,
                     roof_km2_map=area_all, roof_km2_city=area_city,
                     gw_map=gw(area_all * 1e6), gw_city=gw(area_city * 1e6),
                     gw_map_low=gw(area_all * 1e6, C.USABLE_LOW),
                     gw_map_high=gw(area_all * 1e6, C.USABLE_HIGH),
                     twh_map=twh(gw(area_all * 1e6)), twh_city=twh(gw(area_city * 1e6))))
ep = pd.DataFrame(rows)
ep.round(3).to_csv(OUTDIR / "epoch_stats.csv", index=False)
print(ep[["year", "roof_km2_map", "roof_km2_city", "gw_map", "gw_city"]].round(1).to_string(index=False))

# smooth curves for the chart
T = np.linspace(C.EPOCHS[0], C.EPOCHS[-1], 400)
full_map, full_city = np.array([totals(roof_at(t)) for t in T]).T
GW_MAP, GW_CITY = gw(full_map * 1e6), gw(full_city * 1e6)
VMAX = float(np.percentile(density(stack[-1]).compressed(), 99.5))
cmap = C.SOLAR.copy()
cmap.set_bad((0, 0, 0, 0))


# ------------------------------------------------------------- map drawing
def draw_map(ax, a, labels=True):
    """Base map + roof raster on an axes. Returns the image artist."""
    ax.set_facecolor(C.BG)
    ax.set_axis_off()
    if context is not None:
        inner = box(EXT[0] + 0.002, EXT[2] + 0.002, EXT[1] - 0.002, EXT[3] - 0.002)
        context.boundary.clip(inner).plot(ax=ax, color=C.GRID, linewidth=0.7, zorder=1)
    if water is not None and len(water):
        polys = water[water.geom_type.isin(["Polygon", "MultiPolygon"])]
        lines = water[water.geom_type.isin(["LineString", "MultiLineString"])]
        if len(polys):
            polys.plot(ax=ax, color=C.WATER_FILL, linewidth=0, zorder=1)
        if len(lines):
            lines.plot(ax=ax, color=C.WATER_FILL, linewidth=1.0, zorder=1)
    im = ax.imshow(density(a), cmap=cmap, vmin=0, vmax=VMAX, extent=EXT,
                   interpolation="bilinear", zorder=2)
    thanas.boundary.plot(ax=ax, color="white", linewidth=0.4, alpha=0.18, zorder=3)
    city.boundary.plot(ax=ax, color=C.CYAN, linewidth=1.6, zorder=4)
    if labels and places is not None:
        for _, p in places.iterrows():
            if p["kind"] == "city" and p["name"] not in ("Uttara", "Mirpur", "Gulshan", "Old Dhaka"):
                continue
            fringe = p["kind"] == "fringe"
            ax.text(p.geometry.x, p.geometry.y, p["name"].upper() if fringe else p["name"],
                    fontsize=13 if fringe else 13.5, color=C.MUTED if fringe else C.INK,
                    style="italic" if fringe else "normal", ha="center", va="center",
                    zorder=5, path_effects=STROKE)
    ax.set_xlim(EXT[0], EXT[1])
    ax.set_ylim(EXT[2], EXT[3])
    ax.set_aspect(1 / np.cos(np.radians(LAT0)))
    # north arrow and 5 km scale bar
    ax.annotate("N", xy=(0.94, 0.955), xycoords="axes fraction", ha="center",
                fontsize=17, weight="bold", color=C.INK, zorder=6)
    ax.annotate("", xy=(0.94, 0.945), xytext=(0.94, 0.885), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=C.INK, lw=1.6), zorder=6)
    km5 = 5 / (111.32 * np.cos(np.radians(LAT0)))
    x0 = EXT[0] + 0.04 * (EXT[1] - EXT[0])
    y0 = EXT[2] + 0.035 * (EXT[3] - EXT[2])
    ax.plot([x0, x0 + km5], [y0, y0], color=C.INK, lw=3, solid_capstyle="butt", zorder=6)
    ax.text(x0 + km5 / 2, y0 + 0.004, "5 km", ha="center", va="bottom", fontsize=13,
            color=C.INK, zorder=6, path_effects=STROKE)
    return im


def colorbar(fig, im, rect, size=12):
    cax = fig.add_axes(rect)
    cb = fig.colorbar(im, cax=cax, orientation="horizontal")
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=C.MUTED, labelsize=size, length=0)
    cb.set_label("Possible rooftop solar (kWp per hectare)", color=C.MUTED, fontsize=size + 1)
    return cb


# ------------------------------------------------------------- main frame
fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
ax_map = fig.add_axes([0.02, 0.10, 0.52, 0.86])
img = draw_map(ax_map, stack[0])
colorbar(fig, img, [0.07, 0.065, 0.26, 0.014])

X0 = 0.575
fig.text(X0, 0.895, "Dhaka's Growing Solar Roof", fontsize=40, weight="bold", color=C.INK)
fig.text(X0, 0.852, SUBTITLE, fontsize=20, style="italic", color=C.MUTED)
year_txt = fig.text(X0 - 0.004, 0.655, "", fontsize=124, weight="bold", color=C.AMBER)
phase_txt = fig.text(X0, 0.628, "", fontsize=16, style="italic", color=C.MUTED)

stat_labels = [("Roof area", "km²"), ("Solar capacity", "GW"), ("Clean power", "TWh per year")]
stat_vals = []
for i, (lab, unit) in enumerate(stat_labels):
    x = X0 + i * 0.135
    fig.text(x, 0.565, lab, fontsize=16, color=C.MUTED)
    stat_vals.append(fig.text(x, 0.515, "", fontsize=38, weight="bold", color=C.INK))
    fig.text(x, 0.492, unit, fontsize=14, color=C.MUTED)
city_txt = fig.text(X0, 0.445, "", fontsize=15, color=C.CYAN)

ax_ch = fig.add_axes([0.605, 0.135, 0.355, 0.265], facecolor=C.PANEL)
for s in ax_ch.spines.values():
    s.set_visible(False)
ax_ch.grid(color=C.GRID, lw=0.8)
ax_ch.set_xlim(C.EPOCHS[0], C.EPOCHS[-1])
ax_ch.set_ylim(0, GW_MAP.max() * 1.15)
ax_ch.axvspan(C.LAST_OBSERVED, C.EPOCHS[-1], color="white", alpha=0.05, lw=0)
ax_ch.text(C.LAST_OBSERVED + 0.6, GW_MAP.max() * 1.07, "Model estimate", fontsize=13,
           color=C.MUTED, style="italic", va="center")
ax_ch.plot(T, GW_MAP, color=C.AMBER, lw=1.5, alpha=0.18)
ax_ch.plot(T, GW_CITY, color=C.CYAN, lw=1.5, alpha=0.18)
ln_map, = ax_ch.plot([], [], color=C.AMBER, lw=3.2, label="Whole map area")
ln_city, = ax_ch.plot([], [], color=C.CYAN, lw=2.6, label="Dhaka city (41 thanas)")
dot_map, = ax_ch.plot([], [], "o", color=C.AMBER, ms=9)
dot_city, = ax_ch.plot([], [], "o", color=C.CYAN, ms=8)
ax_ch.set_ylabel("Solar capacity (GW)", fontsize=14)
ax_ch.tick_params(labelsize=13, length=0)
leg = ax_ch.legend(loc="upper left", frameon=False, fontsize=13, labelcolor=C.INK)

fig.text(X0, 0.062, C.credit(*CREDIT_KEYS), fontsize=12, color=C.MUTED)
fig.text(X0, 0.020,
         f"Central case: {C.USABLE_FRACTION:.0%} of roof usable, {C.KWP_PER_M2} kWp per m², "
         f"{YIELD:,.0f} kWh per kWp per year ({YIELD_SRC}).\n"
         "Years between the 5-yearly GHSL epochs are smoothed with a monotone curve.",
         fontsize=12, color=C.MUTED, linespacing=1.4)


def grab(f=fig):
    f.canvas.draw()
    return np.asarray(f.canvas.buffer_rgba())[..., :3].copy()


def render_map(t, phase):
    a = roof_at(t)
    img.set_data(density(a))
    area_all, area_city = totals(a)
    g_all, g_city = gw(area_all * 1e6), gw(area_city * 1e6)
    year_txt.set_text(f"{int(np.floor(t + 1e-6))}")
    on_epoch = abs(t - round(t)) < 1e-6 and int(round(t)) in C.EPOCHS
    phase_txt.set_text({"observed": "Observed by satellite (GHSL epoch)" if on_epoch
                        else "Smoothed between 5-year satellite observations",
                        "hold": "2020: the latest observed year",
                        "projected": "GHSL model estimate (made in 2023)"}[phase])
    stat_vals[0].set_text(f"{area_all:,.0f}")
    stat_vals[1].set_text(f"{g_all:,.1f}")
    stat_vals[2].set_text(f"{twh(g_all):,.1f}")
    city_txt.set_text(f"Inside Dhaka city: {area_city:,.0f} km² of roof, {g_city:,.1f} GW")
    k = T <= t + 1e-9
    ln_map.set_data(T[k], GW_MAP[k])
    ln_city.set_data(T[k], GW_CITY[k])
    dot_map.set_data([t], [g_all])
    dot_city.set_data([t], [g_city])
    return grab()


# ------------------------------------------------------------- cards
def card(kind):
    f = plt.figure(figsize=(19.2, 10.8), dpi=100)
    bg = f.add_axes([0.58, 0.0, 0.42, 1.0])
    bg.imshow(density(stack[-1] if kind == "outro" else stack[C.EPOCHS.index(2020)]),
              cmap=cmap, vmin=0, vmax=VMAX, extent=EXT, alpha=0.30, interpolation="bilinear")
    bg.set_xlim(EXT[0], EXT[1])
    bg.set_ylim(EXT[2], EXT[3])
    bg.set_aspect(1 / np.cos(np.radians(LAT0)))
    bg.set_axis_off()
    fade = np.zeros((1, 256, 4))
    fade[..., :3] = matplotlib.colors.to_rgb(C.BG)
    fade[..., 3] = np.linspace(1, 0, 256)
    fx = f.add_axes([0.58, 0.0, 0.12, 1.0])
    fx.imshow(fade, aspect="auto", extent=(0, 1, 0, 1))
    fx.set_axis_off()
    x = 0.07
    if kind == "title":
        f.text(x, 0.80, "MAP COMPETITION 2026   |   MAPPING BANGLADESH FOR A SUSTAINABLE FUTURE",
               fontsize=15, color=C.MUTED)
        f.text(x, 0.58, "Dhaka's Growing\nSolar Roof", fontsize=80, weight="bold",
               color=C.INK, linespacing=1.0, va="bottom")
        f.add_artist(plt.Line2D([x, x + 0.16], [0.545, 0.545], color=C.AMBER, lw=5,
                                transform=f.transFigure))
        f.text(x, 0.46, SUBTITLE, fontsize=28, style="italic", color=C.INK)
        f.text(x, 0.40, "Dhaka, Bangladesh   |   1975 to 2030", fontsize=20, color=C.AMBER)
        if C.AUTHOR:
            f.text(x, 0.12, C.AUTHOR, fontsize=18, color=C.MUTED)
    else:
        r75, r20, r30 = ep.set_index("year").loc[[1975, C.LAST_OBSERVED, 2030], "roof_km2_map"]
        row20 = ep.set_index("year").loc[C.LAST_OBSERVED]
        f.text(x, 0.84, "WHAT THE ROOFS OF GREATER DHAKA COULD GIVE", fontsize=16, color=C.MUTED)
        items = [
            (f"{r75:,.0f} → {r20:,.0f} km²",
             f"Roof area in the mapped area (city and fringe), 1975 to {C.LAST_OBSERVED}, {r20 / r75:.1f} times larger"),
            (f"{row20.gw_map:,.1f} GW",
             f"Solar capacity those roofs could hold (range {row20.gw_map_low:,.1f} "
             f"to {row20.gw_map_high:,.1f} GW); 41 city thanas alone: {row20.gw_city:,.1f} GW"),
            (f"{row20.twh_map:,.1f} TWh",
             "Clean electricity those panels could produce every year"),
        ]
        for i, (big, small) in enumerate(items):
            y = 0.67 - i * 0.17
            f.text(x, y, big, fontsize=58, weight="bold", color=[C.INK, C.AMBER, C.CYAN][i])
            f.text(x, y - 0.045, small, fontsize=19, color=C.MUTED)
        f.text(x, 0.12, TAGLINE, fontsize=24, style="italic", color=C.INK)
    f.text(x, 0.05, C.credit(*CREDIT_KEYS), fontsize=12, color=C.MUTED)
    out = grab(f)
    plt.close(f)
    return out


# ------------------------------------------------------------- timeline
def ease(u):
    u = np.clip(u, 0, 1)
    return u * u * u * (u * (6 * u - 15) + 10)     # smootherstep


def n(sec):
    return max(1, int(round(sec * FPS)))


def blend(a, b, w):
    return (a.astype(np.float32) * (1 - w) + b.astype(np.float32) * w).astype(np.uint8)


mp4 = OUTDIR / "dhaka_solar_roof.mp4"
gif_frames = []
count = 0


def put(vid, frame):
    global count
    vid.append_data(frame)
    if MAKE_GIF and count % 4 == 0:
        gif_frames.append(Image.fromarray(frame).resize((800, 450), Image.LANCZOS))
    count += 1


print("Rendering title and summary cards ...")
title, outro = card("title"), card("outro")
black = np.zeros_like(title)
black[:] = np.array(matplotlib.colors.to_rgb(C.BG)) * 255

print("Rendering map frames ...")
first = render_map(C.EPOCHS[0], "observed")
with imageio.get_writer(mp4, fps=FPS, codec="libx264", quality=9,
                        pixelformat="yuv420p", macro_block_size=8) as vid:
    for u in np.linspace(0, 1, n(SEC["title_in"])):
        put(vid, blend(black, title, ease(u)))
    for _ in range(n(SEC["title_hold"])):
        put(vid, title)
    for u in np.linspace(0, 1, n(SEC["to_map"])):
        put(vid, blend(title, first, ease(u)))
    for u in np.linspace(0, 1, n(SEC["observed"])):
        frame = render_map(C.EPOCHS[0] + (C.LAST_OBSERVED - C.EPOCHS[0]) * ease(u), "observed")
        put(vid, frame)
    frame = render_map(C.LAST_OBSERVED, "hold")
    for _ in range(n(SEC["hold_2020"])):
        put(vid, frame)
    for u in np.linspace(0, 1, n(SEC["projected"]))[1:]:
        frame = render_map(C.LAST_OBSERVED + (C.EPOCHS[-1] - C.LAST_OBSERVED) * ease(u), "projected")
        put(vid, frame)
    for _ in range(n(SEC["hold_end"])):
        put(vid, frame)
    for u in np.linspace(0, 1, n(SEC["to_outro"])):
        put(vid, blend(frame, outro, ease(u)))
    for _ in range(n(SEC["outro"])):
        put(vid, outro)
plt.close(fig)
print(f"Saved {mp4.name}: {count} frames, {count / FPS:.1f} s")

if MAKE_GIF:
    gif = OUTDIR / "dhaka_solar_roof.gif"
    gif_frames[0].save(gif, save_all=True, append_images=gif_frames[1:],
                       duration=int(1000 * 4 / FPS), loop=0, optimize=True)
    print(f"Saved {gif.name}: {gif.stat().st_size / 1e6:.1f} MB")

# ------------------------------------------------------------- swipe stills
for y in SWIPE_YEARS:
    f = plt.figure(figsize=(10, 11.6), dpi=160)
    ax = f.add_axes([0.02, 0.10, 0.96, 0.84])
    im = draw_map(ax, stack[C.EPOCHS.index(y)])
    colorbar(f, im, [0.20, 0.075, 0.60, 0.016], size=11)
    f.text(0.04, 0.955, f"{y}", fontsize=40, weight="bold", color=C.AMBER, va="center")
    f.text(0.20, 0.955, "GHSL model estimate (made in 2023)" if y > C.LAST_OBSERVED else "Observed rooftop area (GHSL)",
           fontsize=17, style="italic", color=C.MUTED, va="center")
    f.text(0.5, 0.012, C.credit(*CREDIT_KEYS), fontsize=9.5, color=C.MUTED, ha="center")
    f.savefig(OUTDIR / f"swipe_{y}.png", dpi=160)
    plt.close(f)
print(f"Saved swipe stills for {SWIPE_YEARS}")
