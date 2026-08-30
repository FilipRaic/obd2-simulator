# -*- coding: utf-8 -*-
"""Removal of dead trace leftovers.

WHY IT EXISTS. Freerouting and our own maze router occasionally leave a short
piece of track with one end touching nothing - usually on ground, less than a
millimetre long. It is electrically harmless, but DRC reports it as an
unconnected item, so it cannot be told apart from a genuine missing connection.

`heal_gnd_fragments.py` cleans up pour islands but not leftovers like these, so
the outcome of the chain came down to luck: the same placement gave 0 unconnected
items in one pass and 1 in the next. This is the same job KiCad's "Cleanup Tracks
and Vias" does, except it can be run from a script.

WHAT GETS DELETED. Only a track with AT LEAST ONE FREE END, that is one touching
neither another track of the same net on that layer, nor a via, nor a pad, nor
the filled pour of that net on that layer. Such a track cannot by definition be
part of any connection. The procedure repeats while there is anything left to
delete, because deleting one track frees the end of the next.

Running it (KiCad's Python, because of the pcbnew module):
    & "$k\\python.exe" scripts\\clean_dangling.py <board.kicad_pcb>
"""
import os
import sys

import pcbnew

PCB = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                 "obd2-simulator.kicad_pcb"))
TOL = pcbnew.FromMM(0.001)

board = pcbnew.LoadBoard(PCB)


def pt(v):
    return (v.x, v.y)


def near(a, b, tol=TOL):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def on_segment(p, a, b, halfwidth):
    """Lezi li tocka p na duzini a-b, s dopustenim odstupanjem halfwidth."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return near(p, a, halfwidth)
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / float(l2)
    t = max(0.0, min(1.0, t))
    qx, qy = ax + t * dx, ay + t * dy
    return (p[0] - qx) ** 2 + (p[1] - qy) ** 2 <= halfwidth * halfwidth


def endpoint_supported(track, p, tracks, vias, pads, zones):
    net = track.GetNetCode()
    lay = track.GetLayer()
    for other in tracks:
        if other is track or other.GetNetCode() != net:
            continue
        if other.GetLayer() != lay:
            continue
        if on_segment(p, pt(other.GetStart()), pt(other.GetEnd()),
                      other.GetWidth() / 2 + TOL):
            return True
    for v in vias:
        if v.GetNetCode() != net:
            continue
        if not v.IsOnLayer(lay):
            continue
        # KiCad 10: PCB_VIA.GetWidth() wants a layer as its argument, otherwise
        # it fails an assert. The per-layer via width is what matters here.
        try:
            vw = v.GetWidth(lay)
        except TypeError:
            vw = v.GetWidth()
        if near(p, pt(v.GetPosition()), vw / 2 + TOL):
            return True
    for pad in pads:
        if pad.GetNetCode() != net:
            continue
        if not pad.IsOnLayer(lay):
            continue
        if pad.HitTest(pcbnew.VECTOR2I(int(p[0]), int(p[1])), TOL):
            return True
    for z in zones:
        if z.GetNetCode() != net or z.GetIsRuleArea():
            continue
        if not z.IsOnLayer(lay):
            continue
        if z.HitTestFilledArea(lay, pcbnew.VECTOR2I(int(p[0]), int(p[1])), 0):
            return True
    return False


total = 0
for it in range(20):
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    pads = list(board.GetPads())
    zones = list(board.Zones())
    dead = []
    for t in tracks:
        a, b = pt(t.GetStart()), pt(t.GetEnd())
        if not endpoint_supported(t, a, tracks, vias, pads, zones) or \
           not endpoint_supported(t, b, tracks, vias, pads, zones):
            dead.append(t)
    if not dead:
        break
    for t in dead:
        net = t.GetNetname()
        ln = pcbnew.ToMM(t.GetLength())
        p = t.GetStart()
        print("  brisem ostatak: mreza %-8s duljina %.2f mm na (%.2f, %.2f)"
              % (net, ln, pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
        board.Delete(t)
    total += len(dead)

# ── Dead vias ───────────────────────────────────────────────────────────────
#
# A via is dead when NO layer has a track or a pad touching it, i.e. it only
# connects the pour to itself. Such a via is not stitching but a leftover: the
# router brought a track to it and later removed it.
#
# WHY THAT MATTERS. While such a via stands, KiCad considers the pour island
# around it connected (the via is a connection to the net) and does not remove
# it, even though the other side leads nowhere. The result is a floating piece of
# copper that DRC reports as an unconnected zone and that heal_gnd_fragments.py
# cannot bridge. Once the via is removed, the island is left without a single
# connection and the next zone fill removes it cleanly.
dead_vias = 0
for _ in range(5):
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    pads = list(board.GetPads())
    kill = []
    for v in vias:
        net = v.GetNetCode()
        p = pt(v.GetPosition())
        used = False
        for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
            if not v.IsOnLayer(lay):
                continue
            try:
                vw = v.GetWidth(lay)
            except TypeError:
                vw = v.GetWidth()
            for tr in tracks:
                if tr.GetNetCode() != net or tr.GetLayer() != lay:
                    continue
                if on_segment(p, pt(tr.GetStart()), pt(tr.GetEnd()),
                              tr.GetWidth() / 2 + vw / 2 + TOL):
                    used = True
                    break
            if used:
                break
            for pad in pads:
                if pad.GetNetCode() != net or not pad.IsOnLayer(lay):
                    continue
                if pad.HitTest(pcbnew.VECTOR2I(int(p[0]), int(p[1])), vw / 2 + TOL):
                    used = True
                    break
            if used:
                break
        if not used:
            kill.append(v)
    if not kill:
        break
    for v in kill:
        pp = v.GetPosition()
        print("  brisem mrtvu rupicu: mreza %-8s na (%.2f, %.2f)"
              % (v.GetNetname(), pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y)))
        board.Delete(v)
    dead_vias += len(kill)

if total or dead_vias:
    for z in board.Zones():
        if not z.GetIsRuleArea():
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.BuildListOfNets()
    flr = pcbnew.ZONE_FILLER(board)
    flr.Fill(board.Zones())
    board.Save(PCB)
    print("deleted: %d trace leftovers, %d dead vias; zones refilled, "
          "board saved" % (total, dead_vias))
else:
    print("no dead trace leftovers or vias")
