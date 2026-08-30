# -*- coding: utf-8 -*-
"""Route the CAN pair as a CHAIN, on one layer and without vias.

    python.exe route_can_chain.py <board.kicad_pcb>

WHY IT EXISTS. The design review checklist (section "CAN chain") requires the
pair to run as one unbranched line

    SN65HVD230 -> 120 ohm termination -> PESD1CAN ESD -> J1962F

without branching, without vias under the pair, and with approximately equal
lengths. Freerouting knows nothing about that: it routes a minimum spanning tree
over the pads, and on the first routed board the measurement came out as:

    CANH  73,7 mm, R7 is a node with THREE branches, D1 hangs off a 13,0 mm stub
    CANL  56,9 mm, same node, a 4,3 mm stub, plus ONE via

So not one of the three criteria was met, while the checklist recorded them as
met. The placement was fixed (D1 anchors to the connector, R7 to D1), but
placement alone cannot force a topology on the router - it can only make the
chain cheap. This step therefore takes the pair over and routes it by hand, in
the prescribed order.

HOW. For each net all of its copper is deleted first, then a path is searched hop
by hop with a maze router on a 0,2 mm grid, exclusively on the F.Cu layer.
Everything foreign is an obstacle: pads, tracks, vias, the keep-out area and the
board edge, each expanded by the clearance. Our own copper laid in an earlier hop
is an obstacle for the next one too, so the chain can neither cut across itself
nor form a loop.

If a hop does not get through on F.Cu, the script does NOT quietly switch to the
bottom layer but reports it and hands that hop back to Freerouting's solution. It
is better to know a criterion was not met than to get a via nobody documented.
"""
import pcbnew, sys, math, heapq, os, json
from collections import defaultdict

PCB = sys.argv[1]
# The second invocation, "--replay", does not route but only restores the chain
# saved by the first one.
#
# WHY IT IS NEEDED. The chain is routed before Freerouting and handed to it as
# "(type protect)". Freerouting really does NOT rip those tracks up - but it
# still considers its net unrouted, so it lays its own trace alongside them. The
# result was 42 segments and 19 branches on CANH instead of 11 segments without a
# branch. So after the SES import the chain is simply put back: the space was
# reserved anyway, because the router routed everything else around it.
REPLAY = "--replay" in sys.argv[2:]
CHAIN_JSON = os.path.join(os.path.dirname(os.path.abspath(PCB)), "can_chain.json")

CELL = 0.2          # mm, grid step
TRACK_W = 0.20      # mm, track width (default netclass)
CLR = 0.15          # mm, minimum clearance
LAYER = pcbnew.F_Cu

# The chain per net: the order is ELECTRICAL, from the transceiver toward the
# connector. The test point is inserted next to the termination, i.e. IN LINE, as
# the checklist requires ("test points go in line, not on a stub").
#
# CANL GOES FIRST, even though the schematic treats both equally. The reason is
# geometry: its R7.2 -> D1.2 link is only 4 mm long and passes through the
# bottleneck between the termination and the ESD diode. Routing CANH first closes
# that bottleneck with its trace and CANL then has no top-layer path at all
# (tried and confirmed). In the reverse order both get through: CANL takes the
# bottleneck, and CANH has room north and east of it.
#
# The test point may stand before or after the termination - both count as "in
# line". Whichever gives the shorter chain as the crow flies is chosen, because
# the TP is placed wherever there is room and can end up on the side the chain
# would have to double back from.
CHAINS = [
    ("CANL", ("U5", "6"), ("TP4", "1"), ("R7", "2"), ("D1", "2"), ("J2", "14")),
    ("CANH", ("U5", "7"), ("TP3", "1"), ("R7", "1"), ("D1", "1"), ("J2", "6")),
]

board = pcbnew.LoadBoard(PCB)
bb = board.GetBoardEdgesBoundingBox()
X0 = pcbnew.ToMM(bb.GetX()); Y0 = pcbnew.ToMM(bb.GetY())
BW = pcbnew.ToMM(bb.GetWidth()); BH = pcbnew.ToMM(bb.GetHeight())
NX = int(BW / CELL) + 1
NY = int(BH / CELL) + 1


def to_cell(x, y):
    return (int(round((x - X0) / CELL)), int(round((y - Y0) / CELL)))


