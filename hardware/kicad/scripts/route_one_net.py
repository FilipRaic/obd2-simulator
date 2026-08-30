# -*- coding: utf-8 -*-
"""Finish ONE net on an already routed board (maze router on a 0,2 mm grid).

At this density Freerouting occasionally leaves one net unconnected, and any
placement shift that fixes it usually breaks another net. Instead, that one net
is finished here: a breadth-first search over the grid across both layers,
respecting clearance to foreign copper, keep-out areas and hole spacing.

    python.exe route_one_net.py <board.kicad_pcb> <NET_NAME> [<NET_NAME> ...]

Skripta je idempotentna: ako je net vec spojen, ne dira nista.
"""
import pcbnew, sys, math, heapq
from collections import defaultdict

PCB = sys.argv[1]
NETS = sys.argv[2:]
if not NETS:
    sys.exit("navesti barem jedan net")

CELL = 0.2          # mm, korak mreze
TRACK_W = 0.20      # mm, sirina novog voda (kao default netclass)
CLR = 0.15          # mm, minimalna zracnost
VIA_D = 0.6         # mm, promjer rupice
VIA_DRILL = 0.3
HOLE_MIN = 0.55     # mm, minimalni razmak rupa (od ruba do ruba, grubo)
VIA_COST = 12       # koliko celija "kosta" prijelaz na drugi sloj

board = pcbnew.LoadBoard(PCB)
bb = board.GetBoardEdgesBoundingBox()
X0 = pcbnew.ToMM(bb.GetX()); Y0 = pcbnew.ToMM(bb.GetY())
W = pcbnew.ToMM(bb.GetWidth()); H = pcbnew.ToMM(bb.GetHeight())
NX = int(W / CELL) + 1
NY = int(H / CELL) + 1
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]

def to_cell(x, y):
    return (int(round((x - X0) / CELL)), int(round((y - Y0) / CELL)))

def to_mm(ix, iy):
    return (X0 + ix * CELL, Y0 + iy * CELL)

def stamp(grid, x, y, r):
    """Mark every cell within radius r (mm) of a point."""
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
    """Mark a rectangle expanded by m (mm). For elongated pads this is markedly
    more accurate than a circumscribed circle, which can close a passage that
    really exists."""
    ix1, iy1 = to_cell(x1 - m, y1 - m)
    ix2, iy2 = to_cell(x2 + m, y2 + m)
    for ix in range(max(0, ix1), min(NX - 1, ix2) + 1):
        for iy in range(max(0, iy1), min(NY - 1, iy2) + 1):
            grid[ix][iy] = True

def stamp_seg(grid, x1, y1, x2, y2, r):
    n = max(1, int(math.hypot(x2 - x1, y2 - y1) / (CELL / 2)))
    for i in range(n + 1):
        stamp(grid, x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n, r)

