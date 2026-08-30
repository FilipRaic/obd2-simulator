# -*- coding: utf-8 -*-
"""Stitch a single ground pad onto the MAIN ground pour, with a short trace and
a via.

    python.exe stitch_gnd_pad.py <board.kicad_pcb> <REF.PAD>

WHY IT EXISTS. Under dense routing the bottom-layer ground pour breaks up into a
main piece and a few islands. `heal_gnd_fragments.py` bridges those islands, but
on the final revision one of them defeated it: pad 1 of module U6 has a top-layer
escape only 1,2 mm long, and the via at the end of that escape landed in an
island rather than in the main pour. The result was a pad that looks connected
but is not.

This script handles exactly that case: it looks for a spot that is at once
  1. reachable from the pad on the TOP layer (maze router, 0,2 mm grid),
  2. INSIDE the main ground pour on the bottom layer,
  3. far enough from foreign copper and from other holes,
and lays a trace and a via there. The nearest such spot is chosen.
"""
import pcbnew, sys, math, heapq
from collections import defaultdict

PCB = sys.argv[1]
REF, NUM = sys.argv[2].split(".")

CELL = 0.2
TRACK_W = 0.20
CLR = 0.15
VIA_D = 0.6
VIA_DRILL = 0.3
HOLE_MIN = 0.30
MAX_R = 8.0          # mm, how far from the pad a via spot is searched for

board = pcbnew.LoadBoard(PCB)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())

bb = board.GetBoardEdgesBoundingBox()
X0 = pcbnew.ToMM(bb.GetX()); Y0 = pcbnew.ToMM(bb.GetY())
BW = pcbnew.ToMM(bb.GetWidth()); BH = pcbnew.ToMM(bb.GetHeight())
NX = int(BW / CELL) + 1
NY = int(BH / CELL) + 1


def to_cell(x, y):
    return (int(round((x - X0) / CELL)), int(round((y - Y0) / CELL)))


def to_mm(ix, iy):
    return (X0 + ix * CELL, Y0 + iy * CELL)


def find_pad(ref, num):
    for fp in board.GetFootprints():
        if fp.GetReference() != ref:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() == num:
                return fp, pad
    return None, None


fp, pad = find_pad(REF, NUM)
if pad is None:
    sys.exit("no pad %s.%s" % (REF, NUM))
NC = pad.GetNetCode()
PX = pcbnew.ToMM(pad.GetPosition().x)
PY = pcbnew.ToMM(pad.GetPosition().y)
print("pad %s.%s at (%.2f, %.2f), net %s" % (REF, NUM, PX, PY, pad.GetNetname()))

# ── the main ground pour on the bottom layer ─────────────────────────────────
gz = [z for z in board.Zones()
      if z.GetNetCode() == NC and z.IsOnLayer(pcbnew.B_Cu)]
if not gz:
    sys.exit("no ground pour on the bottom layer")
polys = gz[0].GetFilledPolysList(pcbnew.B_Cu)


def outline_pts(i):
    o = polys.Outline(i)
    return [(pcbnew.ToMM(o.CPoint(j).x), pcbnew.ToMM(o.CPoint(j).y))
            for j in range(o.PointCount())]


def area(pts):
    return abs(sum(pts[j][0] * pts[(j + 1) % len(pts)][1] -
                   pts[(j + 1) % len(pts)][0] * pts[j][1]
                   for j in range(len(pts)))) / 2.0


best_i, best_a = None, -1
for i in range(polys.OutlineCount()):
    a = area(outline_pts(i))
    if a > best_a:
        best_a, best_i = a, i
MAIN = outline_pts(best_i)
print("main pour: index %d, area %.0f mm2" % (best_i, best_a))


def inside(pts, x, y):
    c = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xin:
                c = not c
    return c