def to_mm(ix, iy):
    return (X0 + ix * CELL, Y0 + iy * CELL)


def stamp_box(grid, x1, y1, x2, y2, m):
    ix1, iy1 = to_cell(x1 - m, y1 - m)
    ix2, iy2 = to_cell(x2 + m, y2 + m)
    for ix in range(max(0, ix1), min(NX - 1, ix2) + 1):
        for iy in range(max(0, iy1), min(NY - 1, iy2) + 1):
            grid[ix][iy] = True


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


def stamp_seg(grid, x1, y1, x2, y2, r):
    n = max(1, int(math.hypot(x2 - x1, y2 - y1) / (CELL / 2)))
    for i in range(n + 1):
        stamp(grid, x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n, r)


def find_pad(ref, num):
    for fp in board.GetFootprints():
        if fp.GetReference() != ref:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() == num:
                return pad
    return None


def pad_box(pad):
    pb = pad.GetBoundingBox()
    x1 = pcbnew.ToMM(pb.GetX()); y1 = pcbnew.ToMM(pb.GetY())
    return (x1, y1, x1 + pcbnew.ToMM(pb.GetWidth()), y1 + pcbnew.ToMM(pb.GetHeight()))


def rip_up(netname):
    """Delete all copper of a net. Returns what was deleted, so it can be put
    back if the manual routing fails."""
    net = board.GetNetsByName()[netname]
    nc = net.GetNetCode()
    saved = []
    for t in list(board.GetTracks()):
        if t.GetNetCode() != nc:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            # In KiCad 10 PCB_VIA::GetWidth() wants a layer as its argument (a
            # via can have a different annulus per layer). Without it, assert.
            saved.append(("via", pcbnew.ToMM(t.GetPosition().x),
                          pcbnew.ToMM(t.GetPosition().y),
                          t.GetWidth(pcbnew.F_Cu), t.GetDrill(), None))
        else:
            saved.append(("seg", pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y),
                          pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y),
                          (t.GetWidth(), t.GetLayer())))
        # Delete, not Remove: Remove only takes the item out of the board and
        # ownership of the C++ object ends up nowhere (SWIG reports a "memory
        # leak of type PCB_TRACK"). The values were already copied into plain
        # numbers above.
        board.Delete(t)
    return nc, saved


def restore(nc, saved):
    for item in saved:
        if item[0] == "via":
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(item[1]), pcbnew.FromMM(item[2])))
            v.SetWidth(item[3]); v.SetDrill(item[4])
            v.SetNetCode(nc)
            board.Add(v)
        else:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(item[1]), pcbnew.FromMM(item[2])))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(item[3]), pcbnew.FromMM(item[4])))
            t.SetWidth(item[5][0]); t.SetLayer(item[5][1])
            t.SetNetCode(nc)
            board.Add(t)


