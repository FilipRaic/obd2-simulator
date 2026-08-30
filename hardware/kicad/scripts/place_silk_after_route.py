# -*- coding: utf-8 -*-
"""place_silk_after_route.py - reference designators after routing.

GOAL: every reference designator (R1, C3, U6 ...) stands NEXT TO its own part, on
any side, as close to it as possible, and all of them are horizontal. Proximity
is the only way to make it clear which part a designator refers to, because the
board is dense and neighbouring parts are only a few millimetres apart.

The search therefore goes by INCREASING DISTANCE rather than by a predefined
direction: the first free spot at the smallest distance is taken, whether it is
below, above or to the side. That way no designator wanders further than it must.

SILKSCREEN OVER A TRACK IS ALLOWED. That is not a defect: silkscreen is applied
over the solder mask, i.e. after the copper, so overlapping a track has no
consequence. An earlier version avoided it and thereby pushed designators
needlessly far from their part. Tracks only serve as a tie-breaker between two
EQUALLY DISTANT spots: if a spot without a track exists at the same distance, it
is taken.

WHAT IS NOT RELAXED:
  * a designator never goes over a PAD. The fabricator trims silkscreen over
    exposed copper and it can contaminate the solder joint;
  * a designator does not go over foreign silkscreen or over another designator.
    KiCad reports that as "Silkscreen clearance", and it is illegible anyway;
  * a designator does not run past the board outline.

A TRAP IN THE OBSTACLE MODEL: the body outline of a resistor is a single `Rect`.
Taking its bounding box would close off the whole interior of the body and push
designators needlessly further away. So `silk_shapes()` decomposes every drawing
into the segments of its outline, leaving the interior free.

At the end it is checked whether every designator is nearest to ITS OWN part,
because otherwise a reader could attribute a designator to a neighbour.

CAUTION: the designator placement in `obd2-simulator.kicad_pcb` was FURTHER
ADJUSTED BY HAND in KiCad after this script ran, and that state is authoritative.
Running this script again will overwrite those manual changes.

  Since 10.08.2026. this is no longer one isolated correction: the WHOLE
  placement was gone over by hand in KiCad, so most designators sit somewhere
  other than where this script would put them (J2 next to the OBD connector, U4
  and U6 beside their module bodies, R21 under its own resistor, and so on).
  Only the top silkscreen changed, copper and drilling stayed byte for byte the
  same. The board in git is the record of that placement: after a full rebuild,
  restore the `(property "Reference" ... (at ...))` entries from the last
  committed `.kicad_pcb` instead of accepting what the script produced.

  A second hand pass followed on 11.08.2026. and moved 59 designators. It was
  measured the same way: 107 footprints, 892 track segments, 73 vias and 64 nets
  before and after, copper and drill files identical once the date line in the
  Gerber header is ignored. All 107 designators are still horizontal, and the
  103 visible ones are still 0.9 mm (the four at 1.0 mm are the hidden mounting
  holes H1 to H4). With `min_silk_clearance` raised to 0.15 mm the board reports
  three warnings instead of the two it had before: the two long-standing J4
  outline clips, plus the reference field of U11 at 0.1463 mm from its own body
  outline. That last one is 3.7 um short of the rule and well inside silkscreen
  registration tolerance, so it was left alone.

  The older manual change, kept here because it explains a gap in the algorithm:
    * designator U6: local (0, -6.705) -> (2, 15.5), i.e. global
      (94.71, 94.00) -> (72.50, 96.00). Reason: the old position was UNDER THE
      MODULE BODY (the module covers x 75.25-100.75, y 85.0-103.0), so the
      designator was invisible on an assembled board. The new one is to the left
      of the module, beside the pad row 15-26. Verified: 1.19 mm from the nearest
      pad, 6.15 mm from the nearest other designator, inside the outline, outside
      the copper keep-out around the antenna, DRC 0 reports.

      THIS IS A GAP IN THE ALGORITHM, not just an isolated case: `silk_shapes()`
      decomposes drawings into outline segments and thereby deliberately leaves
      the INTERIOR of a body free. For a resistor that is right, because the body
      is thin and the designator next to it has to go somewhere. For a module of
      18 x 25.5 mm it is not, because the designator gets placed underneath it.
      If this script is ever developed further, bodies taller than a few
      millimetres should be treated as a solid obstacle.

The script REMAINS part of `route_board.ps1`, because a full regeneration builds
the board from scratch anyway and thereby erases everything done by hand, so it
is better for it to finish with this placement than with the one from
`build_board.py`, which does not know where the tracks are. Do not run it
separately over the board as it stands, unless the manual placement is being
discarded deliberately.

Running it (KiCad's Python, because of the pcbnew module):
  & "$k\\python.exe" scripts\\place_silk_after_route.py obd2-simulator.kicad_pcb
"""

