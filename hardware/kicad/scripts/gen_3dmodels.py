# gen_3dmodels.py - generator of custom VRML models for the board render.
#
# WHY: two parts on the board have no model in KiCad's library, so in the render
# they appeared either as a bare grey box or not at all:
#   J2   - MINITOOLS SEP-A-OBD-D2, the female OBD-II (J1962) connector. The old
#          hand-written model was three boxes stacked on top of each other, which
#          looks nothing like a connector.
#   ENC1 - BI Technologies EN11-HSB1AQ20, an 11 mm incremental encoder with a
#          push-button. The STOCK KiCad Alps EC11E footprint is used, and in
#          KiCad 10 that footprint has NO 3D model attached, so the encoder was
#          missing from the render entirely.
#
# The script writes two .wrl files into kicad/3dmodels/. The models are
# simplified (no threads, no fillets) but have the correct outline, height and
# contact layout, which is what shows up in a render.
#
# COORDINATES. KiCad's VRML reader expects a unit of 0.1 inch = 2.54 mm, so every
# dimension is divided by 2.54 at the end. The Y axis in VRML points opposite to
# KiCad's Y axis, so every footprint y coordinate is passed with the sign flipped
# (the `pt` function). The origin is the footprint origin, and z = 0 is the top
# surface of the board.
#
# Running it (any Python 3, pcbnew not required):
#   python scripts/gen_3dmodels.py

import math
import os

MM = 1.0 / 2.54  # mm -> VRML unit (0.1 inch)

OUT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "3dmodels"))


# ── Materials ────────────────────────────────────────────────────────────────
# (diffuse, specular, shininess). The names describe the real material.
MAT = {
    "black_plastic":  ((0.085, 0.085, 0.095), (0.055, 0.055, 0.060), 0.20),
    "grey_plastic":  ((0.560, 0.560, 0.575), (0.120, 0.120, 0.125), 0.22),
    "dark_hole":     ((0.030, 0.030, 0.035), (0.020, 0.020, 0.020), 0.05),
    "brass":           ((0.760, 0.640, 0.330), (0.500, 0.440, 0.240), 0.60),
    "nickel":          ((0.640, 0.650, 0.665), (0.400, 0.400, 0.420), 0.50),
    "nickel_dark":    ((0.520, 0.530, 0.545), (0.320, 0.320, 0.340), 0.42),
    "tin":        ((0.680, 0.685, 0.700), (0.350, 0.350, 0.360), 0.40),
}


# ── Geometry helpers (everything in millimetres, footprint coordinates) ──────

def pt(x, y, z):
    """Footprint point (mm, KiCad y) -> VRML point (unit 0.1 inch)."""
    return (x * MM, -y * MM, z * MM)


def poly_area(poly):
    a = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def ccw(poly):
    """A polygon in KiCad coordinates, always wound so that after mirroring the
    Y axis the normal points toward +Z (i.e. upward in the render)."""
    return poly if poly_area(poly) < 0 else list(reversed(poly))


def chamfer(poly, c):
    """Chamfered corners: every corner is replaced by a pair of points c away
    along both adjacent sides. It keeps the connector trapezoid from looking
    like a sharp wedge."""
    out = []
    n = len(poly)
    for i in range(n):
        px, py = poly[(i - 1) % n]
        cx, cy = poly[i]
        nx, ny = poly[(i + 1) % n]
        # redoslijed je bitan: prvo tocka prema prethodnom vrhu, pa prema
        # sljedecem, cime obilazak poligona ostaje neprekinut
        for (ax, ay) in ((px, py), (nx, ny)):
            dx, dy = ax - cx, ay - cy
            d = math.hypot(dx, dy)
            k = min(c, d * 0.45) / d
            out.append((cx + dx * k, cy + dy * k))
    return out


def offset_poly(poly, d):
    """Konveksan poligon uvucen za d prema unutra (mitrirani offset).
    Racuna se presjek pomaknutih pravaca susjednih stranica."""
    n = len(poly)
    area = poly_area(poly)
    # kod obilaska u smjeru suprotnom kazaljci unutrasnjost je lijevo od
    # stranice, kod obilaska u smjeru kazaljke desno - odatle predznak normale
    sgn = 1.0 if area > 0 else -1.0
    lines = []
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        ln = math.hypot(ex, ey)
        if ln < 1e-9:
            continue
        nx, ny = sgn * (-ey / ln), sgn * (ex / ln)
        lines.append((nx, ny, nx * (x0 + nx * d) + ny * (y0 + ny * d)))
    out = []
    m = len(lines)
    for i in range(m):
        a1, b1, c1 = lines[i - 1]
        a2, b2, c2 = lines[i]
        det = a1 * b2 - a2 * b1
        if abs(det) < 1e-9:
            continue
        out.append(((c1 * b2 - c2 * b1) / det, (a1 * c2 - a2 * c1) / det))
    return out


