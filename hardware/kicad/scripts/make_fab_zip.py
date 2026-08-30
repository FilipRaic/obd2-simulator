# -*- coding: utf-8 -*-
"""Pack the production files into a single .zip for the board fabricator.

    python make_fab_zip.py <gerber_dir> <output.zip>

WHY NOT THE WHOLE DIRECTORY. `kicad-cli pcb export gerbers` exports EVERY layer,
including the ones that are only drawing aids: Courtyard, Fab, Adhesive, Margin,
User_1 through User_4, Eco1, Eco2, Comments, Drawings. The fabricator does not
need them, and some readers pick them up as extra copper or as an outline, which
yields the wrong board. The package therefore contains exactly what is made.

Paste (F_Paste, B_Paste) is NOT in the package. It only serves to make a steel
stencil for applying solder paste, and this board is hand-soldered. If a stencil
is ordered after all, add those two layers.
"""
import os, sys, zipfile

GERBER_DIR = sys.argv[1]
OUT = sys.argv[2]

# Layer by layer, with an explanation of what each one carries.
LAYERS = [
    ("-F_Cu.gtl",         "copper, top layer"),
    ("-B_Cu.gbl",         "copper, bottom layer (ground pour)"),
    ("-F_Mask.gts",       "solder mask, top"),
    ("-B_Mask.gbs",       "solder mask, bottom"),
    ("-F_Silkscreen.gto", "silkscreen, top (reference designators)"),
    ("-B_Silkscreen.gbo", "silkscreen, bottom (board title)"),
    ("-Edge_Cuts.gm1",    "board outline, the board is cut along it"),
    (".drl",              "drilling, Excellon"),
    ("-job.gbrjob",       "Gerber job: layer list and stackup"),
]

base = None
for f in os.listdir(GERBER_DIR):
    if f.endswith("-Edge_Cuts.gm1"):
        base = f[:-len("-Edge_Cuts.gm1")]
if base is None:
    sys.exit("no -Edge_Cuts.gm1 file in %s" % GERBER_DIR)

missing = []
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for suffix, description in LAYERS:
        name = base + suffix
        path = os.path.join(GERBER_DIR, name)
        if not os.path.isfile(path):
            missing.append(name)
            continue
        z.write(path, name)
        print("  + %-40s %s" % (name, description))

if missing:
    print("MISSING:", ", ".join(missing))
    sys.exit(1)

size = os.path.getsize(OUT)
print("package: %s (%.0f kB, %d files)" % (OUT, size / 1024.0, len(LAYERS)))