import math
import os
import sys

import pcbnew

MM = pcbnew.ToMM

TXT_H = 0.9      # letter height (mm), same as in build_board.py
TXT_T = 0.15     # stroke thickness (mm)
TXT_H2 = 0.8     # reduced letters when the full size does not fit.
                 # NOT BELOW 0,8 mm: Board Setup sets the minimum silkscreen text
                 # height to 0,8 mm, so 0,63 mm (which build_board.py used) is
                 # reported by DRC as a warning.

PAD_M = 0.25     # designator clearance from a pad (mm)
EDGE_M = 0.5     # clearance from the board outline (mm)

# Distances from the part outline, smallest first. The first one at which a free
# spot is found is the one chosen.
DIST = (0.4, 0.6, 0.8, 1.0, 1.3, 1.6, 2.0, 2.5, 3.0, 3.6, 4.5, 5.5, 7.0, 9.0)


# ── geometry: everything in mm, KiCad's system (y grows downward) ────────────

def rect_of(bbox, margin=0.0):
    return (MM(bbox.GetLeft()) - margin, MM(bbox.GetTop()) - margin,
            MM(bbox.GetRight()) + margin, MM(bbox.GetBottom()) + margin)


def rects_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def seg_hits_rect(x1, y1, x2, y2, hw, r):
    """Does a segment of thickness 2*hw intersect rectangle r? The rectangle is
    inflated by hw, which reduces this to a segment / axis-aligned rectangle
    intersection."""
    ax, ay, bx, by = r[0] - hw, r[1] - hw, r[2] + hw, r[3] + hw
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - ax), (dx, bx - x1), (-dy, y1 - ay), (dy, by - y1)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                if t > t1:
                    return False
                if t > t0:
                    t0 = t
            else:
                if t < t0:
                    return False
                if t < t1:
                    t1 = t
    return True


def rect_dist(r, x, y):
    """Distance from a point to a rectangle, 0 if the point is inside it."""
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return math.hypot(dx, dy)


# ── loading and obstacles ───────────────────────────────────────────────────

pcb = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                 "obd2-simulator.kicad_pcb"))
board = pcbnew.LoadBoard(pcb)

edge = None
for d in board.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        r = rect_of(d.GetBoundingBox())
        edge = r if edge is None else (min(edge[0], r[0]), min(edge[1], r[1]),
                                       max(edge[2], r[2]), max(edge[3], r[3]))
BOARD = (edge[0] + EDGE_M, edge[1] + EDGE_M, edge[2] - EDGE_M, edge[3] - EDGE_M)

pads = []
for fp in board.GetFootprints():
    for pad in fp.Pads():
        pads.append(rect_of(pad.GetBoundingBox(), PAD_M))


