import pcbnew, io, sys

pcb, dsn = sys.argv[1], sys.argv[2]

# Nets whose already laid copper is KEPT and handed to Freerouting as a fixed
# obstacle. Everything else is deleted, because Freerouting routes from scratch.
#
# The CAN pair is routed BEFORE Freerouting (route_can_chain.py), on a still
# empty board, where the top layer is free and the chain fits without a single
# via. Routed afterwards it would have to thread through 800 already laid
# segments, and by then no top-layer path exists at all - this was tried, and two
# of the eight links of the chain failed to get through.
KEEP_NETS = ("CANH", "CANL")

board = pcbnew.LoadBoard(pcb)
kept = 0
for t in list(board.GetTracks()):
    if t.GetNetname() in KEEP_NETS:
        kept += 1
        continue
    board.Delete(t)
board.Save(pcb)
ok = pcbnew.ExportSpecctraDSN(board, dsn)
print("DSN export:", ok, "->", dsn, "(kept %d segments: %s)"
      % (kept, ", ".join(KEEP_NETS)))

# KiCad writes every track as "(type route)", which Freerouting is allowed to rip
# up and lay again. For the nets in KEEP_NETS that becomes "(type protect)",
# making them immovable: the router sees them as an obstacle and routes around.
#
# DELETING THE PIN LISTS of those nets was tried and REJECTED. The idea was that
# a net without pins has nothing to connect, so Freerouting would not lay its own
# trace alongside the protected chain. The effect was the opposite: the router
# got lost, laid 91 segments on CANH instead of 42, and the whole board ended up
# with 37 unconnected items and 3 violations instead of 5 and 5.
# Only "protect" remains, and the excess copper is removed afterwards, in
# route_can_chain.py --replay.
if ok and kept:
    with io.open(dsn, encoding="utf-8") as fh:
        txt = fh.read()
    n = 0
    for net in KEEP_NETS:
        needle = "(net %s)(type route)" % net
        n += txt.count(needle)
        txt = txt.replace(needle, "(net %s)(type protect)" % net)
    with io.open(dsn, "w", encoding="utf-8") as fh:
        fh.write(txt)
    print("tracks protected in the DSN:", n)
