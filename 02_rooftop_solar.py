"""
Step 2: rooftop solar potential for every building and every thana.

Per building:
    usable roof (m2)    = footprint area x USABLE_FRACTION
    capacity (kWp)      = usable roof x KWP_PER_M2
    generation (kWh/yr) = capacity x PVOUT (Global Solar Atlas, kWh/kWp/yr)

Outputs (output/):
    rooftop_solar.gpkg  layers "thanas_solar" and "buildings_solar"
    thana_summary.csv   one row per thana, for charts and the StoryMap
    key_findings.txt    headline numbers for the "Key findings" section
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

import common as C

if not C.BUILDINGS.exists():
    raise SystemExit("Buildings missing. Run 01_download_data.py first.")

thanas = gpd.read_file(C.THANAS, layer="thanas").to_crs(C.UTM)

# ------------------------------------------------------------ buildings
print("Reading buildings ...")
b = gpd.read_parquet(C.BUILDINGS)
keep = [c for c in ["id", "height", "num_floors", "class", "sources", "geometry"] if c in b]
b = b[keep]
b = b[b.geom_type.isin(["Polygon", "MultiPolygon"])].to_crs(C.UTM)
print(f"  {len(b):,} footprints in the download box")

if "sources" in b:
    def first_source(s):
        try:
            return str(s[0]["dataset"])
        except Exception:
            return "unknown"
    b["source"] = b["sources"].apply(first_source)
    b = b.drop(columns="sources")

# each building belongs to the thana that contains its inner point
pts = gpd.GeoDataFrame(geometry=b.representative_point(), crs=C.UTM, index=b.index)
j = gpd.sjoin(pts, thanas[["thana", "geometry"]], predicate="within", how="inner")
j = j[~j.index.duplicated()]
b = b.loc[j.index].copy()
b["thana"] = j["thana"]
b["roof_m2"] = b.area
b = b[b["roof_m2"] >= C.MIN_ROOF_M2].copy()
print(f"  {len(b):,} buildings of {C.MIN_ROOF_M2} m2 or more inside the 41 thanas")

# ------------------------------------------------------------ solar yield
pv = C.find_pvout()
if pv:
    with rasterio.open(pv) as src:
        p = gpd.GeoSeries(b.representative_point(), crs=C.UTM).to_crs(src.crs)
        vals = np.array([v[0] for v in src.sample(zip(p.x, p.y))], dtype="float64")
        if src.nodata is not None:
            vals[np.isclose(vals, src.nodata)] = np.nan
    vals[(vals <= 1) | ~np.isfinite(vals)] = np.nan
    vals = np.where(np.isnan(vals), np.nanmedian(vals), vals)
    if np.nanmedian(vals) < 20:          # daily file given by mistake
        vals *= 365
    b["yield_kwh_kwp"] = vals
    yield_src = "Global Solar Atlas PVOUT"
elif C.NASA_CSV.exists():
    g = pd.read_csv(C.NASA_CSV)[["thana", "ghi_ann_kwh_m2_day"]]
    g["yield_kwh_kwp"] = g["ghi_ann_kwh_m2_day"] * 365 * C.PERFORMANCE_RATIO
    b = b.merge(g[["thana", "yield_kwh_kwp"]], on="thana", how="left").set_geometry("geometry")
    yield_src = "NASA POWER GHI"
else:
    raise SystemExit("No solar data. Put PVOUT.tif in data/gsa/ or run 01_download_data.py.")
print(f"Solar yield: {b['yield_kwh_kwp'].mean():,.0f} kWh/kWp/yr ({yield_src})")

b["usable_m2"] = b["roof_m2"] * C.USABLE_FRACTION
b["kwp"] = b["usable_m2"] * C.KWP_PER_M2
b["kwh_yr"] = b["kwp"] * b["yield_kwh_kwp"]

# roof size class, for the "big roofs first" finding
b["roof_rank_pct"] = b["roof_m2"].rank(pct=True, ascending=False) * 100

# ------------------------------------------------------------ per thana
agg = b.groupby("thana").agg(
    buildings=("roof_m2", "size"), roof_m2=("roof_m2", "sum"),
    mean_roof_m2=("roof_m2", "mean"), kwp=("kwp", "sum"), kwh_yr=("kwh_yr", "sum"),
).reset_index()
t = thanas.merge(agg, on="thana", how="left")
for c in ["buildings", "roof_m2", "kwp", "kwh_yr"]:
    t[c] = t[c].fillna(0)
t["area_km2"] = t.area / 1e6
t["capacity_mw"] = t["kwp"] / 1000
t["capacity_mw_low"] = t["capacity_mw"] * C.USABLE_LOW / C.USABLE_FRACTION
t["capacity_mw_high"] = t["capacity_mw"] * C.USABLE_HIGH / C.USABLE_FRACTION
t["gen_gwh_yr"] = t["kwh_yr"] / 1e6
t["mw_per_km2"] = t["capacity_mw"] / t["area_km2"]
t["roof_cover_pct"] = 100 * t["roof_m2"] / (t["area_km2"] * 1e6)

wp = C.find_worldpop()
if wp:
    from rasterstats import zonal_stats
    with rasterio.open(wp) as src:
        zs = zonal_stats(t.to_crs(src.crs), str(wp), stats=["sum"], nodata=src.nodata)
    t["population"] = [z["sum"] or 0 for z in zs]
    t["pop_per_km2"] = t["population"] / t["area_km2"]
    t["kwh_per_person"] = np.where(t["population"] > 0, t["kwh_yr"] / t["population"], np.nan)
    if C.RES_KWH_PER_PERSON:
        t["pct_res_demand"] = 100 * t["kwh_per_person"] / C.RES_KWH_PER_PERSON
else:
    print("WorldPop not found: per-person columns skipped")

if "source" in b:
    share = b.groupby(["thana", "source"]).size().unstack(fill_value=0)
    share = share.div(share.sum(axis=1), axis=0).mul(100).round(1)
    share.columns = ["pct_src_" + "".join(ch if ch.isalnum() else "_" for ch in c.lower())
                     for c in share.columns]
    t = t.merge(share, left_on="thana", right_index=True, how="left")

t = t.drop(columns=["kwp", "kwh_yr"]).sort_values("gen_gwh_yr", ascending=False)

# ------------------------------------------------------------ save
print("Saving ...")
t.to_crs(4326).to_file(C.RESULTS, layer="thanas_solar", driver="GPKG")
cols = [c for c in ["id", "thana", "source", "class", "height", "num_floors", "roof_m2",
                    "usable_m2", "kwp", "kwh_yr", "roof_rank_pct", "geometry"] if c in b]
b[cols].to_crs(4326).to_file(C.RESULTS, layer="buildings_solar", driver="GPKG")
t.drop(columns="geometry").round(3).to_csv(C.OUT / "thana_summary.csv", index=False)

# ------------------------------------------------------------ findings
mw, gwh = t["capacity_mw"].sum(), t["gen_gwh_yr"].sum()
top10 = b.loc[b["roof_rank_pct"] <= 10, "kwp"].sum() / b["kwp"].sum() * 100
lines = [
    f"Solar yield: {b['yield_kwh_kwp'].mean():,.0f} kWh per kWp per year ({yield_src})",
    f"Buildings analysed: {len(b):,} in 41 thanas ({t['area_km2'].sum():,.0f} km2)",
    f"Roof area: {t['roof_m2'].sum() / 1e6:,.1f} km2 "
    f"({100 * t['roof_m2'].sum() / (t['area_km2'].sum() * 1e6):.0f}% of the city's land)",
    f"Rooftop solar potential: {mw:,.0f} MW (range {t['capacity_mw_low'].sum():,.0f} "
    f"to {t['capacity_mw_high'].sum():,.0f} MW), {gwh:,.0f} GWh per year",
    f"The largest 10% of roofs hold {top10:.0f}% of the potential",
    "Top 5 thanas by generation: " + ", ".join(
        f"{r.thana} ({r.gen_gwh_yr:,.0f} GWh)" for r in t.head(5).itertuples()),
    "Top 5 thanas by MW per km2: " + ", ".join(
        f"{r.thana} ({r.mw_per_km2:,.1f})" for r in t.nlargest(5, "mw_per_km2").itertuples()),
]
if "population" in t:
    pop = t["population"].sum()
    lines.append(f"Population (WorldPop 2020): {pop:,.0f}; rooftop solar per person: "
                 f"{gwh * 1e6 / pop:,.0f} kWh per year")
    low = t[t["population"] > 0].nsmallest(5, "kwh_per_person")
    lines.append("Least solar per person: " + ", ".join(
        f"{r.thana} ({r.kwh_per_person:,.0f} kWh)" for r in low.itertuples()))
(C.OUT / "key_findings.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n" + "\n".join(lines))
print(f"\nSaved {C.RESULTS.name}, thana_summary.csv, key_findings.txt in {C.OUT}")