def silk_shapes(g):
    """Silkscreen drawing -> (segments, rectangles). An outline is decomposed
    into its sides, so the interior of the body stays free."""
    hwd = MM(g.GetWidth()) / 2.0 + 0.1
    st = g.GetShape()
    pmm = lambda p: (MM(p.x), MM(p.y))
    segs_, rects_ = [], []

    def ring(pts):
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            segs_.append((a[0], a[1], b[0], b[1], hwd))

    if st == pcbnew.SHAPE_T_SEGMENT:
        a, b = pmm(g.GetStart()), pmm(g.GetEnd())
        segs_.append((a[0], a[1], b[0], b[1], hwd))
    elif st == pcbnew.SHAPE_T_RECT:
        ring([pmm(p) for p in g.GetRectCorners()])
    elif st == pcbnew.SHAPE_T_CIRCLE:
        cx, cy = pmm(g.GetCenter())
        rad = MM(g.GetRadius())
        if rad < 0.6:                        # pin 1 marker, a solid dot
            segs_.append((cx, cy, cx, cy, rad + 0.1))
        else:
            ring([(cx + rad * math.cos(2 * math.pi * i / 16),
                   cy + rad * math.sin(2 * math.pi * i / 16)) for i in range(16)])
    elif st == pcbnew.SHAPE_T_POLY:
        ps = g.GetPolyShape()
        for i in range(ps.OutlineCount()):
            oc = ps.Outline(i)
            ring([(MM(oc.CPoint(k).x), MM(oc.CPoint(k).y))
                  for k in range(oc.PointCount())])
    else:                                     # luk i ostalo, na ovoj ploci sitno
        rects_.append(rect_of(g.GetBoundingBox(), 0.1))
    return segs_, rects_


silk_segs, silk_rects = [], []
for fp in board.GetFootprints():
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_SilkS:
            a, b = silk_shapes(g)
            silk_segs += a
            silk_rects += b
for d in board.GetDrawings():
    if d.GetLayer() == pcbnew.F_SilkS:
        silk_rects.append(rect_of(d.GetBoundingBox(), 0.1))

# Top-layer tracks and vias are NOT obstacles, they only serve as a tie-breaker
# between two equally distant spots.
trk, vias = [], []
for t in board.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        p = t.GetStart()
        vias.append((MM(p.x), MM(p.y), MM(t.GetWidth(pcbnew.F_Cu)) / 2 + 0.1))
    elif t.GetLayer() == pcbnew.F_Cu:
        s, e = t.GetStart(), t.GetEnd()
        trk.append((MM(s.x), MM(s.y), MM(e.x), MM(e.y),
                    MM(t.GetWidth()) / 2 + 0.1))

placed_boxes = []


def free(r):
    if not (r[0] >= BOARD[0] and r[1] >= BOARD[1]
            and r[2] <= BOARD[2] and r[3] <= BOARD[3]):
        return False
    for h in pads:
        if rects_overlap(r, h):
            return False
    for h in silk_rects:
        if rects_overlap(r, h):
            return False
    for (x1, y1, x2, y2, hwd) in silk_segs:
        if seg_hits_rect(x1, y1, x2, y2, hwd, r):
            return False
    for b in placed_boxes:
        if rects_overlap(r, b):
            return False
    return True


def najblizi_je_svoj(tx, ty, ref):
    """Is the point (tx, ty) closer to its own part than to any other one?
    Without this, a designator can end up next to a neighbour and the reader
    cannot tell whose it is."""
    d_min, who = 1e9, None
    for (r2, rect) in bodies:
        dd = rect_dist(rect, tx, ty)
        if dd < d_min:
            d_min, who = dd, r2
    return who == ref


def clear_of_copper(r):
    for (x1, y1, x2, y2, hw) in trk:
        if seg_hits_rect(x1, y1, x2, y2, hw, r):
            return False
    for (cx, cy, rad) in vias:
        if rect_dist(r, cx, cy) < rad:
            return False
    return True


# ── repositioning ───────────────────────────────────────────────────────────

def courtyard_rect(fp):
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False, False)
    return rect_of(bb)


bodies = []          # (ref, part rectangle) for the unambiguity check
for fp in board.GetFootprints():
    if fp.Reference().IsVisible() and not fp.GetReference().startswith("H"):
        bodies.append((fp.GetReference(), courtyard_rect(fp)))

n_placed, n_no_room = 0, 0
clear_of_tracks = 0
distances = []