def build_obstacles(netcode, src_pad):
    """blocked[l] = obstacles; own[l] = the net's TARGET copper (everything but
    the source pad). The source pad is neither an obstacle nor a target,
    otherwise the search immediately 'arrives' at itself and does nothing."""
    src_pos = (round(pcbnew.ToMM(src_pad.GetPosition().x), 4),
               round(pcbnew.ToMM(src_pad.GetPosition().y), 4))
    blocked = {l: [[False] * NY for _ in range(NX)] for l in LAYERS}
    # A separate grid for VIAS: a 0,6 mm diameter needs more clearance than a
    # 0,2 mm track, so a via must not be placed using the track grid.
    blk_via = {l: [[False] * NY for _ in range(NX)] for l in LAYERS}
    own = {l: [[False] * NY for _ in range(NX)] for l in LAYERS}
    holes = []

    # rub ploce
    for l in LAYERS:
        g = blocked[l]
        for ix in range(NX):
            for iy in range(NY):
                x, y = to_mm(ix, iy)
                if (x < X0 + 0.6 or x > X0 + W - 0.6 or
                        y < Y0 + 0.6 or y > Y0 + H - 0.6):
                    g[ix][iy] = True

    # zone zabrane (antena): ni vodovi ni rupice
    for z in board.Zones():
        if not z.GetIsRuleArea():
            continue
        zb = z.GetBoundingBox()
        zx1 = pcbnew.ToMM(zb.GetX()); zy1 = pcbnew.ToMM(zb.GetY())
        zx2 = zx1 + pcbnew.ToMM(zb.GetWidth()); zy2 = zy1 + pcbnew.ToMM(zb.GetHeight())
        for l in LAYERS:
            g = blocked[l]
            for ix in range(NX):
                for iy in range(NY):
                    x, y = to_mm(ix, iy)
                    if zx1 - 0.3 <= x <= zx2 + 0.3 and zy1 - 0.3 <= y <= zy2 + 0.3:
                        g[ix][iy] = True

    margin = TRACK_W / 2 + CLR
    margin_via = VIA_D / 2 + CLR

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            p, s = pad.GetPosition(), pad.GetSize()
            x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
            r = max(pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)) / 2
            drill = pcbnew.ToMM(pad.GetDrillSize().x)
            if drill > 0:
                holes.append((x, y, drill / 2))
            for l in LAYERS:
                if not pad.GetLayerSet().Contains(l):
                    continue
                if pad.GetNetCode() == netcode:
                    if (round(x, 4), round(y, 4)) != src_pos:
                        stamp(own[l], x, y, max(r * 0.6, CELL))
                else:
                    pb = pad.GetBoundingBox()
                    bx1 = pcbnew.ToMM(pb.GetX()); by1 = pcbnew.ToMM(pb.GetY())
                    bx2 = bx1 + pcbnew.ToMM(pb.GetWidth())
                    by2 = by1 + pcbnew.ToMM(pb.GetHeight())
                    stamp_box(blocked[l], bx1, by1, bx2, by2, margin)
                    stamp_box(blk_via[l], bx1, by1, bx2, by2, margin_via)

    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
            holes.append((x, y, VIA_DRILL / 2))
            for l in LAYERS:
                if t.GetNetCode() == netcode:
                    stamp(own[l], x, y, CELL)
                else:
                    stamp(blocked[l], x, y, VIA_D / 2 + margin)
                    stamp(blk_via[l], x, y, VIA_D / 2 + margin_via)
        else:
            l = t.GetLayer()
            if l not in LAYERS:
                continue
            a, e = t.GetStart(), t.GetEnd()
            x1, y1 = pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)
            x2, y2 = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
            hw = pcbnew.ToMM(t.GetWidth()) / 2
            if t.GetNetCode() == netcode:
                stamp_seg(own[l], x1, y1, x2, y2, CELL)
            else:
                stamp_seg(blocked[l], x1, y1, x2, y2, hw + margin)
                stamp_seg(blk_via[l], x1, y1, x2, y2, hw + margin_via)

    # The board edge and the keep-out area apply to vias as well. The keep-out is
    # already written into `blocked` before pads and tracks were added, so it is
    # carried over by taking the union with a slightly wider margin.
    for l in LAYERS:
        gv = blk_via[l]
        for ix in range(NX):
            for iy in range(NY):
                x, y = to_mm(ix, iy)
                if (x < X0 + 0.9 or x > X0 + W - 0.9 or
                        y < Y0 + 0.9 or y > Y0 + H - 0.9):
                    gv[ix][iy] = True
    for z in board.Zones():
        if not z.GetIsRuleArea():
            continue
        zb = z.GetBoundingBox()
        zx1 = pcbnew.ToMM(zb.GetX()); zy1 = pcbnew.ToMM(zb.GetY())
        zx2 = zx1 + pcbnew.ToMM(zb.GetWidth()); zy2 = zy1 + pcbnew.ToMM(zb.GetHeight())
        for l in LAYERS:
            stamp_box(blk_via[l], zx1, zy1, zx2, zy2, 0.5)

    return blocked, blk_via, own, holes

def via_ok(x, y, holes):
    for (hx, hy, hr) in holes:
        if math.hypot(x - hx, y - hy) < hr + VIA_DRILL / 2 + HOLE_MIN:
            return False
    return True

