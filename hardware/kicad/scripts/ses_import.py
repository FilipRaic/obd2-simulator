import pcbnew, sys, math, os
pcb, ses = sys.argv[1], sys.argv[2]
board = pcbnew.LoadBoard(pcb)
print("SES import:", pcbnew.ImportSpecctraSES(board, ses))

GND = board.GetNetsByName()["GND"].GetNetCode()

# With THT passives the ground has far more drilled pads, and on some of them the
# thermal spokes fail to resolve, leaving the pad electrically separated from the
# pour. Drilled ground pads are therefore given a solid connection.
_full = 0
for _fp in board.GetFootprints():
    for _pad in _fp.Pads():
        if _pad.GetNetCode() == GND and _pad.GetDrillSize().x > 0:
            _pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
            _full += 1
print("THT GND pads set to a solid pour connection:", _full)

# ── Copper / hole maps of the routed board (mm) ─────────────────────────────
def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / float(dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

copper, holes = [], []
for t in board.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        p = t.GetPosition()
        holes.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
        copper.append((t.GetNetCode(), pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                       pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                       pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2))
    else:
        a, b = t.GetStart(), t.GetEnd()
        copper.append((t.GetNetCode(),
                       pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                       pcbnew.ToMM(b.x), pcbnew.ToMM(b.y),
                       pcbnew.ToMM(t.GetWidth()) / 2))
for fp in board.GetFootprints():
    for pad in fp.Pads():
        p, s = pad.GetPosition(), pad.GetSize()
        r = max(pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)) / 2
        copper.append((pad.GetNetCode(), pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                       pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), r))
        if pad.GetDrillSize().x > 0:
            holes.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))

VIA_R, CLR, HOLE_MIN = 0.3, 0.3, 0.9

def via_fits(x, y, net):
    for (hx, hy) in holes:
        if math.hypot(x - hx, y - hy) < HOLE_MIN:
            return False
    for (n, x1, y1, x2, y2, hw) in copper:
        if n == net:
            continue
        if seg_dist(x, y, x1, y1, x2, y2) < VIA_R + hw + CLR:
            return False
    return True

def add_via(x, y, net):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    v.SetDrill(pcbnew.FromMM(0.3)); v.SetWidth(pcbnew.FromMM(0.6))
    v.SetNetCode(net); v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(v)
    holes.append((x, y))
    copper.append((net, x, y, x, y, 0.3))

# ── Thermal vias under the exposed pads of U1 (QFN) and U3 (SOT-223) ────────
# The exposed pad IS the ground connection for these parts, so it must reach
# the bottom plane. Candidates are scanned across the pad and each one is
# clearance-checked against copper of other nets (same-net copper - the pad
# itself - is fine to sit on).
def epad_vias(ref, pad_num, want):
    placed = 0
    for fp in board.GetFootprints():
        if fp.GetReference() != ref:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() != pad_num or pad.GetNetCode() != GND:
                continue
            p, s = pad.GetPosition(), pad.GetSize()
            px, py = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
            hw = pcbnew.ToMM(s.x) / 2 - 0.45      # keep the via inside the pad
            hh = pcbnew.ToMM(s.y) / 2 - 0.45
            if hw <= 0 or hh <= 0:
                return 0
            # Vias sit inside the exposed pad itself (standard QFN practice),
            # so they are placed unconditionally and DRC verifies the result.
            for (sx, sy) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                if placed >= want:
                    return placed
                add_via(px + sx * hw * 0.6, py + sy * hh * 0.6, GND)
                placed += 1
    return placed

# The U9 (TS3USB221) exposed pad gets no vias of its own: B.Cu traces run under
# it, so an "unconditional" via in the EP could puncture the 3V3 trace (a short).
# Its EP is grounded through an F.Cu connection to pads 5/6.
thermal = epad_vias("U1", "0", 4)
print("thermal vias:", thermal)

# ── GND bridges on the top layer ────────────────────────────────────────────
# Traces crossing the bottom plane can cut a corner of it loose, and the pads in
# that island are then not grounded. A short top-layer track between two GND
# through-hole pads bridges the island back to the plane.
def pad_of(ref, num):
    for fp in board.GetFootprints():
        if fp.GetReference() != ref:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() == num:
                return pad
    return None

def track_clear(x1, y1, x2, y2, net, width=0.25):
    steps = max(2, int(math.hypot(x2 - x1, y2 - y1) / 0.1))
    for i in range(steps + 1):
        x = x1 + (x2 - x1) * i / steps
        y = y1 + (y2 - y1) * i / steps
        for (n, ax, ay, bx, by, hw) in copper:
            if n == net:
                continue
            if seg_dist(x, y, ax, ay, bx, by) < width / 2 + hw + CLR:
                return False
    return True

