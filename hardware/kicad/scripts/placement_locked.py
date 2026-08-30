# -*- coding: utf-8 -*-
"""Frozen board placement.

CURRENT STATE: LOCKED is EMPTY, so the placement is computed by the packer again.

WHY IT WAS EMPTIED. On the earlier 115 x 100 mm outline this file held a complete
list of coordinates taken from the last routed board. It came about because at
that size the packer was overloaded: every new part shifted a neighbour, that
neighbour shifted the next one, and the routing failed. Freezing sidestepped the
problem, but it also cemented everything the design review lists as bad:

  * bootstrap capacitors 14 to 16 mm from their pins (C21, C29),
  * C7 seventeen millimetres from OSC2,
  * the ESD diode D1 nineteen millimetres behind the OBD connector,
  * the module's decoupling capacitors fourteen and eighteen millimetres from
    pin 2.

The intent behind NEAR_OF in build_board.py was exactly the opposite, but LOCKED
overrode NEAR_OF, so that intent never reached the board.

At 130 x 115 mm the packer has room, so LOCKED is no longer used and NEAR_OF
decides again. If the placement ever settles and freezing it becomes desirable,
the coordinates are printed from the finished board and put back here. Formally:
the key is the reference designator, the value is (x, y, rotation) in local mm
with the origin at the bottom left corner of the board.
"""

LOCKED = {}