def circle_poly(cx, cy, r, n=24, start=0.0):
    return [(cx + r * math.cos(start + 2 * math.pi * i / n),
             cy + r * math.sin(start + 2 * math.pi * i / n)) for i in range(n)]


def d_shaft_poly(cx, cy, r, flat, n=28):
    """Presjek osovine s ravnim rezom (D profil) na udaljenosti `flat` od osi."""
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        if x - cx > flat:
            x = cx + flat
        pts.append((x, y))
    # ukloni duplikate nastale rezanjem
    out = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    return out


def rrect_poly(cx, cy, w, h, r, seg=5):
    """Pravokutnik zaobljenih uglova, kao poligon."""
    pts = []
    hw, hh = w / 2.0 - r, h / 2.0 - r
    for (sx, sy, a0) in ((1, 1, 0.0), (-1, 1, math.pi / 2),
                         (-1, -1, math.pi), (1, -1, 1.5 * math.pi)):
        ox, oy = cx + sx * hw, cy + sy * hh
        for i in range(seg + 1):
            a = a0 + (math.pi / 2) * i / seg
            pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
    return pts


# ── Assembling the VRML shapes ───────────────────────────────────────────────

class Model:
    def __init__(self, header):
        self.header = header
        self.parts = []

    def shape(self, mat, points, faces):
        self.parts.append((mat, points, faces))

    # ---- osnovni volumeni ----

    def prism(self, mat, poly, z0, z1):
        """Puno tijelo: plast, dno i vrh."""
        poly = ccw(poly)
        n = len(poly)
        pts = [pt(x, y, z0) for (x, y) in poly] + [pt(x, y, z1) for (x, y) in poly]
        faces = []
        for i in range(n):
            j = (i + 1) % n
            faces.append([i, j, j + n, i + n])
        faces.append(list(range(n, 2 * n)))                 # top
        faces.append(list(reversed(range(n))))              # bottom
        self.shape(mat, pts, faces)

    def ring(self, mat, outer, inner, z0, z1):
        """Suplji plast: vanjski i unutarnji zid + prsten na vrhu i na dnu.
        Time se dobiva prava udubina konektora, a ne kutija na kutiji."""
        outer, inner = ccw(outer), ccw(inner)
        n = len(outer)
        assert len(inner) == n
        po = [pt(x, y, z0) for (x, y) in outer]
        pu = [pt(x, y, z1) for (x, y) in outer]
        io = [pt(x, y, z0) for (x, y) in inner]
        iu = [pt(x, y, z1) for (x, y) in inner]
        pts = po + pu + io + iu
        O0, O1, I0, I1 = 0, n, 2 * n, 3 * n
        faces = []
        for i in range(n):
            j = (i + 1) % n
            faces.append([O0 + i, O0 + j, O1 + j, O1 + i])          # vani
            faces.append([I1 + i, I1 + j, I0 + j, I0 + i])          # unutra
            faces.append([O1 + i, O1 + j, I1 + j, I1 + i])          # top
            faces.append([I0 + i, I0 + j, O0 + j, O0 + i])          # bottom
        self.shape(mat, pts, faces)

    def disc(self, mat, poly, z):
        """A flat face pointing upward. The winding has to match that of a
        prism's top face - with the reverse winding the normal points down and
        the face is invisible from above in the render (that is how the
        connector holes disappeared the first time)."""
        poly = ccw(poly)
        pts = [pt(x, y, z) for (x, y) in poly]
        self.shape(mat, pts, [list(range(len(poly)))])

    def cyl(self, mat, cx, cy, r, z0, z1, n=24):
        self.prism(mat, circle_poly(cx, cy, r, n), z0, z1)

    def box(self, mat, cx, cy, w, h, z0, z1):
        self.prism(mat, [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
                         (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)],
                   z0, z1)

    # ---- output ----

    def write(self, path):
        out = ["#VRML V2.0 utf8", self.header.rstrip(), ""]
        # The structure deliberately matches the hand-written models that work:
        # Transform > children > Shape. KiCad's VRML reader does not accept the
        # material of a bare top-level `Shape`, so the part comes out in the
        # default grey.
        for (mat, points, faces) in self.parts:
            dif, spec, shin = MAT[mat]
            out.append("Transform {")
            out.append("  children [")
            out.append("    Shape {")
            out.append("      appearance Appearance {")
            out.append("        material Material { diffuseColor %.3f %.3f %.3f "
                       "specularColor %.3f %.3f %.3f shininess %.2f }"
                       % (dif + spec + (shin,)))
            out.append("      }")
            out.append("      geometry IndexedFaceSet {")
            out.append("        creaseAngle 1.05")
            out.append("        coord Coordinate { point [")
            out.append(",\n".join("          %.4f %.4f %.4f" % p for p in points))
            out.append("        ] }")
            out.append("        coordIndex [")
            out.append(",\n".join(
                "          " + ", ".join(str(i) for i in f) + ", -1"
                for f in faces))
            out.append("        ]")
            out.append("      }")
            out.append("    }")
            out.append("  ]")
            out.append("}")
            out.append("")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out))
        print("%-28s %2d shapes, %s"
              % (os.path.basename(path), len(self.parts), path))


