# -*- coding: utf-8 -*-
"""Dimensioned drawing of the board from the actual .kicad_pcb: outline,
mounting holes, dimensions, every footprint with its designator and the legend.
The drawing labels are Croatian, because the drawing goes into the Croatian
documentation. Run it with KiCad's python:

    python.exe generate_drawing.py <board.kicad_pcb> <out.svg>

POSITIONS. A footprint is drawn on the centre of its courtyard, never on
fp.GetPosition(). That anchor is wherever the footprint author put the origin,
usually pin 1, and it is NOT the middle of the part. Until 25.08.2026. the
drawing centred every part on the anchor, which put 73 of the 107 footprints
more than 1 mm off: J5 by 8,9 mm, ENC1 by 7,25 mm and every through-hole
resistor by exactly 5,08 mm, half its lead pitch. The board looked shuffled.
Check any change against hardware/kicad/render-top.png, which is the same board.

TYPOGRAPHY. The sizes follow the same role scale as the figures of the written
documentation: the same 16:13:12 ratio, the same weights
and the same colour per role. What this drawing does NOT share is the 12 pt
printed floor. It is a scale drawing, and a designator is tied to the size of
the part it names: at 12 pt the label for D1 would be wider than D1 itself. So
FS_REF stays small and figure 12 prints below 12 pt, a deliberate exception
recorded in docs/MAPA-POVEZANIH-DATOTEKA.md.

Known and knowingly left alone: the legend names D2 "TVS P6KE16A" while the
board carries an SMAJ16A.
"""
import sys, os
import pcbnew

BOARD = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "obd2-simulator.kicad_pcb")
# The drawing belongs to the written documentation, its labels are Croatian and
# it lives outside this repository, next to the rest of that material.
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..",
    "Pisani dio", "Slike za rad", "crtezi-ploce", "tehnicki-crtez-pcb-v07.svg")

# ---------------------------------------------------------------- canvas ----
CW, CH = 1289, 838           # locked: matches the .docx frame, 16,00 x 10,40 cm

FS_TITLE = 23                # drawing title
FS_H2 = 19                   # legend headings
FS_BODY = 18                 # legend text, dimensions, notes
FS_REF = 10                  # designator, bound to the size of its footprint

INK = "#111111"
GRAY = "#3f4750"
GOLD = "#8a6508"
RED = "#a03030"

# Board box and legend column. They do not overlap, which they did until
# 25.08.2026., when the legend text ran straight across the board.
BX0, BY0, BX1, BY1 = 95, 132, 782, 748
LEGEND_X = 815
LEGEND_R = CW - 26

# Highlighted parts: the OBD connector and the rotary control mounted directly
# on the board, the rotated stick, the turned-around USB-A and the corrected TVS.
HOT = {"J2", "ENC1", "SW6", "J4", "D2"}

board = pcbnew.LoadBoard(BOARD)
bb = board.GetBoardEdgesBoundingBox()
bx0 = pcbnew.ToMM(bb.GetX())
by1 = pcbnew.ToMM(bb.GetY() + bb.GetHeight())
W_MM = round(pcbnew.ToMM(bb.GetWidth()))
H_MM = round(pcbnew.ToMM(bb.GetHeight()))

S = min((BX1 - BX0) / W_MM, (BY1 - BY0) / H_MM)
OX = BX0
OY = BY0 + H_MM * S          # board y = 0 sits on the bottom edge


def px(x, y):
    return (OX + x * S, OY - y * S)


def tw(s, fs, bold=False):
    """Rough Arial advance width, enough to decide whether a label fits."""
    em = 0.0
    for c in s:
        if c.isupper() or c in "ŽŠĐČĆΩ":
            em += 0.72
        elif c.isdigit():
            em += 0.56
        elif c in ".,:;()[]-/ ":
            em += 0.30
        else:
            em += 0.53
    return em * fs * (1.07 if bold else 1.0)


def extent(fp):
    """Centre and size of a footprint, in board millimetres.

    The courtyard is what the eye reads as the part, so it wins. A few
    footprints have none, and those fall back to the pad/graphic bounding box.
    Either way the CENTRE comes from the box, never from the anchor.
    """
    r = None
    try:
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy and cy.OutlineCount():
            r = cy.BBox()
    except Exception:
        r = None
    if r is None or r.GetWidth() == 0:
        r = fp.GetBoundingBox(False, False)
    c = r.GetCenter()
    return (pcbnew.ToMM(c.x) - bx0, by1 - pcbnew.ToMM(c.y),
            min(pcbnew.ToMM(r.GetWidth()), 30.0),
            min(pcbnew.ToMM(r.GetHeight()), 30.0))


