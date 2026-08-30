# -*- coding: utf-8 -*-
"""Remove duplicated vias (same net, same place).

    python.exe dedup_vias.py <board.kicad_pcb>

WHY IT EXISTS. The ground repair is repeated over several rounds when needed
(`route_board.ps1`). Each round deals with its own leftovers, but
`heal_gnd_fragments.py` and `route_one_net.py` can pick the same bridging point
in two consecutive rounds, so TWO vias end up in the same spot. DRC reports that
as "drilled hole too close to other hole, actual 0.0000 mm", which sounds like a
serious geometry error and is in fact only a duplicate entry.

Electrically the surplus changes nothing (same net, same layer), so the second
and every further via at the same place is simply deleted.
"""
import pcbnew, sys

PCB = sys.argv[1]
board = pcbnew.LoadBoard(PCB)

# Threshold: vias of the same net whose centres are closer than "radius + radius
# + minimum permitted hole spacing" physically overlap or are too tight. They are
# not necessarily on the same coordinate - three repair rounds once left three
# vias within 0,2 mm, which DRC reports as a spacing of 0,0000 mm.
MIN_GAP = 0.25

vias = []
for t in list(board.GetTracks()):
    if t.Type() != pcbnew.PCB_VIA_T:
        continue
    p = t.GetPosition()
    vias.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                 pcbnew.ToMM(t.GetDrill()), t.GetNetCode(), t))

keep = []
dupes = []
for x, y, d, nc, t in vias:
    close = None
    for kx, ky, kd, knc in keep:
        if knc != nc:
            continue
        if ((x - kx) ** 2 + (y - ky) ** 2) ** 0.5 < (d + kd) / 2.0 + MIN_GAP:
            close = (kx, ky)
            break
    if close is None:
        keep.append((x, y, d, nc))
    else:
        dupes.append((x, y, nc, close, t))

for _, _, _, _, t in dupes:
    board.Delete(t)

for x, y, nc, close, _ in dupes:
    net = board.FindNet(nc)
    print("  redundant via at (%.3f, %.3f) net %s, overlaps the one at (%.3f, %.3f) - deleted"
          % (x, y, net.GetNetname() if net else nc, close[0], close[1]))

# ── duplicated segments ──────────────────────────────────────────────────────
# `route_can_chain.py` finishes every link of the chain with a short stub to the
# pad centre. On a pad that is simultaneously the end of one link and the start
# of the next, that stub is written TWICE, so the net looks as if it branches
# even though it is the same 0,01 to 0,11 mm trace. The same happens when two
# ground repair rounds lay the same bridge.
seen = set()
seg_dupes = []
for t in list(board.GetTracks()):
    if t.Type() == pcbnew.PCB_VIA_T:
        continue
    a = (round(pcbnew.ToMM(t.GetStart().x), 4), round(pcbnew.ToMM(t.GetStart().y), 4))
    b = (round(pcbnew.ToMM(t.GetEnd().x), 4), round(pcbnew.ToMM(t.GetEnd().y), 4))
    key = (min(a, b), max(a, b), t.GetLayer(), t.GetNetCode())
    if key in seen:
        seg_dupes.append(t)
    else:
        seen.add(key)

for t in seg_dupes:
    board.Delete(t)

if dupes or seg_dupes:
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    print("deleted: %d duplicate vias, %d duplicate segments; zones refilled"
          % (len(dupes), len(seg_dupes)))
else:
    print("no duplicate vias or segments")
