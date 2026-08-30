# apply_3dmodels.py - attach 3D models to an ALREADY ROUTED board.
#
# WHY IT EXISTS: build_board.py builds the board from scratch and thereby deletes
# every track, so Freerouting has to be run again after it (route_board.ps1).
# When only the appearance of the 3D models changes, there is no reason to touch
# the routing - this script loads the saved .kicad_pcb, rewrites just the model
# fields and saves it back. Copper, zones and DRC stay untouched.
#
# Running it (KiCad's Python, because of the pcbnew module):
#   & "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin\python.exe" `
#       scripts\apply_3dmodels.py obd2-simulator.kicad_pcb

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pcbnew                       # noqa: E402
from models3d import apply_models   # noqa: E402

pcb = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                 "obd2-simulator.kicad_pcb"))

board = pcbnew.LoadBoard(pcb)
done = apply_models(board, pcbnew)
board.Save(pcb)
print("3D models assigned:", ", ".join(done))
print("board saved:", pcb)