HOLES = []
parts = []
for fp in board.GetFootprints():
    ref = fp.GetReference()
    if ref.startswith("H"):
        p = fp.GetPosition()
        HOLES.append((pcbnew.ToMM(p.x) - bx0, by1 - pcbnew.ToMM(p.y)))
        continue
    x, y, w, h = extent(fp)
    parts.append((ref, x, y, w, h))

UI_AXIS = 0.0
for fp in board.GetFootprints():
    if fp.GetReference() == "SW1":
        c = fp.GetCourtyard(pcbnew.F_CrtYd).BBox().GetCenter()
        UI_AXIS = pcbnew.ToMM(c.x) - bx0
        break

KEEPOUT = None
for z in board.Zones():
    if z.GetIsRuleArea():
        b = z.GetBoundingBox()
        KEEPOUT = (pcbnew.ToMM(b.GetX()) - bx0,
                   by1 - pcbnew.ToMM(b.GetY() + b.GetHeight()),
                   pcbnew.ToMM(b.GetWidth()), pcbnew.ToMM(b.GetHeight()))
        break

o = []
A = o.append
A('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
  'font-family="Arial, Helvetica, sans-serif">' % (CW, CH, CW, CH))
A('<defs><marker id="da" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">'
  '<path d="M0,1 L9,4 L0,7 z" fill="#222"/></marker>'
  '<marker id="db" markerWidth="10" markerHeight="8" refX="1" refY="4" orient="auto">'
  '<path d="M9,1 L0,4 L9,7 z" fill="#222"/></marker>'
  '<pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
  'patternTransform="rotate(45)">'
  '<line x1="0" y1="0" x2="0" y2="6" stroke="#b06060" stroke-width="1"/></pattern></defs>')
A('<rect width="%d" height="%d" fill="#ffffff"/>' % (CW, CH))
A('<rect x="18" y="18" width="%d" height="%d" fill="none" stroke="#222" stroke-width="2"/>'
  % (CW - 36, CH - 36))
A('<rect x="26" y="26" width="%d" height="%d" fill="none" stroke="#222" stroke-width="0.8"/>'
  % (CW - 52, CH - 52))

# board outline
A('<rect x="%.0f" y="%.0f" width="%.0f" height="%.0f" fill="none" stroke="#111" '
  'stroke-width="2.6"/>' % (OX, OY - H_MM * S, W_MM * S, H_MM * S))

# otisci
for ref, x, y, w, h in parts:
    cx, cy = px(x, y)
    ww, hh = max(w * S, 7), max(h * S, 7)
    hot = ref in HOT
    A('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" stroke="%s" '
      'stroke-width="%s"/>'
      % (cx - ww / 2, cy - hh / 2, ww, hh,
         "#fdf0d5" if hot else "#f4f6f8", "#b8860b" if hot else "#889",
         "1.6" if hot else "0.9"))

# Designators, every one of them: inside the part where it fits, otherwise just
# above it, which is what the silkscreen does on the real board.
for ref, x, y, w, h in parts:
    cx, cy = px(x, y)
    ww, hh = max(w * S, 7), max(h * S, 7)
    hot = ref in HOT
    if tw(ref, FS_REF) + 3 <= ww and FS_REF + 2 <= hh:
        ty = cy + FS_REF * 0.35
    else:
        ty = cy - hh / 2 - 2.5
    A('<text x="%.1f" y="%.1f" font-size="%d" text-anchor="middle" fill="%s">%s</text>'
      % (cx, ty, FS_REF, GOLD if hot else "#333", ref))

# antenska zona bez bakra
if KEEPOUT:
    kx0, ky0, kw, kh = KEEPOUT
    kx, ky = px(kx0, ky0 + kh)
    A('<rect x="%.0f" y="%.0f" width="%.0f" height="%.0f" fill="url(#hatch)" '
      'stroke="#b04040" stroke-width="1.4" stroke-dasharray="6,4"/>'
      % (kx, ky, kw * S, kh * S))
    A('<text x="%.0f" y="%.0f" font-size="%d" fill="%s" text-anchor="middle">'
      'zona bez bakra (antena)</text>'
      % (kx + kw * S / 2, ky - 5, FS_REF, RED))

# mounting holes
for hx, hy in HOLES:
    cx, cy = px(hx, hy)
    A('<circle cx="%.0f" cy="%.0f" r="8" fill="#fff" stroke="#111" stroke-width="1.6"/>'
      % (cx, cy))
    A('<g stroke="#555" stroke-width="0.8" stroke-dasharray="12,4,3,4">'
      '<line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f"/>'
      '<line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f"/></g>'
      % (cx - 15, cy, cx + 15, cy, cx, cy - 15, cx, cy + 15))