# ── J2: MINITOOLS SEP-A-OBD-D2, the female OBD-II connector ──────────────────
#
# The shape follows a photograph of the part: a black trapezoidal housing (the
# D shape from the J1962 standard), a shallow flange at the bottom, and inside
# the recess a light grey insert carrying 16 female contacts in two rows of 8.
# The trapezoid is wider on the side of pins 1-8.
#
# Dimensions: an overall 43.3 x 20.7 mm and a height of 17.7 mm, from the
# footprint description. The trapezoid narrows from the wider side (y = -10.35,
# half-width 21.65) toward the narrower one (y = +10.35, half-width 18.80). The
# contact layout is taken literally from the footprint: 4.0 mm pitch, x from -14
# to +14, rows at y = -4.3 (pins 1-8) and y = +4.3 (pins 9-16).
#
# SIMPLIFICATIONS: no threads in the brass screw inserts (in the footprint those
# are two non-plated holes at +-16 mm, a mechanical joint with the board) and no
# edge fillets other than the chamfered corners of the trapezoid.

def build_obd2():
    H_TOTAL = 17.7      # visina konektora iznad ploce
    Z_FLANGE = 3.4      # solid bottom of the housing, the recess starts above it
    WALL = 2.2          # debljina stijenke trapeznog plasta
    GAP = 1.0           # zracnost izmedu stijenke i umetka
    Z_INSERT = 13.6     # gornja ploha umetka (4,1 mm ispod ruba)

    trap = ccw(chamfer([(-18.80, 10.35), (18.80, 10.35),
                        (21.65, -10.35), (-21.65, -10.35)], 1.6))
    cavity = offset_poly(trap, WALL)
    insert = offset_poly(trap, WALL + GAP)

    m = Model("""# MINITOOLS SEP-A-OBD-D2 (TME A-OBD-D), female OBD-II J1962 connector,
# montaza licem prema gore. Generirano skriptom scripts/gen_3dmodels.py.
# Trapezoidal housing 43.3 x 20.7 mm, height 17.7 mm, with a grey insert in the
# recess carrying 16 contacts (2 rows of 8, 4.0 mm pitch, 8.6 mm between rows).
# VRML jedinica u KiCadu je 0,1 inca = 2,54 mm, os Y suprotna KiCadovoj.""")

    # housing: solid bottom + trapezoidal shell with a recess
    m.prism("black_plastic", trap, 0.0, Z_FLANGE)
    m.ring("black_plastic", trap, cavity, Z_FLANGE, H_TOTAL)

    # grey insert with the contacts, recessed
    m.prism("grey_plastic", insert, Z_FLANGE, Z_INSERT)

    # 16 contacts: a dark hole with a brass contact inside it. The holes are
    # shallow discs just above the insert - a VRML polygon cannot have a real
    # hole, and this way the render still shows the 2 x 8 layout of the real
    # part.
    for row_y, cols in ((-4.3, range(8)), (4.3, range(8, 16))):
        for k in cols:
            x = -14.0 + 4.0 * (k % 8)
            m.disc("dark_hole", circle_poly(x, row_y, 0.95, 16), Z_INSERT + 0.02)
            m.disc("brass", circle_poly(x, row_y, 0.48, 12), Z_INSERT + 0.04)

    m.write(os.path.join(OUT_DIR, "SEP-A-OBD-D2.wrl"))