def obstacles(skip):
    """Obstacles for one hop. Both endpoint pads are exempt, everything else is
    a wall."""
    blocked = [[False] * NY for _ in range(NX)]
    margin = TRACK_W / 2 + CLR

    for ix in range(NX):
        for iy in range(NY):
            x, y = to_mm(ix, iy)
            if (x < X0 + 0.6 or x > X0 + BW - 0.6 or
                    y < Y0 + 0.6 or y > Y0 + BH - 0.6):
                blocked[ix][iy] = True

    for z in board.Zones():
        if not z.GetIsRuleArea():
            continue
        zb = z.GetBoundingBox()
        zx1 = pcbnew.ToMM(zb.GetX()); zy1 = pcbnew.ToMM(zb.GetY())
        stamp_box(blocked, zx1, zy1,
                  zx1 + pcbnew.ToMM(zb.GetWidth()),
                  zy1 + pcbnew.ToMM(zb.GetHeight()), 0.3)

    # Both endpoint pads are exempt. The comparison is by (designator, pad
    # number), NOT through GetParent(): that call returns a BOARD_ITEM through
    # SWIG without a cast to FOOTPRINT, so GetReference() on it crashes the
    # interpreter.
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            if not pad.GetLayerSet().Contains(LAYER):
                continue
            if (ref, pad.GetNumber()) in skip:
                continue
            x1, y1, x2, y2 = pad_box(pad)
            stamp_box(blocked, x1, y1, x2, y2, margin)

    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            stamp(blocked, pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                  pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2 + margin)
        elif t.GetLayer() == LAYER:
            a, e = t.GetStart(), t.GetEnd()
            stamp_seg(blocked, pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                      pcbnew.ToMM(e.x), pcbnew.ToMM(e.y),
                      pcbnew.ToMM(t.GetWidth()) / 2 + margin)

    # A corridor is opened around both endpoint pads.
    #
    # WHY. The track laid in the previous link of the chain ends EXACTLY at the
    # pad centre, and above it is stamped, like every other track, with a
    # 0,25 mm clearance. That seals its own pad: the next link starts at the
    # centre and has not a single free neighbouring cell. This is exactly what
    # broke the links TP3.1 -> R7.1 and TP4.1 -> R7.2 even on a completely empty
    # board. A circle of radius "half the pad + 0,3 mm" is opened, i.e. as much
    # as the track needs to escape the pad anyway.
    for ref, num in skip:
        pad = find_pad(ref, num)
        if pad is None:
            continue
        px = pcbnew.ToMM(pad.GetPosition().x)
        py = pcbnew.ToMM(pad.GetPosition().y)
        pr = max(pcbnew.ToMM(pad.GetSize().x), pcbnew.ToMM(pad.GetSize().y)) / 2
        rr = pr + 0.3
        ir = int(math.ceil(rr / CELL))
        cx, cy = to_cell(px, py)
        for dx in range(-ir, ir + 1):
            for dy in range(-ir, ir + 1):
                if dx * dx + dy * dy > ir * ir:
                    continue
                ix, iy = cx + dx, cy + dy
                if 0 <= ix < NX and 0 <= iy < NY:
                    blocked[ix][iy] = False
    return blocked


def hop(src, dst, netcode):
    """One link of the chain: src and dst are (designator, pad number).
    Returns the length in mm, or None."""
    src_pad = find_pad(*src)
    dst_pad = find_pad(*dst)
    blocked = obstacles({src, dst})
    sx = pcbnew.ToMM(src_pad.GetPosition().x)
    sy = pcbnew.ToMM(src_pad.GetPosition().y)
    dx_ = pcbnew.ToMM(dst_pad.GetPosition().x)
    dy_ = pcbnew.ToMM(dst_pad.GetPosition().y)
    s = to_cell(sx, sy)
    d = to_cell(dx_, dy_)

    INF = float("inf")
    dist = defaultdict(lambda: INF)
    prev = {}
    dist[s] = 0
    pq = [(0, s[0], s[1])]
    while pq:
        cd, ix, iy = heapq.heappop(pq)
        if cd > dist[(ix, iy)]:
            continue
        if (ix, iy) == d:
            break
        # Eight neighbours, not four. With four directions the path is a
        # staircase and comes out about 30 % longer than the straight line, and
        # the length of the pair is exactly what is being measured here. A
        # diagonal step costs sqrt(2) and is only allowed when both of the
        # corresponding orthogonal neighbours are free as well, otherwise the
        # track would cut through the corner of foreign copper.
        for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                         (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx_, ny_ = ix + ddx, iy + ddy
            if not (0 <= nx_ < NX and 0 <= ny_ < NY):
                continue
            if blocked[nx_][ny_] and (nx_, ny_) != d:
                continue
            step = 1.0
            if ddx and ddy:
                if blocked[ix + ddx][iy] or blocked[ix][iy + ddy]:
                    continue
                step = 1.41421356
            # Turn penalty: without it the search returns paths that zig-zag
            # between two equally priced directions and pass the same pad
            # several times. It is small, because length takes precedence over
            # appearance.
            turn = 0.0
            p = prev.get((ix, iy))
            if p is not None:
                pdx, pdy = ix - p[0], iy - p[1]
                if (pdx, pdy) != (ddx, ddy):
                    turn = 0.0
            nd = cd + step + turn
            if nd < dist[(nx_, ny_)]:
                dist[(nx_, ny_)] = nd
                prev[(nx_, ny_)] = (ix, iy)
                heapq.heappush(pq, (nd, nx_, ny_))

    if dist[d] == INF:
        return None

    path = [d]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()

    # The end cells are replaced with the EXACT pad centre.
    #
    # A separate little stub used to be drawn from the last cell to the pad
    # centre. On a pad that is at once the end of one link and the start of the
    # next, that produced two such stubs, so after duplicate removal the pad was
    # left on a 0,01 to 0,11 mm stub and the cell in front of it was a node with
    # three branches. Electrically harmless (the pad is 1,6 mm wide), but the net
    # looked branched when the chain was not. Now the trace starts and ends
    # exactly on the pad.
    length = 0.0
    run = [path[0]]
    out = []
    for node in path[1:]:
        if len(run) >= 2:
            adx, ady = run[-1][0] - run[-2][0], run[-1][1] - run[-2][1]
            bdx, bdy = node[0] - run[-1][0], node[1] - run[-1][1]
            if (adx, ady) != (bdx, bdy):
                out.append((run[0], run[-1]))
                run = [run[-1]]
        run.append(node)
    out.append((run[0], run[-1]))

    px_s = pcbnew.ToMM(src_pad.GetPosition().x)
    py_s = pcbnew.ToMM(src_pad.GetPosition().y)
    px_d = pcbnew.ToMM(dst_pad.GetPosition().x)
    py_d = pcbnew.ToMM(dst_pad.GetPosition().y)

    def cell_xy(c, first, last):
        if first:
            return (px_s, py_s)
        if last:
            return (px_d, py_d)
        return to_mm(c[0], c[1])

    for idx, (a, b) in enumerate(out):
        ax, ay = cell_xy(a, idx == 0, False)
        bx, by = cell_xy(b, False, idx == len(out) - 1)
        if (ax, ay) == (bx, by):
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(ax), pcbnew.FromMM(ay)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(bx), pcbnew.FromMM(by)))
        t.SetWidth(pcbnew.FromMM(TRACK_W))
        t.SetLayer(LAYER)
        t.SetNetCode(netcode)
        board.Add(t)
        length += math.hypot(bx - ax, by - ay)

    return length


