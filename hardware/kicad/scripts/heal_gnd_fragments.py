# -*- coding: utf-8 -*-
"""Locate any remaining GND pour fragment and try to join it to the main one:
a pair of vias (one in the fragment, one in the main pour) + a short F.Cu trace."""
import os
import pcbnew, math

# THE PATH IS NO LONGER HARD-CODED. It used to be, and it pointed at a different
# board directory, so running the script from here silently repaired the ground
# of SOMEBODY ELSE'S board: the routing chain reported that everything had been
# bridged while the board being built stayed unchanged. Now it takes an argument,
# and if there is none, the board from the directory the script lives in.
import sys as _sys
PCB = _sys.argv[1] if len(_sys.argv) > 1 else os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                 "obd2-simulator.kicad_pcb"))
board = pcbnew.LoadBoard(PCB)
GND = board.GetNetsByName()["GND"].GetNetCode()

def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / float(dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

copper = {pcbnew.F_Cu: [], pcbnew.B_Cu: []}
holes = []
for t in board.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        p = t.GetPosition()
        holes.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
        for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
            copper[lay].append((t.GetNetCode(), pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                                pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), 0.3))
    elif t.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
        a, b = t.GetStart(), t.GetEnd()
        copper[t.GetLayer()].append((t.GetNetCode(), pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                                     pcbnew.ToMM(b.x), pcbnew.ToMM(b.y),
                                     pcbnew.ToMM(t.GetWidth()) / 2))
for fp in board.GetFootprints():
    for pad in fp.Pads():
        p, s = pad.GetPosition(), pad.GetSize()
        r = max(pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)) / 2
        if pad.GetDrillSize().x > 0:
            holes.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
        for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
            if pad.GetLayerSet().Contains(lay):
                copper[lay].append((pad.GetNetCode(), pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                                    pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), r))

def track_clear(x1, y1, x2, y2, lay):
    steps = max(2, int(math.hypot(x2 - x1, y2 - y1) / 0.1))
    for i in range(steps + 1):
        x = x1 + (x2 - x1) * i / steps
        y = y1 + (y2 - y1) * i / steps
        # The TRACE has to avoid the keep-out area too, not just the via.
        # Without this check the bridge between ground fragments crossed the
        # antenna keep-out and DRC reported it as items_not_allowed.
        for (kx1, ky1, kx2, ky2) in keepout_boxes:
            if kx1 <= x <= kx2 and ky1 <= y <= ky2:
                return False
        for (n, ax, ay, bx, by, hw) in copper[lay]:
            if n == GND:
                continue
            if seg_dist(x, y, ax, ay, bx, by) < 0.125 + hw + 0.3:
                return False
    return True

# Zone zabrane (keepout antene) ne smiju dobiti rupicu - DRC to prijavljuje
# kao items_not_allowed. Uzima se obuhvat zone prosiren za 0,8 mm.
keepout_boxes = []
for _z in board.Zones():
    if _z.GetIsRuleArea():
        _bb = _z.GetBoundingBox()
        keepout_boxes.append((pcbnew.ToMM(_bb.GetX()) - 0.8,
                              pcbnew.ToMM(_bb.GetY()) - 0.8,
                              pcbnew.ToMM(_bb.GetX() + _bb.GetWidth()) + 0.8,
                              pcbnew.ToMM(_bb.GetY() + _bb.GetHeight()) + 0.8))

def via_fits(x, y):
    for (kx1, ky1, kx2, ky2) in keepout_boxes:
        if kx1 <= x <= kx2 and ky1 <= y <= ky2:
            return False
    for (hx, hy) in holes:
        if math.hypot(x - hx, y - hy) < 0.9:
            return False
    for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
        for (n, ax, ay, bx, by, hw) in copper[lay]:
            if n == GND:
                continue
            if seg_dist(x, y, ax, ay, bx, by) < 0.3 + hw + 0.3:
                return False
    return True

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
gz = [z for z in board.Zones() if z.GetNetCode() == GND and not z.GetIsRuleArea()][0]
polys = gz.GetFilledPolysList(pcbnew.B_Cu)
frag = []
for i in range(polys.OutlineCount()):
    ch = polys.Outline(i)
    bb = ch.BBox()
    frag.append((ch.Area(), i, bb))
frag.sort(reverse=True)
main_idx = frag[0][1]
print("fragments:")
for a, i, bb in frag:
    print("  idx %d area %.0f mm2  bbox x %.1f..%.1f y %.1f..%.1f" %
          (i, a / 1e12, pcbnew.ToMM(bb.GetX()) - 50, pcbnew.ToMM(bb.GetX() + bb.GetWidth()) - 50,
           130 - pcbnew.ToMM(bb.GetY() + bb.GetHeight()), 130 - pcbnew.ToMM(bb.GetY())))