def edge_dist(pts, x, y):
    d = 1e9
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
        d = min(d, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return d


# ── prepreke na gornjem sloju ────────────────────────────────────────────────
blocked = [[False] * NY for _ in range(NX)]
blk_via = [[False] * NY for _ in range(NX)]
holes = []
margin = TRACK_W / 2 + CLR
margin_via = VIA_D / 2 + CLR


def stamp(grid, x, y, r):
    ir = int(math.ceil(r / CELL))
    cx, cy = to_cell(x, y)
    for dx in range(-ir, ir + 1):
        for dy in range(-ir, ir + 1):
            if dx * dx + dy * dy > ir * ir:
                continue
            ix, iy = cx + dx, cy + dy
            if 0 <= ix < NX and 0 <= iy < NY:
                grid[ix][iy] = True


def stamp_box(grid, x1, y1, x2, y2, m):
    ix1, iy1 = to_cell(x1 - m, y1 - m)
    ix2, iy2 = to_cell(x2 + m, y2 + m)
    for ix in range(max(0, ix1), min(NX - 1, ix2) + 1):
        for iy in range(max(0, iy1), min(NY - 1, iy2) + 1):
            grid[ix][iy] = True


def stamp_seg(grid, x1, y1, x2, y2, r):
    n = max(1, int(math.hypot(x2 - x1, y2 - y1) / (CELL / 2)))
    for i in range(n + 1):
        stamp(grid, x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n, r)


for f in board.GetFootprints():
    fref = f.GetReference()
    for p in f.Pads():
        pp = p.GetPosition()
        x, y = pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y)
        drill = pcbnew.ToMM(p.GetDrillSize().x)
        if drill > 0:
            holes.append((x, y, drill / 2))
        if not p.GetLayerSet().Contains(pcbnew.F_Cu):
            continue
        if fref == REF and p.GetNumber() == NUM:
            continue
        pb = p.GetBoundingBox()
        bx1 = pcbnew.ToMM(pb.GetX()); by1 = pcbnew.ToMM(pb.GetY())
        bx2 = bx1 + pcbnew.ToMM(pb.GetWidth()); by2 = by1 + pcbnew.ToMM(pb.GetHeight())
        stamp_box(blocked, bx1, by1, bx2, by2, margin)
        stamp_box(blk_via, bx1, by1, bx2, by2, margin_via)

for t in board.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        p = t.GetPosition()
        x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
        holes.append((x, y, VIA_DRILL / 2))
        stamp(blocked, x, y, VIA_D / 2 + margin)
        stamp(blk_via, x, y, VIA_D / 2 + margin_via)
    elif t.GetLayer() == pcbnew.F_Cu:
        a, e = t.GetStart(), t.GetEnd()
        hw = pcbnew.ToMM(t.GetWidth()) / 2
        stamp_seg(blocked, pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                  pcbnew.ToMM(e.x), pcbnew.ToMM(e.y), hw + margin)
        stamp_seg(blk_via, pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                  pcbnew.ToMM(e.x), pcbnew.ToMM(e.y), hw + margin_via)

# koridor uz sam pad
pr = max(pcbnew.ToMM(pad.GetSize().x), pcbnew.ToMM(pad.GetSize().y)) / 2
stampr = int(math.ceil((pr + 0.3) / CELL))
scx, scy = to_cell(PX, PY)
for dx in range(-stampr, stampr + 1):
    for dy in range(-stampr, stampr + 1):
        if dx * dx + dy * dy > stampr * stampr:
            continue
        ix, iy = scx + dx, scy + dy
        if 0 <= ix < NX and 0 <= iy < NY:
            blocked[ix][iy] = False


def via_ok(x, y):
    for (hx, hy, hr) in holes:
        if math.hypot(x - hx, y - hy) < hr + VIA_DRILL / 2 + HOLE_MIN:
            return False
    return True