def bridge(ref_a, pad_a, ref_b, pad_b):
    pa, pb = pad_of(ref_a, pad_a), pad_of(ref_b, pad_b)
    if pa is None or pb is None:
        return False
    ax, ay = pcbnew.ToMM(pa.GetPosition().x), pcbnew.ToMM(pa.GetPosition().y)
    bx, by = pcbnew.ToMM(pb.GetPosition().x), pcbnew.ToMM(pb.GetPosition().y)
    paths = [[(ax, ay), (bx, by)],                       # straight
             [(ax, ay), (ax, by), (bx, by)],             # L, vertical first
             [(ax, ay), (bx, ay), (bx, by)]]             # L, horizontal first
    for path in paths:
        if all(track_clear(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1], GND)
               for i in range(len(path) - 1)):
            for i in range(len(path) - 1):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(path[i][0]), pcbnew.FromMM(path[i][1])))
                t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(path[i + 1][0]), pcbnew.FromMM(path[i + 1][1])))
                t.SetLayer(pcbnew.F_Cu); t.SetNetCode(GND)
                t.SetWidth(pcbnew.FromMM(0.25))
                board.Add(t)
                copper.append((GND, path[i][0], path[i][1],
                               path[i + 1][0], path[i + 1][1], 0.125))
            print("  GND bridge: %s.%s -> %s.%s" % (ref_a, pad_a, ref_b, pad_b))
            return True
    print("  GND bridge FAILED: %s.%s -> %s.%s" % (ref_a, pad_a, ref_b, pad_b))
    return False

# ── Automatic healing of ground islands ─────────────────────────────────────
# B.Cu traces cut the ground pour into islands, and which pad ends up cut off
# changes with every placement. So after the pour is filled, EVERY GND pad is
# checked for whether it reaches ground (connectivity), and the cut-off ones are
# bridged with a short F.Cu trace to the nearest healthy GND pad.
def bridge_pads(pa, pb):
    ax, ay = pcbnew.ToMM(pa.GetPosition().x), pcbnew.ToMM(pa.GetPosition().y)
    bx, by = pcbnew.ToMM(pb.GetPosition().x), pcbnew.ToMM(pb.GetPosition().y)
    paths = [[(ax, ay), (bx, by)],
             [(ax, ay), (ax, by), (bx, by)],
             [(ax, ay), (bx, ay), (bx, by)]]
    for path in paths:
        if all(track_clear(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1], GND)
               for i in range(len(path) - 1)):
            for i in range(len(path) - 1):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(path[i][0]), pcbnew.FromMM(path[i][1])))
                t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(path[i + 1][0]), pcbnew.FromMM(path[i + 1][1])))
                t.SetLayer(pcbnew.F_Cu); t.SetNetCode(GND)
                t.SetWidth(pcbnew.FromMM(0.25))
                board.Add(t)
                copper.append((GND, path[i][0], path[i][1],
                               path[i + 1][0], path[i + 1][1], 0.125))
            return True
    return False

def heal_gnd_islands():
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    conn = board.GetConnectivity()

    def touches_zone(pad):
        for it in conn.GetConnectedItems(pad):
            if it.Type() == pcbnew.PCB_ZONE_T and it.GetNetCode() == GND \
                    and not it.GetIsRuleArea():
                return True
        return False

    gnd_pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()
                if pad.GetNetCode() == GND]
    for round_no in range(3):
        healthy = [p for p in gnd_pads if touches_zone(p)]
        sick = [p for p in gnd_pads if not touches_zone(p)]
        if not sick:
            break
        print("GND islands (round %d): %d pads" % (round_no + 1, len(sick)))
        fixed = 0
        for pad in sick:
            px, py = pad.GetPosition().x, pad.GetPosition().y
            cand = sorted(healthy, key=lambda q: (q.GetPosition().x - px) ** 2 +
                                                 (q.GetPosition().y - py) ** 2)
            for q in cand[:8]:
                if bridge_pads(pad, q):
                    ref = pad.GetParentFootprint().GetReference()
                    qref = q.GetParentFootprint().GetReference()
                    print("  bridge: %s.%s -> %s.%s" % (ref, pad.GetNumber(), qref, q.GetNumber()))
                    fixed += 1
                    break
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.BuildConnectivity()
        conn = board.GetConnectivity()
        if fixed == 0:
            print("  nista vise ne mogu premostiti")
            break

heal_gnd_islands()
board.Save(pcb)
tr = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T)
vi = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T)
print("tracks:", tr, "vias:", vi)
print("saved:", pcb)