def add_track(x1, y1, x2, y2, lay):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
    t.SetLayer(lay); t.SetNetCode(GND)
    t.SetWidth(pcbnew.FromMM(0.25))
    board.Add(t)

def add_via(x, y):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    v.SetDrill(pcbnew.FromMM(0.3)); v.SetWidth(pcbnew.FromMM(0.6))
    v.SetNetCode(GND); v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(v)

# sekundarni fragmenti: nadji tocku u fragmentu i tocku u glavnom, obje
# prohodne za rupicu, spojene kratkom cistom F.Cu trasom.
import itertools
ok_all = True
for a, idx, bb in frag[1:]:
    x0 = pcbnew.ToMM(bb.GetX()); x1 = pcbnew.ToMM(bb.GetX() + bb.GetWidth())
    y0 = pcbnew.ToMM(bb.GetY()); y1 = pcbnew.ToMM(bb.GetY() + bb.GetHeight())
    done = False
    xs = [x0 + (x1 - x0) * t / 8.0 for t in range(9)]
    ys = [y0 + (y1 - y0) * t / 8.0 for t in range(9)]
    for fx, fy in itertools.product(xs, ys):
        pf = pcbnew.VECTOR2I(pcbnew.FromMM(fx), pcbnew.FromMM(fy))
        if not polys.Contains(pf, idx) or not via_fits(fx, fy):
            continue
        # trazi tocku glavnog fragmenta u okolici
        r = 1.5
        while r <= 14.0 and not done:
            for k in range(24):
                ang = k * math.pi / 12
                mx, my = fx + r * math.cos(ang), fy + r * math.sin(ang)
                pm = pcbnew.VECTOR2I(pcbnew.FromMM(mx), pcbnew.FromMM(my))
                if not polys.Contains(pm, main_idx) or not via_fits(mx, my):
                    continue
                if track_clear(fx, fy, mx, my, pcbnew.F_Cu):
                    add_via(fx, fy); add_via(mx, my)
                    add_track(fx, fy, mx, my, pcbnew.F_Cu)
                    print("fragment %d spojen: (%.1f,%.1f) -> (%.1f,%.1f)" %
                          (idx, fx - 50, 130 - fy, mx - 50, 130 - my))
                    done = True
                    break
                # 05.08.2026.: ako ravan potez ne prolazi, probaj most u obliku
                # slova L preko jednog od dva kutna cvora. Uz modul U6 je pojas
                # poligona toliko uzak da ravna crta uvijek negdje zapne, a
                # zaobilazak u dva poteza prolazi.
                for cx, cy in ((fx, my), (mx, fy)):
                    if (track_clear(fx, fy, cx, cy, pcbnew.F_Cu) and
                            track_clear(cx, cy, mx, my, pcbnew.F_Cu)):
                        add_via(fx, fy); add_via(mx, my)
                        add_track(fx, fy, cx, cy, pcbnew.F_Cu)
                        add_track(cx, cy, mx, my, pcbnew.F_Cu)
                        print("fragment %d spojen preko kuta: (%.1f,%.1f) -> "
                              "(%.1f,%.1f) -> (%.1f,%.1f)" %
                              (idx, fx - 50, 130 - fy, cx - 50, 130 - cy,
                               mx - 50, 130 - my))
                        done = True
                        break
                if done:
                    break
            r += 0.5
        if done:
            break
    # Narrow tongues of the pour (under 1 mm wide) cannot take a via, so an F.Cu
    # bridge does not exist for them. Those are joined with a TRACE ON B.Cu: a
    # 0,2 mm trace fits even such a tongue, and when it is on the same net as the
    # pour, the fill joins them. Cutting such a patch away is NOT a solution -
    # tried and rejected, because the grounds of capacitors C24 and C26 are
    # connected through it.
    if not done:
        fine = 25
        xs2 = [x0 + (x1 - x0) * t / (fine - 1.0) for t in range(fine)]
        ys2 = [y0 + (y1 - y0) * t / (fine - 1.0) for t in range(fine)]
        for fx, fy in itertools.product(xs2, ys2):
            pf = pcbnew.VECTOR2I(pcbnew.FromMM(fx), pcbnew.FromMM(fy))
            if not polys.Contains(pf, idx):
                continue
            r = 0.5
            while r <= 12.0 and not done:
                for k in range(48):
                    ang = k * math.pi / 24
                    mx, my = fx + r * math.cos(ang), fy + r * math.sin(ang)
                    pm = pcbnew.VECTOR2I(pcbnew.FromMM(mx), pcbnew.FromMM(my))
                    if not polys.Contains(pm, main_idx):
                        continue
                    if track_clear(fx, fy, mx, my, pcbnew.B_Cu):
                        add_track(fx, fy, mx, my, pcbnew.B_Cu)
                        print("fragment %d spojen trasom po B.Cu: (%.1f,%.1f) "
                              "-> (%.1f,%.1f)" %
                              (idx, fx - 50, 130 - fy, mx - 50, 130 - my))
                        done = True
                        break
                    for cx, cy in ((fx, my), (mx, fy)):
                        if (track_clear(fx, fy, cx, cy, pcbnew.B_Cu) and
                                track_clear(cx, cy, mx, my, pcbnew.B_Cu)):
                            add_track(fx, fy, cx, cy, pcbnew.B_Cu)
                            add_track(cx, cy, mx, my, pcbnew.B_Cu)
                            print("fragment %d spojen trasom po B.Cu preko "
                                  "kuta: (%.1f,%.1f) -> (%.1f,%.1f)" %
                                  (idx, fx - 50, 130 - fy, mx - 50, 130 - my))
                            done = True
                            break
                    if done:
                        break
                r += 0.5
            if done:
                break

    # Last line of defence: if a tongue cannot be joined on either layer, its pads
    # stay attached only to it, i.e. practically without a ground. Each such pad
    # is then connected straight to the main pour: a via in the main pour near the
    # pad and a short F.Cu trace to it.
    if not done:
        rescued = 0
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetCode() != GND:
                    continue
                px = pcbnew.ToMM(pad.GetPosition().x)
                py = pcbnew.ToMM(pad.GetPosition().y)
                pp = pcbnew.VECTOR2I(pcbnew.FromMM(px), pcbnew.FromMM(py))
                if not polys.Contains(pp, idx):
                    continue
                fixed = False
                r = 1.0
                while r <= 12.0 and not fixed:
                    for k in range(48):
                        ang = k * math.pi / 24
                        mx, my = px + r * math.cos(ang), py + r * math.sin(ang)
                        pm = pcbnew.VECTOR2I(pcbnew.FromMM(mx), pcbnew.FromMM(my))
                        if not polys.Contains(pm, main_idx) or not via_fits(mx, my):
                            continue
                        if track_clear(px, py, mx, my, pcbnew.F_Cu):
                            add_via(mx, my)
                            add_track(px, py, mx, my, pcbnew.F_Cu)
                            print("  pad %s.%s from fragment %d joined to the "
                                  "main pour: (%.1f,%.1f) -> (%.1f,%.1f)" %
                                  (fp.GetReference(), pad.GetNumber(), idx,
                                   px - 50, 130 - py, mx - 50, 130 - my))
                            rescued += 1
                            fixed = True
                            break
                    r += 0.5
                if not fixed:
                    print("  pad %s.%s from fragment %d NOT joined" %
                          (fp.GetReference(), pad.GetNumber(), idx))
        print("fragment %d: the tongue was not bridged, but %d pads were joined"
              % (idx, rescued))
        ok_all = False

