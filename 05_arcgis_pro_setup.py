r"""
Step 5: build the ArcGIS Pro map with the project palette.

Run this INSIDE ArcGIS Pro (it uses Pro's own arcpy, not the PyCharm venv):
    1. Open ArcGIS Pro and create or open a project.
    2. Analysis tab > Python > Python Window.
    3. Paste this line and press Enter twice:
       exec(open(r"<repo folder>\05_arcgis_pro_setup.py", encoding="utf-8").read())

What it does:
    adds a map "Dhaka Rooftop Solar" in UTM 46N on a navy background,
    loads the thana and building results from output/rooftop_solar.gpkg,
    colours them with the same five solar colours as the video and PNG maps,
    labels thanas in Times New Roman,
    saves a shareable map package: output/DhakaSolarRoof.mpkx
Every step is wrapped so a version difference in Pro cannot stop the rest.
"""
import os

import arcpy

FOLDER = r"D:\Documents\Map Contest"  # change to your copy of the repository
GPKG = os.path.join(FOLDER, "output", "rooftop_solar.gpkg")
MAP_NAME = "Dhaka Rooftop Solar"
SOLAR = [(58, 12, 163), (114, 9, 183), (247, 37, 133), (255, 109, 0), (255, 190, 11)]
NAVY = [10, 15, 44, 100]
CYAN = [76, 201, 240, 100]


def step(name, fn):
    try:
        out = fn()
        print(f"[ ok ] {name}")
        return out
    except Exception as e:
        print(f"[skip] {name}: {e}")
        return None


if not os.path.exists(GPKG):
    raise SystemExit(f"Not found: {GPKG}. Run 02_rooftop_solar.py in PyCharm first.")

aprx = arcpy.mp.ArcGISProject("CURRENT")


def get_map():
    found = aprx.listMaps(MAP_NAME)
    if found:
        return found[0]
    return aprx.createMap(MAP_NAME)


m = step("Create map", get_map) or aprx.activeMap
step("Projection UTM 46N",
     lambda: setattr(m, "spatialReference", arcpy.SpatialReference(32646)))


def navy_background():
    cim = m.getDefinition("V3")
    col = arcpy.cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
    col.values = NAVY
    cim.backgroundColor = col
    m.setDefinition(cim)


step("Navy background", navy_background)

# remove old copies so re-running does not stack duplicates
for old in m.listLayers():
    if old.name in ("thanas_solar", "buildings_solar", "main.thanas_solar", "main.buildings_solar"):
        step(f"Remove old {old.name}", lambda old=old: m.removeLayer(old))

buildings = step("Add buildings", lambda: m.addDataFromPath(GPKG + r"\main.buildings_solar"))
thanas = step("Add thanas", lambda: m.addDataFromPath(GPKG + r"\main.thanas_solar"))


def style_thanas():
    sym = thanas.symbology
    sym.updateRenderer("GraduatedColorsRenderer")
    sym.renderer.classificationField = "mw_per_km2"
    sym.renderer.classificationMethod = "NaturalBreaks"
    sym.renderer.breakCount = 5
    for i, brk in enumerate(sym.renderer.classBreaks):
        brk.symbol.color = {"RGB": list(SOLAR[i]) + [100]}
        brk.symbol.outlineColor = {"RGB": NAVY}
        brk.symbol.outlineWidth = 0.8
    thanas.symbology = sym
    thanas.name = "Rooftop solar, MW per km2"
    thanas.transparency = 0


def style_buildings():
    sym = buildings.symbology
    sym.updateRenderer("GraduatedColorsRenderer")
    sym.renderer.classificationField = "kwp"
    sym.renderer.breakCount = 5
    uppers = [5, 20, 50, 150]
    labels = ["under 5 kWp", "5 to 20 kWp", "20 to 50 kWp", "50 to 150 kWp", "150 kWp or more"]
    for i, brk in enumerate(sym.renderer.classBreaks):
        if i < len(uppers):
            brk.upperBound = uppers[i]
        brk.label = labels[i]
        brk.symbol.color = {"RGB": list(SOLAR[i]) + [100]}
        brk.symbol.outlineColor = {"RGB": [0, 0, 0, 0]}
        brk.symbol.outlineWidth = 0
    buildings.symbology = sym
    buildings.name = "Roof capacity per building"
    buildings.minThreshold = 60000   # draw buildings only when zoomed in past 1:60,000
    buildings.visible = True


def label_thanas():
    lc = thanas.listLabelClasses()[0]
    lc.expression = "$feature.thana"
    cim = thanas.getDefinition("V3")
    ts = cim.labelClasses[0].textSymbol.symbol
    ts.fontFamilyName = "Times New Roman"
    ts.fontStyleName = "Regular"
    ts.height = 9
    white = arcpy.cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
    white.values = [247, 244, 236, 100]
    ts.symbol.symbolLayers[0].color = white
    thanas.setDefinition(cim)
    thanas.showLabels = True


if thanas:
    step("Style thanas (5 solar colours, natural breaks)", style_thanas)
    step("Label thanas in Times New Roman", label_thanas)
if buildings:
    step("Style buildings (kWp classes)", style_buildings)

aprx.save()

# Shareable ArcGIS file: a map package with the data inside.
MPKX = os.path.join(FOLDER, "output", "DhakaSolarRoof.mpkx")


def package():
    arcpy.env.overwriteOutput = True
    if os.path.exists(MPKX):
        os.remove(MPKX)
    arcpy.management.PackageMap(
        in_map=m,
        output_file=MPKX,
        convert_data="CONVERT",  # copy the data into the package
        summary="Rooftop solar potential of Dhaka's 41 thanas (Map Competition 2026)",
        tags="Dhaka, rooftop solar, renewable energy, GHSL, Overture, Bangladesh")


step(f"Map package {os.path.basename(MPKX)}", package)
print(f"\nDone. Open the map '{MAP_NAME}' from the Catalog pane (Maps folder).")
print("Next: right-click 'Rooftop solar, MW per km2' > Zoom To Layer, then Share > Web Map.")