def route(netname):
    net = board.GetNetsByName().get(netname) if hasattr(board.GetNetsByName(), 'get') else None
    if net is None:
        nets = board.GetNetsByName()
        if netname not in [str(k) for k in nets.keys()]:
            print("net %s ne postoji" % netname); return False
        net = nets[netname]
    nc = net.GetNetCode()

    # NOTE: the id() of a SWIG wrapper is NOT stable between pcbnew API calls, so
    # group membership must not be determined through id(). Instead it is checked
    # geometrically whether the pad touches any trace or via of the same net.
    pads = [p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetCode() == nc]
    if len(pads) < 2:
        print("%s: manje od dva pada, preskacem" % netname); return False

    ends = []
    for t in board.GetTracks():
        if t.GetNetCode() != nc:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition(); ends.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
        else:
            for p in (t.GetStart(), t.GetEnd()):
                ends.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))

    def touched(pad):
        pb = pad.GetBoundingBox()
        x1 = pcbnew.ToMM(pb.GetX()); y1 = pcbnew.ToMM(pb.GetY())
        x2 = x1 + pcbnew.ToMM(pb.GetWidth()); y2 = y1 + pcbnew.ToMM(pb.GetHeight())
        return any(x1 - 0.05 <= ex <= x2 + 0.05 and y1 - 0.05 <= ey <= y2 + 0.05
                   for (ex, ey) in ends)

    missing = [p for p in pads if not touched(p)]
    if not missing:
        print("%s: every pad already has copper, skipping" % netname); return False
    # There used to be an early exit here for "the net is not routed at all". It
    # was unnecessary - `own` holds ALL the other pads of the net, so the same
    # search leads from pad to pad just as well when there is no copper yet. On
    # this board Freerouting can leave a whole short net (CC2) unrouted, not just
    # one of its ends. For a net with more than two pads the caller repeats the
    # call while it keeps making progress.

    src = missing[0]
    blocked, blk_via, own, holes = build_obstacles(nc, src)
    sx, sy = pcbnew.ToMM(src.GetPosition().x), pcbnew.ToMM(src.GetPosition().y)
    scx, scy = to_cell(sx, sy)
    sl = 0 if src.GetLayerSet().Contains(pcbnew.F_Cu) else 1

    # goal: any cell of our own copper that is NOT adjacent to the source
    goal = {l: own[LAYERS[l]] for l in (0, 1)}

    INF = float('inf')
    dist = {0: defaultdict(lambda: INF), 1: defaultdict(lambda: INF)}
    prev = {}
    pq = [(0, scx, scy, sl)]
    dist[sl][(scx, scy)] = 0
    found = None
    while pq:
        d, ix, iy, l = heapq.heappop(pq)
        if d > dist[l][(ix, iy)]:
            continue
        if goal[l][ix][iy]:
            found = (ix, iy, l); break
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx_, ny_ = ix + dx, iy + dy
            if not (0 <= nx_ < NX and 0 <= ny_ < NY):
                continue
            if blocked[LAYERS[l]][nx_][ny_] and not goal[l][nx_][ny_]:
                continue
            nd = d + 1
            if nd < dist[l][(nx_, ny_)]:
                dist[l][(nx_, ny_)] = nd
                prev[(nx_, ny_, l)] = (ix, iy, l)
                heapq.heappush(pq, (nd, nx_, ny_, l))
        ol = 1 - l
        x, y = to_mm(ix, iy)
        if (not blk_via[LAYERS[ol]][ix][iy] and not blk_via[LAYERS[l]][ix][iy]
                and via_ok(x, y, holes)):
            nd = d + VIA_COST
            if nd < dist[ol][(ix, iy)]:
                dist[ol][(ix, iy)] = nd
                prev[(ix, iy, ol)] = (ix, iy, l)
                heapq.heappush(pq, (nd, ix, iy, ol))

    if not found:
        ngoal = sum(1 for l in (0, 1) for ix in range(NX) for iy in range(NY)
                    if goal[l][ix][iy])
        nvis = sum(1 for l in (0, 1) for v in dist[l].values() if v < INF)
        srcblk = [blocked[LAYERS[l]][scx][scy] for l in (0, 1)]
        print("%s: NEMA puta | ciljnih celija=%d | posjeceno=%d | "
              "izvor (%d,%d) blokiran F/B=%s" %
              (netname, ngoal, nvis, scx, scy, srcblk))
        return False

    path = [found]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()

    # Put -> skupine po sloju -> unutar skupine kolinearne dionice.
    groups = [[path[0]]]
    vias = []
    for node in path[1:]:
        if node[2] != groups[-1][-1][2]:
            vias.append(to_mm(node[0], node[1]))
            groups.append([node])
        else:
            groups[-1].append(node)

    def emit(p1, p2, layer):
        a = to_mm(p1[0], p1[1]); b_ = to_mm(p2[0], p2[1])
        if a == b_:
            return 0
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I_MM(a[0], a[1]))
        t.SetEnd(pcbnew.VECTOR2I_MM(b_[0], b_[1]))
        t.SetLayer(LAYERS[layer]); t.SetNetCode(nc)
        t.SetWidth(pcbnew.FromMM(TRACK_W))
        board.Add(t)
        return 1

    added = 0
    for grp in groups:
        if len(grp) < 2:
            continue
        layer = grp[0][2]
        start = grp[0]
        for i in range(1, len(grp)):
            d_prev = (grp[i][0] - grp[i-1][0], grp[i][1] - grp[i-1][1])
            d_run = (grp[i-1][0] - start[0], grp[i-1][1] - start[1])
            straight = (d_run == (0, 0) or
                        (d_run[0] == 0 and d_prev[0] == 0) or
                        (d_run[1] == 0 and d_prev[1] == 0))
            if not straight:
                added += emit(start, grp[i-1], layer)
                start = grp[i-1]
        added += emit(start, grp[-1], layer)

    for (x, y) in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I_MM(x, y))
        v.SetDrill(pcbnew.FromMM(VIA_DRILL)); v.SetWidth(pcbnew.FromMM(VIA_D))
        v.SetNetCode(nc); v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(v)

    print("%s: dodano %d segmenata, %d rupica (duljina puta %d celija)"
          % (netname, added, len(vias), len(path)))
    return True

changed = False
for n in NETS:
    # Several calls: one call joins one pad to the rest of the net, so a net with
    # three or more pads needs as many passes as it has open ends.
    for _ in range(8):
        if not route(n):
            break
        changed = True

if changed:
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    print("saved:", PCB)
else:
    print("nothing changed")