for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
    ref = fp.GetReference()
    rf = fp.Reference()
    if not rf.IsVisible() or ref.startswith("H"):
        continue

    rf.SetTextAngleDegrees(0)      # all horizontal
    rf.SetKeepUpright(False)

    br = courtyard_rect(fp)
    cx, cyy = (br[0] + br[2]) / 2.0, (br[1] + br[3]) / 2.0
    hw, hh = (br[2] - br[0]) / 2.0, (br[3] - br[1]) / 2.0

    def positions(d):
        """Eight directions around the part, at distance d from its outline."""
        dd = d * 0.7071
        return [(cx, cyy + hh + d), (cx, cyy - hh - d),
                (cx + hw + d, cyy), (cx - hw - d, cyy),
                (cx + hw + dd, cyy + hh + dd), (cx - hw - dd, cyy + hh + dd),
                (cx + hw + dd, cyy - hh - dd), (cx - hw - dd, cyy - hh - dd)]

    got = None
    for size in (TXT_H, TXT_H2):
        rf.SetTextSize(pcbnew.VECTOR2I_MM(size, size))
        rf.SetTextThickness(pcbnew.FromMM(TXT_T if size == TXT_H else TXT_T * 0.8))
        for d in DIST:
            # At the same distance prefer, in order: a spot that is both
            # unambiguous and free of tracks, then merely unambiguous, then
            # merely track-free, then any. Unambiguity comes before appearance,
            # because a designator next to the wrong part is worse than a
            # designator over a track.
            for trazi_jedno, trazi_cisto in ((True, True), (True, False),
                                             (False, True), (False, False)):
                for (tx, ty) in positions(d):
                    rf.SetPosition(pcbnew.VECTOR2I_MM(tx, ty))
                    r = rect_of(rf.GetBoundingBox(), 0.05)
                    if not free(r):
                        continue
                    if trazi_jedno and not najblizi_je_svoj(tx, ty, ref):
                        continue
                    cisto = clear_of_copper(r)
                    if trazi_cisto and not cisto:
                        continue
                    got = (r, d, cisto)
                    break
                if got:
                    break
            if got:
                break
        if got:
            break

    if got is None:
        rf.SetTextSize(pcbnew.VECTOR2I_MM(TXT_H2, TXT_H2))
        rf.SetPosition(pcbnew.VECTOR2I_MM(cx, cyy))
        got = (rect_of(rf.GetBoundingBox(), 0.05), 0.0, False)
        n_no_room += 1
    else:
        n_placed += 1
        distances.append(got[1])
        clear_of_tracks += 1 if got[2] else 0
    placed_boxes.append(got[0])

board.Save(pcb)

# ── check: is every designator nearest to ITS OWN part ──────────────────────
ambiguous = []
for fp in board.GetFootprints():
    rf = fp.Reference()
    ref = fp.GetReference()
    if not rf.IsVisible() or ref.startswith("H"):
        continue
    tx, ty = MM(rf.GetPosition().x), MM(rf.GetPosition().y)
    d_own, d_min, who = None, 1e9, None
    for (r2, rect) in bodies:
        dd = rect_dist(rect, tx, ty)
        if r2 == ref:
            d_own = dd
        if dd < d_min:
            d_min, who = dd, r2
    if who != ref:
        ambiguous.append("%s (closer to %s, %.1f vs %.1f mm)" % (ref, who, d_min, d_own))

n = n_placed + n_no_room
print("reference designators: %d in total, all horizontal, all next to their part" % n)
print("  placed next to part : %d" % n_placed)
print("  no room             : %d" % n_no_room)
if distances:
    print("  distance from body  : average %.2f mm, largest %.2f mm"
          % (sum(distances) / len(distances), max(distances)))
print("  of those clear of tracks: %d (silkscreen over a track is allowed)" % clear_of_tracks)
if ambiguous:
    print("  AMBIGUOUS: %s" % ", ".join(ambiguous))
else:
    print("  every designator is nearest to its own part")
print("saved:", pcb)