# ── ENC1: BI Technologies EN11-HSB1AQ20, 11 mm incremental encoder ───────────
#
# The footprint is the stock KiCad RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm:
# body x = 1.5..13.5 and y = -3.3..8.3 (12.0 x 11.6 mm), shaft axis at the body
# centre (7.5, 2.5). Terminals A/C/B are at x = 0 (y = 0 / 2.5 / 5.0), the
# push-button contacts S1/S2 at x = 14.5 (y = 5.0 / 0), and the two mounting tabs
# MP at (7.5, -3.1) and (7.5, 8.1).
#
# Construction of the part: a black plastic base, a nickel-plated sheet-metal
# cover over it, an M7 threaded bushing emerging from the cover and, out of that,
# a 6 mm shaft with a flat (D profile). The H20mm designation means 20 mm of
# shaft above the mounting surface.
#
# SIMPLIFICATIONS: no thread on the bushing, no slot for the washer and nut, and
# the flat on the shaft runs its whole length (on the real part only the top
# 15 mm).

def build_encoder():
    CX, CY = 7.5, 2.5   # shaft axis = body centre
    BW, BH = 12.0, 11.6
    Z_BASE = 1.4        # plastic base
    Z_CASE = 6.5        # mounting surface (top of the sheet-metal cover)
    Z_BUSH = 11.5       # top of the M7 bushing
    Z_SHAFT = Z_CASE + 20.0

    m = Model("""# BI Technologies EN11-HSB1AQ20, 11 mm incremental encoder with a push-button.
# Generated by scripts/gen_3dmodels.py. The footprint is the stock KiCad
# RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm, which has no 3D model attached
# in KiCad 10. Body 12.0 x 11.6 mm, shaft axis at (7.5, 2.5) mm from the
# footprint origin, 6 mm shaft with a flat, 20 mm above the mounting surface.
# The VRML unit in KiCad is 0.1 inch = 2.54 mm, the Y axis opposite to KiCad's.""")

    # base and sheet-metal cover
    m.prism("black_plastic", rrect_poly(CX, CY, BW, BH, 0.8), 0.0, Z_BASE)
    m.prism("nickel", rrect_poly(CX, CY, BW, BH, 1.2), Z_BASE, Z_CASE)
    # udubljeni pojas pri vrhu pokrova, da se limena kapa razlikuje od postolja
    m.prism("nickel_dark", rrect_poly(CX, CY, BW - 0.7, BH - 0.7, 1.0),
            Z_CASE - 0.6, Z_CASE + 0.15)

    # mounting tabs: bent sheet metal at the front and rear edge, into the board
    for y in (-3.3 - 0.25, 8.3 + 0.25):
        m.box("nickel_dark", CX, y, 3.6, 0.5, -1.6, 3.2)

    # M7 bushing and the 6 mm shaft with a flat
    m.cyl("nickel", CX, CY, 3.85, Z_CASE + 0.15, Z_CASE + 0.75, 24)
    m.cyl("nickel", CX, CY, 3.50, Z_CASE + 0.75, Z_BUSH, 24)
    m.prism("nickel_dark", d_shaft_poly(CX, CY, 3.0, 2.4), Z_BUSH, Z_SHAFT)

    # terminals: A/C/B on the left, S1/S2 on the right. A horizontal arm from the
    # body to the hole, then a vertical one through the board.
    for (px, py) in ((0.0, 0.0), (0.0, 2.5), (0.0, 5.0),
                     (14.5, 5.0), (14.5, 0.0)):
        edge = 1.5 if px < CX else 13.5
        x0, x1 = min(px, edge), max(px, edge)
        m.prism("tin", [(x0, py - 0.4), (x1, py - 0.4),
                            (x1, py + 0.4), (x0, py + 0.4)], 0.85, 1.25)
        m.box("tin", px, py, 0.8, 0.8, -1.6, 1.25)

    m.write(os.path.join(OUT_DIR, "EN11-HSB1AQ20.wrl"))


if __name__ == "__main__":
    build_obd2()
    build_encoder()
