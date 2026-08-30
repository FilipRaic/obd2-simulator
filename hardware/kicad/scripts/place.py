# place.py - shelf placer: fixed items (module, edge connectors, UI column,
# mounting holes) are pinned, and everything else is packed into its zone with a
# raster search over a 0.5 mm occupancy grid using the footprint's real
# courtyard, so the result is overlap-free by construction.
import pcbnew

GAP = 0.8          # min gap between courtyards (mm)
CELL = 0.5
# These defaults are only a fallback - build_board.py passes the real dimensions
# to the constructor, so they are no longer tied to one board revision. They used
# to be hard-coded here, and enlarging the board would silently have no effect:
# the packer would still consider everything above y = 100 to be off the board.
BW, BH = 115.0, 100.0
EDGE = 1.0

class Placer:
    def __init__(self, bw=BW, bh=BH):
        self.bw, self.bh = float(bw), float(bh)
        self.nx = int(self.bw / CELL) + 1
        self.ny = int(self.bh / CELL) + 1
        self.occ = [[False] * self.ny for _ in range(self.nx)]
        # board edge margin
        for x in range(self.nx):
            for y in range(self.ny):
                mx, my = x * CELL, y * CELL
                if mx < EDGE or mx > self.bw - EDGE or my < EDGE or my > self.bh - EDGE:
                    self.occ[x][y] = True

    def block(self, x1, y1, x2, y2):
        for x in range(max(0, int(x1 / CELL)), min(self.nx - 1, int(x2 / CELL) + 1) + 1):
            for y in range(max(0, int(y1 / CELL)), min(self.ny - 1, int(y2 / CELL) + 1) + 1):
                self.occ[x][y] = True

    def free(self, x1, y1, x2, y2):
        if x1 < EDGE or y1 < EDGE or x2 > self.bw - EDGE or y2 > self.bh - EDGE:
            return False
        for x in range(max(0, int(x1 / CELL)), min(self.nx - 1, int(x2 / CELL) + 1) + 1):
            for y in range(max(0, int(y1 / CELL)), min(self.ny - 1, int(y2 / CELL) + 1) + 1):
                if self.occ[x][y]:
                    return False
        return True

    # A footprint's courtyard is not necessarily centred on its origin, so
    # every candidate position is tested with the courtyard's real offset:
    #   shape = (w, h, ox, oy)  - courtyard centre sits at origin + (ox, oy).
    def _rect(self, shape, cx, cy):
        w, h, ox, oy = shape
        gx, gy = w / 2 + GAP / 2, h / 2 + GAP / 2
        return (cx + ox - gx, cy + oy - gy, cx + ox + gx, cy + oy + gy)

    def place_near(self, shape, ax, ay, max_r=12.0, block=True):
        """Nearest free spot to (ax, ay) - for decoupling caps, crystal load
        caps and pull-ups, which must sit next to their device's pin.

        block=False only looks for a spot and does not reserve it. It serves a
        caller that tries the same part in several rotations before picking the
        best one: if every attempt reserved its spot immediately, the three
        rejected rotations would leave behind three occupied rectangles that
        nobody uses."""
        import math
        r = CELL
        while r <= max_r:
            steps = max(8, int(2 * math.pi * r / CELL))
            for i in range(steps):
                a = 2 * math.pi * i / steps
                cx, cy = ax + r * math.cos(a), ay + r * math.sin(a)
                rect = self._rect(shape, cx, cy)
                if self.free(*rect):
                    if block:
                        self.block(*rect)
                    return (cx, cy)
            r += CELL
        return None

    def place(self, shape, zone):
        """Find a free spot inside zone (x1,y1,x2,y2); returns origin (x, y)."""
        zx1, zy1, zx2, zy2 = zone
        w, h, ox, oy = shape
        gx, gy = w / 2 + GAP / 2, h / 2 + GAP / 2
        cy = zy1 + gy - oy
        while True:
            rect_y2 = cy + oy + gy
            if rect_y2 > zy2 + 1e-6:
                return None
            cx = zx1 + gx - ox
            while cx + ox + gx <= zx2 + 1e-6:
                rect = self._rect(shape, cx, cy)
                if self.free(*rect):
                    self.block(*rect)
                    return (cx, cy)
                cx += CELL
            cy += CELL

    def block_fp(self, shape, cx, cy):
        self.block(*self._rect(shape, cx, cy))