# ── ciljne celije: unutar glavnog poligona, s rezervom do njegovog ruba ──────
goal = set()
ir = int(math.ceil(MAX_R / CELL))
for dx in range(-ir, ir + 1):
    for dy in range(-ir, ir + 1):
        ix, iy = scx + dx, scy + dy
        if not (0 <= ix < NX and 0 <= iy < NY):
            continue
        x, y = to_mm(ix, iy)
        if math.hypot(x - PX, y - PY) > MAX_R:
            continue
        if blk_via[ix][iy] or not via_ok(x, y):
            continue
        if not inside(MAIN, x, y):
            continue
        if edge_dist(MAIN, x, y) < VIA_D / 2 + 0.1:
            continue
        goal.add((ix, iy))
print("candidate via spots:", len(goal))
if not goal:
    sys.exit("no spot that is both inside the main pour and free for a via")

# ── Dijkstra over the top layer ──────────────────────────────────────────────
INF = float("inf")
dist = defaultdict(lambda: INF)
prev = {}
dist[(scx, scy)] = 0.0
pq = [(0.0, scx, scy)]
found = None
while pq:
    cd, ix, iy = heapq.heappop(pq)
    if cd > dist[(ix, iy)]:
        continue
    if (ix, iy) in goal and (ix, iy) != (scx, scy):
        found = (ix, iy)
        break
    for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                     (1, 1), (1, -1), (-1, 1), (-1, -1)):
        nx_, ny_ = ix + ddx, iy + ddy
        if not (0 <= nx_ < NX and 0 <= ny_ < NY):
            continue
        if blocked[nx_][ny_]:
            continue
        step = 1.0
        if ddx and ddy:
            if blocked[ix + ddx][iy] or blocked[ix][iy + ddy]:
                continue
            step = 1.41421356
        nd = cd + step
        if nd < dist[(nx_, ny_)]:
            dist[(nx_, ny_)] = nd
            prev[(nx_, ny_)] = (ix, iy)
            heapq.heappush(pq, (nd, nx_, ny_))

if not found:
    sys.exit("no candidate spot is reachable on the top layer")

path = [found]
while path[-1] in prev:
    path.append(prev[path[-1]])
path.reverse()

# kolinearne celije u jedan segment
out = []
run = [path[0]]
for node in path[1:]:
    if len(run) >= 2:
        a = (run[-1][0] - run[-2][0], run[-1][1] - run[-2][1])
        bdir = (node[0] - run[-1][0], node[1] - run[-1][1])
        if a != bdir:
            out.append((run[0], run[-1]))
            run = [run[-1]]
    run.append(node)
out.append((run[0], run[-1]))

total = 0.0
for a, b in out:
    ax, ay = to_mm(a[0], a[1])
    bx, by = to_mm(b[0], b[1])
    if (ax, ay) == (bx, by):
        continue
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(ax), pcbnew.FromMM(ay)))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(bx), pcbnew.FromMM(by)))
    t.SetWidth(pcbnew.FromMM(TRACK_W))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNetCode(NC)
    board.Add(t)
    total += math.hypot(bx - ax, by - ay)

# komadic od pada do prve celije
c0x, c0y = to_mm(path[0][0], path[0][1])
if abs(c0x - PX) > 1e-6 or abs(c0y - PY) > 1e-6:
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(PX), pcbnew.FromMM(PY)))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(c0x), pcbnew.FromMM(c0y)))
    t.SetWidth(pcbnew.FromMM(TRACK_W))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNetCode(NC)
    board.Add(t)
    total += math.hypot(c0x - PX, c0y - PY)

vx, vy = to_mm(found[0], found[1])
v = pcbnew.PCB_VIA(board)
v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(vx), pcbnew.FromMM(vy)))
v.SetWidth(pcbnew.FromMM(VIA_D))
v.SetDrill(pcbnew.FromMM(VIA_DRILL))
v.SetNetCode(NC)
board.Add(v)

print("stitched: a %.2f mm F.Cu trace + a via at (%.2f, %.2f)" % (total, vx, vy))
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.Save(PCB)
print("spremljeno:", PCB)