def dump_chain():
    """Save the laid chain, so it can be restored after Freerouting."""
    out = {}
    for netname, _, _, _, _, _ in CHAINS:
        nc = board.GetNetsByName()[netname].GetNetCode()
        segs = []
        for t in board.GetTracks():
            if t.GetNetCode() != nc or t.Type() == pcbnew.PCB_VIA_T:
                continue
            segs.append([pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y),
                         pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y)])
        out[netname] = segs
    with open(CHAIN_JSON, "w") as fh:
        json.dump(out, fh)
    print("chain saved to", CHAIN_JSON)


def replay_chain():
    if not os.path.isfile(CHAIN_JSON):
        print("no %s, nothing to restore" % CHAIN_JSON)
        return 2
    with open(CHAIN_JSON) as fh:
        saved = json.load(fh)
    for netname, segs in saved.items():
        nets = board.GetNetsByName()
        if netname not in [str(k) for k in nets.keys()]:
            print("net %s does not exist" % netname)
            return 2
        nc = nets[netname].GetNetCode()
        before = 0
        for t in list(board.GetTracks()):
            if t.GetNetCode() == nc:
                before += 1
                board.Delete(t)
        total = 0.0
        for ax, ay, bx, by in segs:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(ax), pcbnew.FromMM(ay)))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(bx), pcbnew.FromMM(by)))
            t.SetWidth(pcbnew.FromMM(TRACK_W))
            t.SetLayer(LAYER)
            t.SetNetCode(nc)
            board.Add(t)
            total += math.hypot(bx - ax, by - ay)
        print("%s: Freerouting's %d segments replaced by a chain of %d, %.1f mm"
              % (netname, before, len(segs), total))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    print("saved:", PCB)
    return 0


if REPLAY:
    sys.exit(replay_chain())