if HOLES:
    hx, hy = px(W_MM * 0.5, 0)
    A('<text x="%.0f" y="%.0f" font-size="%d" fill="#111" text-anchor="middle">'
      '%d &#215; &#8960;3,2 (M3), u kutovima</text>'
      % (hx, hy + 26, FS_BODY, len(HOLES)))


# kote
def dim_h(x1, x2, y, txt):
    px1, py = px(x1, y)
    px2, _ = px(x2, y)
    o.append('<line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f" stroke="#222" '
             'stroke-width="1" marker-start="url(#db)" marker-end="url(#da)"/>'
             % (px1, py, px2, py))
    o.append('<text x="%.0f" y="%.0f" font-size="%d" text-anchor="middle" '
             'fill="#111">%s</text>' % ((px1 + px2) / 2, py - 7, FS_BODY, txt))


def dim_v(y1, y2, x, txt):
    px1, py1 = px(x, y1)
    _, py2 = px(x, y2)
    o.append('<line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f" stroke="#222" '
             'stroke-width="1" marker-start="url(#db)" marker-end="url(#da)"/>'
             % (px1, py1, px1, py2))
    o.append('<text x="%.0f" y="%.0f" font-size="%d" text-anchor="middle" fill="#111" '
             'transform="rotate(-90 %.0f %.0f)">%s</text>'
             % (px1 - 9, (py1 + py2) / 2, FS_BODY, px1 - 9, (py1 + py2) / 2, txt))


dim_h(0, W_MM, -12.0, "%d mm" % W_MM)
dim_v(0, H_MM, -8.0, "%d mm" % H_MM)

# ---------------------------------------------------------------- legenda ----
# THE LABELS BELOW STAY IN CROATIAN ON PURPOSE: this drawing is a figure of the
# Croatian written documentation. Everything else in this file is English.
LX = LEGEND_X
ly = 132
LH = round(FS_BODY * 1.42)


def head(t, fill="#111"):
    global ly
    A('<text x="%d" y="%d" font-size="%d" font-weight="bold" fill="%s">%s</text>'
      % (LX, ly, FS_H2, fill, t))
    ly += round(FS_H2 * 1.55)


def item(t, fill=GRAY):
    global ly
    if tw(t, FS_BODY) > LEGEND_R - LX:
        raise RuntimeError("legend line too wide (%.0f > %d): %r"
                           % (tw(t, FS_BODY), LEGEND_R - LX, t))
    A('<text x="%d" y="%d" font-size="%d" fill="%s">%s</text>'
      % (LX, ly, FS_BODY, fill, t))
    ly += LH


A('<text x="%d" y="96" font-size="%d" font-weight="bold" fill="#111">'
  'Tehnički crtež tiskane pločice</text>' % (LX, FS_TITLE))
item("OBD-II simulator, revizija v0.7")
ly += 10
item("Dvoslojni FR4, %d &#215; %d mm, 1,6 mm" % (W_MM, H_MM))
item("%d montažna otvora M3 (&#8960;3,2 mm)" % len(HOLES))
item("Gornji rub: J1 (USB-C) i J2 (OBD-II)")
item("Donji rub: J4 (USB-A), desni rub: sučelje")
ly += 14
head("Obilježja revizije v0.7", GOLD)
item("J2: SEP-A-OBD-D2 izravno na pločici", GOLD)
item("ENC1: EN11 enkoder, 20 impulsa/okretu", GOLD)
item("SW6: palica zarotirana za 45°", GOLD)
item("J4: USB-A okrenut otvorom prema van", GOLD)
item("D2: ispravljen polaritet TVS diode", GOLD)
item("Svi pasivi THT, otpornici vodoravno", GOLD)
ly += 14
head("Sučelje u jednoj osi (x = %.0f mm)" % UI_AXIS)
item("SW3, SW2, SW1, SW6 i ENC1 okomito")
ly += 14
item("Ukupno otisaka: %d (%d dijela + %d otvora)"
     % (len(parts) + len(HOLES), len(parts), len(HOLES)))

if ly > CH - 30:
    raise RuntimeError("legend overruns the frame: %d > %d" % (ly, CH - 30))

A('</svg>')
open(OUT, "w", encoding="utf-8").write("\n".join(o))
print("drawing: %s | parts: %d | scale %.2f px/mm | legend ends at %d/%d"
      % (OUT, len(parts), S, ly, CH))