# ── Cleanup after routing ───────────────────────────────────────────────────
# This is done ONLY NOW, after the Specctra export and the routing, so it cannot
# influence the router's result (enabling island removal in build_board.py
# changes the .dsn and breaks the routing - tried and rejected).
#
# 1) Ground pour: delete any remaining floating copper patches that touch neither
#    a pad nor a via. They are electrically useless and DRC reports them.
for z in board.Zones():
    if z.GetNetCode() == GND and not z.GetIsRuleArea():
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())

# 2) Dead ground-trace leftovers: the router can leave a short piece that leads
#    nowhere. Everything not connected to a pad, a via or the pour is deleted (in
#    several passes, because one leftover can hang off another).
for _round in range(4):
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    dead = []
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_TRACE_T or t.GetNetCode() != GND:
            continue
        anchored = False
        for it in conn.GetConnectedItems(t):
            if it.Type() in (pcbnew.PCB_PAD_T, pcbnew.PCB_VIA_T, pcbnew.PCB_ZONE_T):
                anchored = True
                break
        if not anchored:
            dead.append(t)
    if not dead:
        break
    for t in dead:
        board.Remove(t)
    print("obrisano mrtvih GND ostataka: %d" % len(dead))

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.Save(PCB)
print("spremljeno (svi fragmenti premosteni: %s)" % ok_all)