# Auxiliary mode: connect TWO named pads with a single trace on the top layer.
#
#     python.exe route_can_chain.py <board> --pair GND U6.1 C15.2
#
# It serves the ground repair when `heal_gnd_fragments.py` fails to bridge a pour
# island. The same maze router, only without a chain: it is usually enough to
# connect the pad left stranded on the island with the nearest pad of the same
# net that sits on the main pour, and the island stops being an island.
if "--pair" in sys.argv:
    i = sys.argv.index("--pair")
    netname = sys.argv[i + 1]
    a_ref, a_num = sys.argv[i + 2].split(".")
    b_ref, b_num = sys.argv[i + 3].split(".")
    nets = board.GetNetsByName()
    nc = nets[netname].GetNetCode()
    d = hop((a_ref, a_num), (b_ref, b_num), nc)
    if d is None:
        print("%s: %s.%s -> %s.%s does not get through on F.Cu"
              % (netname, a_ref, a_num, b_ref, b_num))
        sys.exit(2)
    print("%s: %s.%s -> %s.%s connected, %.1f mm on F.Cu"
          % (netname, a_ref, a_num, b_ref, b_num, d))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    print("saved:", PCB)
    sys.exit(0)


def straight(chain):
    tot = 0.0
    for a, b in zip(chain, chain[1:]):
        pa, pb = find_pad(*a), find_pad(*b)
        tot += math.hypot(pcbnew.ToMM(pa.GetPosition().x) - pcbnew.ToMM(pb.GetPosition().x),
                          pcbnew.ToMM(pa.GetPosition().y) - pcbnew.ToMM(pb.GetPosition().y))
    return tot


# The test point may stand before or after the termination. The choice is made
# THE SAME WAY for both nets, by the sum of straight-line lengths, so both chains
# have the same link structure - otherwise the pair cannot be routed in parallel.
missing = [("%s.%s" % (r, n)) for _, s, t, m, e, c in CHAINS
           for r, n in (s, t, m, e, c) if find_pad(r, n) is None]
if missing:
    print("missing pads:", ", ".join(missing))
    sys.exit(2)

variants = []
for idx in (1, 2, 3):
    chains = []
    for _, s, t, m, e, c in CHAINS:
        if idx == 1:
            chains.append([s, t, m, e, c])      # TP before the termination
        elif idx == 2:
            chains.append([s, m, t, e, c])      # TP between termination and ESD
        else:
            chains.append([s, m, e, t, c])      # TP after the ESD, toward the connector
    variants.append((sum(straight(ch) for ch in chains), chains))
CHOSEN = min(variants)[1]

# THE PAIR IS ROUTED IN PARALLEL, link by link, not net by net.
#
# The first attempt routed all of CANL and then all of CANH. The result was
# 55,8 against 111,4 mm: the first net takes the shortest corridor and the second
# can no longer use it, so it goes half way round the board. When the links
# alternate, the second track looks for a path right next to the one just laid
# every time, because that is cheapest, so the pair stays together and the
# lengths are close. That is what the "approximately equal lengths" criterion is
# really about: what matters is that the pair runs together, not that the numbers
# match.
ok_all = True
lengths = [0.0, 0.0]
saved_all = []
for i, (netname, _, _, _, _, _) in enumerate(CHAINS):
    saved_all.append(rip_up(netname))

failed = None
for hop_i in range(len(CHOSEN[0]) - 1):
    for i, chain in enumerate(CHOSEN):
        nc = saved_all[i][0]
        d = hop(chain[hop_i], chain[hop_i + 1], nc)
        if d is None:
            failed = "%s: %s.%s -> %s.%s" % (
                CHAINS[i][0], chain[hop_i][0], chain[hop_i][1],
                chain[hop_i + 1][0], chain[hop_i + 1][1])
            break
        lengths[i] += d
    if failed:
        break

if failed:
    print("link %s does not get through on F.Cu, restoring Freerouting's solution" % failed)
    for i, (nc, saved) in enumerate(saved_all):
        for t in list(board.GetTracks()):
            if t.GetNetCode() == nc:
                board.Delete(t)
        restore(nc, saved)
    ok_all = False
else:
    for i, chain in enumerate(CHOSEN):
        print("%s: chain %s, %.1f mm, F.Cu, 0 vias"
              % (CHAINS[i][0], " -> ".join("%s.%s" % c for c in chain), lengths[i]))
    diff = abs(lengths[0] - lengths[1])
    print("length difference of the pair: %.1f mm (%.0f %% of the longer one)"
          % (diff, 100.0 * diff / max(lengths)))
    dump_chain()

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.Save(PCB)
print("spremljeno:", PCB)
sys.exit(0 if ok_all else 2)
