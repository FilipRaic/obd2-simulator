# build_board.py - generator of the OBD-II simulator board, revision v0.7
# (final). Running it rebuilds the whole .kicad_pcb from scratch: nets,
# footprints, placement, zones and silkscreen. Anything adjusted by hand in
# KiCad is lost on the next run, so every deliberate change has to end up here.
#
# What this revision carries over from the earlier prototypes:
#   1. J4 USB-A rotated so the opening faces outward past the board edge.
#   2. J2 = SEP-A-OBD-D2 mounted directly on the board (own footprint), on the
#      board perimeter rather than underneath the display.
#   3. SW6 rotated by 45 degrees, so the stick directions become up/down/
#      left/right instead of diagonals.
#   4. ALL passives (resistors, capacitors, inductors) are THT. Only the
#      integrated circuits, the module, the fuse and the TVS stay SMD, because
#      hand-soldering those packages is still practical.
#   5. D2 POLARITY FIXED. The first prototype wired the TVS with its cathode to
#      ground and its anode to +12 V, which conducts in the forward direction
#      and effectively shorts the 12 V branch. Now the cathode (pad 1) is on
#      OBD_12V and the anode (pad 2) on ground.
#   6. The rotary potentiometer RV1 was replaced by the incremental encoder
#      ENC1 (EN11-HSB1AQ20): digital relative steps instead of an absolute
#      analogue position.
#
# Board coordinates: mm, origin = board lower-left corner (like the tech
# drawing). KiCad Y grows downward, so y_k = OY - y.
import pcbnew, io, os, sys

KICAD_SHARE = os.environ["KICAD_SHARE"]
FP_ROOT = os.path.join(KICAD_SHARE, "footprints")
# CH224K's ESSOP-10 has no match in the stock libraries, so it lives here,
# together with the redesign's SEP-A-OBD-D2 and RK12L12C0A0G footprints.
LOCAL_FP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "footprints"))
OUT = sys.argv[1]

OX, OY = 50.0, 130.0          # board (0,0) in KiCad sheet coords
# 130 x 115 mm. The size is deliberately generous: every passive is THT and a
# THT pad blocks BOTH layers, so on a smaller board the two-layer autorouter
# runs out of corridors (at 100 x 80 and 100 x 90 at least one net always
# failed). An intermediate 115 x 100 attempt held 78 footprints, but the design
# review then asked for 17 more (8 test points, 2 series resistors on SPI,
# 3 pull-ups and 3 capacitors on the encoder, a blocking diode in the 12 V
# branch) plus tighter grouping of about fifteen existing parts around their
# chips. That does not fit, and squeezing it was tried on 2026-08-04 and
# REJECTED - the packer reshuffled half the board and 9 nets failed to route.
#
# Perimeter layout:
#   top edge     y 99..115 : OBD connector (left) and USB-C (right) - both
#                            connectors on the SAME side, as requested
#   left/middle  y 50..99  : CAN section (next to OBD) and power section
#                            (next to USB-C)
#   middle       y 20..50  : ESP32-S3 module, display header, flash
#   bottom edge  y 0..20   : USB-A and the USB switching parts
#   right edge   x 112..119: user interface, all on ONE vertical axis
#
# Space is added by moving the EDGE-ANCHORED GROUPS out to the new edge while
# everything else stays put. That opens two free bands the packer fills with the
# new parts:
#   * vertical band   x = 96..111 (the interface moved from x 97..104 to 112..119)
#   * horizontal band y = 84..99  (the top edge moved from y 84..100 to 99..115)
W, H = 130.0, 115.0
# Offsets of the edge-anchored groups, so the coordinates in the table below can
# be read as "how far from its own edge" instead of absolute numbers that would
# have to be recomputed by hand.
DX_RIGHT = 15.0      # everything aligned to the RIGHT edge
DY_TOP = 15.0        # everything aligned to the TOP edge

def P(x, y):
    return pcbnew.VECTOR2I_MM(OX + x, OY - y)

board = pcbnew.CreateEmptyBoard()

# ── Nets ─────────────────────────────────────────────────────────────────────
NET_NAMES = [
    "GND", "+3V3", "VBUS", "OBD_12V", "VBUS_STICK",
    "SW_3V3", "FB_3V3", "BST_3V3",
    # FB_MID: the junction between R17A (15 k) and R17B (470 R). The lower leg
    # of the 3,3 V feedback divider is made of two series resistors, because the
    # E96 value 15,4 k is not obtainable in a THT package.
    "FB_MID",
    # VBUS carries whatever the CH224K negotiated: 5 V at plug-in, 12 V once the
    # PD contract is up. It feeds the 3,3 V buck and, through F1/D2, pin 16 of
    # the J1962F connector, so the diagnostic tool is powered as it is in a car.
    "PD_VDD", "PD_SENSE", "PD_CFG1",
    "CANH", "CANL", "CAN_TX", "CAN_RX", "XTAL1", "XTAL2",
    # SCK_MCU / MOSI_MCU: the stub between the microcontroller pin and the series
    # resistor (R30, R31). Past the resistor lies the SCK / MOSI bus carrying
    # U4, U7 and J5. The split was introduced because the bus is about 100 mm
    # long with three loads and had no termination at all.
    "SCK_MCU", "MOSI_MCU",
    # FUSED_12V: between the fuse F1 and the blocking diode D3. F1 used to feed
    # OBD_12V directly, so external 12 V could travel back into VBUS.
    "FUSED_12V",
    "SCK", "MOSI", "MISO", "CS_CAN", "INT_CAN",
    "CS_TFT", "TFT_DC", "TFT_RST", "TFT_LED", "CS_FLASH",
    "USB_SEL", "USB_HOST_EN", "USB_DP", "USB_DM",
    "USBC_DP", "USBC_DM", "USBA_DP", "USBA_DM", "CC1", "CC2",
    # JOY_XB/JOY_YB: the "far" contact of each SW6 axis reaches its ADC net
    # through a 10 k ladder resistor, so the firmware sees three levels
    # (idle 3,3 V / ladder ~1,96 V / direct 0 V) on JOY_X and JOY_Y.
    # ENC_A/ENC_B: the quadrature outputs of the incremental encoder ENC1,
    # ENC_SW is its built-in push-button. They replaced the POT net of the
    # former potentiometer RV1, and ENC_A took over GPIO1, that is the existing
    # potentiometer trace.
    "ENC_A", "ENC_B", "ENC_SW",
    # ENC_*_RAW: the stub from the encoder contact itself to the series resistor
    # R38-R40 (100 R). Without it the filter capacitor hangs directly on the
    # contact and discharges through it on every closure with no current limit
    # whatsoever. See the comment next to R38.
    "ENC_A_RAW", "ENC_B_RAW", "ENC_SW_RAW",
    "JOY_X", "JOY_Y", "JOY_SW", "JOY_XB", "JOY_YB",
    "BTN_CONFIRM", "BTN_CLEAR", "BTN_RETURN",
    "MCU_EN", "TXD0", "RXD0", "ISET", "BOOT",
    # 12 V -> 5 V buck for the USB stick (U11): VBUS is 12 V after the PD
    # contract, and the SY6280 (5,5 V abs max) plus the stick itself need 5 V.
    "V5_STICK", "SW_5V", "FB_5V", "BST_5V",
]
nets = {}
for name in NET_NAMES:
    ni = pcbnew.NETINFO_ITEM(board, name)
    board.Add(ni)
    nets[name] = ni

# ── THT footprints used for every passive ────────────────────────────────────
# Resistors lie FLAT on the board (classic mounting): 10,16 mm pitch, DIN0207
# body (6,3 x 2,5 mm), i.e. a standard 1/4 W resistor. That pitch also accepts
# smaller bodies (DIN0204), because the leads can always be bent wider, so the
# choice is deliberately the "large common denominator". Vertical mounting
# (2,54 mm pitch) saves about 590 mm2 across 21 resistors but is harder to
# hand-solder - that was the only reason it used to be vertical, so it was
# dropped.
R_THT  = ("Resistor_THT",  "R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal")
# EXCEPTION: R38-R40, the series resistors in the encoder filter, stand VERTICAL
# on a 5,08 mm pitch. That is the only departure from flat mounting on the whole
# board and it comes from necessity, not from saving space. Those three
# resistors have to sit right at the encoder contact, and the column along the
# right edge already carries the encoder, the 5-way switch, three push-buttons
# and nine pull-ups. With the 10,16 mm flat footprint those three parts ate the
# best spots, so the filter capacitors C32/C33 ended up 15 to 16 mm from their
# contact and the pull-ups R33/R34 22 to 26 mm away - the new part would have
# ruined the very thing the filter was added for.
R_VERT = ("Resistor_THT",  "R_Axial_DIN0207_L6.3mm_D2.5mm_P5.08mm_Vertical")
# SOURCING: locally, ceramic capacitors are sold on a 5 mm pitch ("RM 5MM"), so
# every disc capacitor moved from 2,5 mm to 5 mm. Without that the purchased
# part would not fit the board at all.
C_TINY = ("Capacitor_THT", "C_Disc_D4.3mm_W1.9mm_P5.00mm")     # 22 pF
C_SM   = ("Capacitor_THT", "C_Disc_D5.0mm_W2.5mm_P5.00mm")     # 100 nF
C_MED  = ("Capacitor_THT", "C_Disc_D6.0mm_W2.5mm_P5.00mm")     # 1 uF
CP_10  = ("Capacitor_THT", "CP_Radial_D5.0mm_P2.00mm")         # 10 uF electrolytic
CP_100 = ("Capacitor_THT", "CP_Radial_D6.3mm_P2.50mm")         # 100 uF electrolytic
# CP_LOWESR: the package for the 22 uF input and output capacitors of both
# converters. Sized for a solid polymer part, 6,3 mm diameter on a 2,5 mm pitch,
# i.e. the same footprint as the input bulk C1.
# WHAT THE PART HAS TO BE. The TPS562201 datasheet (SLVSD91D, section 7.2.2.3)
# says literally "intended for use with ceramic or other low-ESR capacitors,
# recommended values range from 20 uF to 68 uF", and for the input (7.2.2.4)
# "TI recommends a ceramic capacitor over 10 uF". The criterion is therefore
# IMPEDANCE, not chemistry:
#     ESR at 100 kHz <= 0,15 ohm    ripple current rating >= 0,35 A rms
# Ripple through these parts is 0,88 A peak-to-peak on the 3,3 V rail and 1,07 A
# on the 5 V rail, so 0,15 ohm keeps the output ripple at 130 to 160 mV, which
# leaves the ESP32-S3 (3,0 - 3,6 V) and the flash (2,7 - 3,6 V) comfortable.
# A solid polymer part (20 - 50 mohm) meets it with room to spare. A LOW-ESR /
# low-impedance electrolytic of the same value also meets it and is what this
# build uses, since those were already purchased. A PLAIN electrolytic does not:
# about 1 ohm puts the ripple near 0,9 V, outside both chips' supply range, and
# its ripple current rating of 100 - 200 mA is below the 0,25 - 0,31 A rms that
# actually flows.
# A Ø5 mm / 2,0 mm-pitch part fits this Ø6,3 mm / 2,5 mm footprint: the 0,80 mm
# holes swallow most of the 0,25 mm per-lead offset and the rest is a light
# splay. Body clearance is ample, the courtyard is 6,9 mm.
CP_LOWESR = ("Capacitor_THT", "CP_Radial_D6.3mm_P2.50mm")      # 22 uF low-ESR
# Inductors are RADIAL, which is what the part actually bought on 10.08.2026. is:
# 4,7 uH, 4,3 A, 30 mohm, body Ø8,5 x 11 mm, lead pitch 5,0 mm.
#
# HISTORY OF THIS LINE. It first drew an axial body of Ø5,0 mm, then Ø7,5 mm on
# 09.08.2026. because the BOM asked for a part with a body up to 9 mm and the
# courtyard was smaller than the real part, so DRC could not report a clash with
# a neighbour - the same class of mistake as the U6 module extent. Both of those
# were axial footprints mounted VERTICALLY (one lead bent up), which is not how a
# radial part sits: the radial body is centred BETWEEN the two holes, not over
# one of them, so the axial footprint drew the body in the wrong place as well as
# the wrong size.
#
# WHY THIS ONE. L_Radial_D8.7mm_P5.00mm_Fastron_07HCP draws Ø8,7 mm centred
# between the holes, i.e. slightly larger than the Ø8,5 mm part, so the courtyard
# is conservative. Pitch goes 5,08 -> 5,00 mm, which is the real part's pitch;
# the pad is Ø2,6 mm over a Ø1,3 mm hole, so a 0,6 to 0,8 mm lead drops straight
# in. Clearance was measured on the routed board before the swap: from the body
# centre to the nearest neighbouring pad edge 5,64 mm at L2 (U11 pin 3) and
# 6,19 mm at L3 (R24 pad 2), against a body radius of 4,25 mm.
L_THT  = ("Inductor_THT",  "L_Radial_D8.7mm_P5.00mm_Fastron_07HCP")

# ── Component table ──────────────────────────────────────────────────────────
# (ref, lib, footprint, x, y, rot_deg, value, {pad: net})
G, V3, VB = "GND", "+3V3", "VBUS"
COMPONENTS = [
    # MCU module - antenna toward the right edge, as documented (rev. v0.2+).
    #
    # TRADE-OFF: the KiCad footprint carries Espressif's full RF keep-out
    # (~21 x 48 mm), which on this 100 x 80 panel would sit exactly between
    # the MCU and the UI column at the right edge - no display or UI signal
    # could cross it. The project documentation specifies a 3-5 mm copper
    # keep-out (table 5 / ch. 6.1), so that is what the board implements. The
    # footprint's rule area is removed below. The firmware does not use
    # Wi-Fi/BLE. If radio is ever needed, the module must be moved to a board
    # edge with the antenna overhanging it.
    # Pin numbers per the ESP32-S3-WROOM-1 datasheet v1.8, table 3-1, mapped
    # to the GPIOs the firmware actually configures (firmware/include/
    # pins_custom_s3.h). Module pin -> GPIO:
    #   4=IO4  5=IO5  6=IO6  7=IO7  8=IO15 9=IO16 10=IO17 12=IO8
    #   13=IO19(USB D-) 14=IO20(USB D+) 17=IO9 18=IO10 19=IO11 20=IO12
    #   21=IO13 22=IO14 23=IO21 24=IO47 27=IO0(BOOT) 36=RXD0 37=TXD0
    #   38=IO2 39=IO1
    ("U6", "RF_Module", "ESP32-S3-WROOM-1", 38, 36,
     float(os.environ.get("U6_ROT", "-90")), "ESP32-S3-WROOM-1", {
        "1": G, "2": V3, "3": "MCU_EN",
        "4":  "JOY_Y",        # IO4  - ADC1_CH3
        "5":  "JOY_SW",       # IO5
        "6":  "BTN_CONFIRM",  # IO6
        "7":  "BTN_CLEAR",    # IO7
        "8":  "CS_FLASH",     # IO15
        "9":  "USB_SEL",      # IO16
        "10": "USB_HOST_EN",  # IO17
        "12": "BTN_RETURN",   # IO8
        "13": "USB_DM",       # IO19 - USB D-
        "14": "USB_DP",       # IO20 - USB D+
        "17": "INT_CAN",      # IO9
        "18": "CS_CAN",       # IO10
        "19": "MOSI_MCU",     # IO11 - FSPID,   via R31 (33 R) to MOSI
        "20": "SCK_MCU",      # IO12 - FSPICLK, via R30 (33 R) to SCK
        "21": "MISO",         # IO13 - FSPIQ
        "22": "CS_TFT",       # IO14
        "23": "TFT_DC",       # IO21
        "24": "TFT_RST",      # IO47
        "27": "BOOT",         # IO0 - strapping pin, download-mode button
        "36": "RXD0", "37": "TXD0",
        "38": "JOY_X",        # IO2 - ADC1_CH1
        "31": "ENC_B",        # IO38 - encoder, channel B
        "32": "ENC_SW",       # IO39 - encoder push-button
        "39": "ENC_A",        # IO1  - encoder, channel A (former POT line)
        "40": G, "41": G,     # GND + thermal pad
    }),
    # ── CAN (left edge) ──
    ("U4", "Package_SO", "SOIC-18W_7.5x11.6mm_P1.27mm", 13, 46, 90, "MCP2515-I/SO", {
        "1": "CAN_TX", "2": "CAN_RX", "4": V3, "5": V3, "6": V3,
        "7": "XTAL2", "8": "XTAL1", "9": G, "12": "INT_CAN",
        "13": "SCK", "14": "MOSI", "15": "MISO", "16": "CS_CAN",
        "17": V3, "18": V3,
    }),
    ("Y1", "Crystal", "Crystal_HC49-U_Vertical", 23, 50, 90, "8MHz", {"1": "XTAL1", "2": "XTAL2"}),
    ("C6", "Capacitor_THT", C_TINY[1], 24, 53, 0, "22pF", {"1": "XTAL1", "2": G}),
    ("C7", "Capacitor_THT", C_TINY[1], 24, 47, 0, "22pF", {"1": "XTAL2", "2": G}),
    # SN65HVD230DR replaced the obsolete MCP2551-I/SN (18.07.2026.): same
    # SOIC-8 pinout (TXD/GND/VCC/RXD/Vref/CANL/CANH/RS), RS to GND is
    # high-speed mode on both, and the HVD230 is a native 3,3 V part - the
    # MCP2551 wanted 4,5-5,5 V and was being run out of spec on this rail.
    ("U5", "Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", 13, 33, 90, "SN65HVD230DR", {
        "1": "CAN_TX", "2": G, "3": V3, "4": "CAN_RX",
        "6": "CANL", "7": "CANH", "8": G,
    }),
    # Termination and ESD now sit right at the OBD connector (NEAR_OF J2 pin 6),
    # so the CAN pair is short and unbroken all the way to the connector.
    ("R7", "Resistor_THT", R_THT[1], 40, 28, 0, "120R", {"1": "CANH", "2": "CANL"}),
    # PESD1CAN (TME order 19.07.2026.) replaced the unavailable PRTR5V0U2X:
    # a purpose-made CAN-bus ESD pair, bidirectional 24 V standoff, so it
    # tolerates real-vehicle bus levels instead of clamping to the 3,3 V rail.
    # Pinout per the Nexperia PESD1CAN datasheet: 1 = I/O1, 2 = I/O2,
    # 3 = common (GND). No VCC pin, so the old C30 decoupling cap is gone.
    # Stays SMD: a SOT-23 ESD pair has no THT equivalent, and the diode has to
    # be electrically short to the connector for the protection to mean anything.
    ("D1", "Package_TO_SOT_SMD", "SOT-23", 46, 28, 0, "PESD1CAN", {
        "1": "CANH", "2": "CANL", "3": G,
    }),
    # J2 is not a pin header but a MINITOOLS SEP-A-OBD-D2 mounted directly on the
    # board, facing up (straight pins, the cable plugs in from above). Own
    # footprint in obd2.pretty (pitch measured from the Minitools catalogue v1.3,
    # p. 18). It sits along the TOP edge, on the same side as USB-C (J1) and far
    # from USB-A, so both the diagnostic and the power cable leave on the same
    # side of the enclosure while the middle of the board stays free for the
    # display.
    # Pin rows: 1-8 north (y = +4,3), 9-16 south (y = -4,3).
    # J1962: 4 = CGND, 5 = SGND, 6 = CANH, 14 = CANL, 16 = +12 V.
    # TO VERIFY: compare the pin numbering against the numbers moulded into the
    # plastic of the delivered connector before ordering the board.
    ("J2", "obd2", "SEP-A-OBD-D2", 32, 88, 0, "J1962F OBD-II", {
        "4": G, "5": G, "6": "CANH", "14": "CANL", "16": "OBD_12V",
    }),
    # ── Power (top strip) ──
    # GCT USB4085-GF-A (TME order 19.07.2026.) replaced the LCSC-only HRO
    # TYPE-C-31-M-12: same 16-pin USB 2.0 receptacle class, stock KiCad
    # footprint, identical pad naming (A8/B8 = SBU stay unconnected).
    # The footprint origin is pad A1 (not the body centre): at rot 180 the
    # shell holes land at +4.36 mm and the mating face overhangs the top edge.
    ("J1", "Connector_USB", "USB_C_Receptacle_GCT_USB4085",
     # 23.15 from the 19.07.2026. sweep: at 23.65 the router dropped USBC_DP
     # every run (the DP/DM escape between the staggered A/B pad rows), and
     # 23.65/73.7 dropped CC1. J1_X/J1_Y env knobs sweep candidates.
     float(os.environ.get("J1_X", "70")), float(os.environ.get("J1_Y", "94.2")),
     180, "USB-C", {
        "A1": G, "B12": G, "A12": G, "B1": G,
        "A4": VB, "B9": VB, "A9": VB, "B4": VB,
        "A5": "CC1", "B5": "CC2",
        "A6": "USBC_DP", "B6": "USBC_DP", "A7": "USBC_DM", "B7": "USBC_DM",
        "SH": G,
    }),
    # PD sink (CH224K, ESSOP-10). Pinout verified against the WCH CH224DS1
    # reference schematic (section 6.1), NOT against the pin table: the table
    # lists "2, 3, 9 -> CFG1, CFG2, CFG3", but the schematic shows the order is
    # 2 = CFG2, 3 = CFG3, 9 = CFG1. Pad "0" is the exposed pad and the chip's
    # only ground connection.
    #   CFG1 -> Rset to GND selects the requested voltage. Verified verbatim
    #   against CH224DS1 section 5.2.1 on 21.08.2026., and the same table is
    #   repeated next to the reference schematic in section 6.1:
    #   6k8 = 9 V, 24k = 12 V, 56k = 15 V, NC = 20 V.   -> 24k here.
    #   Note the asymmetry that makes this table worth quoting exactly: an open
    #   CFG1 does NOT fall back to 5 V, it asks for 20 V. So a board sitting at
    #   5 V never implicates R23 - 5 V is the USB-C default before any PD
    #   contract, i.e. no contract was made at all.
    #   In resistor mode CFG2/CFG3 "cannot be connected" (5.2.1), hence None.
    # CC1/CC2 go straight to the connector: CH224K provides Rd internally, so
    # the external 5,1 k pull-downs of the old IP2368 stage are gone.
    # PINNED and rotated by 90 degrees: the packer used to place it ~20 mm from
    # the connector with the CC pins facing the opposite way, so CC2 failed to
    # route in all 10 attempts. At rot 90 pins 6/7 (CC2/CC1) face north, straight
    # at J1, and the pair is about 6 mm long.
    ("U1", "obd2", "CH224K_ESSOP-10-1EP_3.9x5.0mm_P1mm_EP2.3x3.2mm", 68, 84, 90, "CH224K", {
        "0": G,                                  # EPAD = GND (only GND pin)
        "1": "PD_VDD",
        "2": None, "3": None,                    # CFG2, CFG3 float in resistor mode
        # DP/DM LEFT UNCONNECTED. They used to sit on USBC_DP/USBC_DM, i.e. on
        # the very pair the ESP32 uses to talk to the computer. The CH224
        # datasheet, section 5.5, addresses this directly: "If you want to block
        # these protocols on CH224K/CH224D, the DP/DM pin on CH224K/CH224D is
        # required to be disconnected from the DP/DM on the Type-C connector,
        # and the DP pin on CH224 is required to be shorted to the DM on CH224."
        #
        # KNOWN DEVIATION (21.08.2026.): only the first half of that sentence is
        # implemented. Both pads are netless, so DP and DM are isolated from each
        # other, while the datasheet wants them tied together. This is not a
        # soldering question - each pin is soldered to its own pad, but no copper
        # joins the two pads. The fix is one shared net across pins 4 and 5,
        # which are adjacent at 1 mm pitch. Not applied to v0.7: the board is
        # already fabricated and populated, and the PD contract is negotiated
        # purely over CC, so the floating pair has no path into it. Carry this
        # into the next revision - see PRE-FABRICATION-CHECKLIST.md.
        #
        # Those pins only serve the
        # A-port protocols (BC1.2, QC), which this board does not need - the PD
        # contract is negotiated purely over the CC lines. Left connected, the
        # controller would attempt a handshake on the data pair when plugged into
        # an ordinary computer, and that pair is also the primary programming
        # path (USB-Serial-JTAG) and the MSC mode.
        "4": None, "5": None,                    # DP, DM - deliberately unconnected
        "6": "CC2", "7": "CC1",
        "8": "PD_SENSE",
        "9": "PD_CFG1",
        "10": None,                              # PG (open drain) unused
    }),
    ("R21", "Resistor_THT", R_THT[1], 6, 62, 0, "1k", {"1": VB, "2": "PD_VDD"}),
    ("C22", "Capacitor_THT", C_MED[1], 6, 66, 0, "1uF", {"1": "PD_VDD", "2": G}),
    ("R22", "Resistor_THT", R_THT[1], 6, 70, 0, "10k", {"1": VB, "2": "PD_SENSE"}),
    ("R23", "Resistor_THT", R_THT[1], 10, 62, 0, "24k", {"1": "PD_CFG1", "2": G}),
    # Input electrolytic 100 uF / 25 V. THT radial, pad 1 = anode (+).
    ("C1", "Capacitor_THT", CP_100[1], 14, 62, 0, "100uF/25V", {"1": VB, "2": G}),
    # VBUS -> 3,3 V buck (TPS562201, SOT-23-6: 1 GND, 2 SW, 3 VIN, 4 FB,
    # 5 EN, 6 VBST). Its 4,5 - 17 V input range covers both the 5 V that VBUS
    # carries before the PD contract and the 12 V after it, so the logic comes
    # up either way.
    ("U2", "Package_TO_SOT_SMD", "SOT-23-6", 36, 70, 0, "TPS562201DDCR", {
        "1": G, "2": "SW_3V3", "3": VB, "4": "FB_3V3",
        "5": VB, "6": "BST_3V3",
    }),
    # 4,7 uH - not 10 uH and not 2,2 uH.
    #
    # HISTORY. The first prototype had 2,2 uH. It was raised to 10 uH because at
    # 2,2 uH the ripple current through the output electrolytic was 0,54 A rms,
    # while a 22 uF electrolytic tolerates 100 to 200 mA. That treated the
    # symptom: the cause was not the inductor but the capacitor.
    #
    # WHY 10 uH IS WRONG. Table 7-2 of the TPS562201 datasheet (SLVSD91D) gives
    # L1 = 3,3 uH typical and 4,7 uH MAXIMUM for a 3,3 V output, and 4,7 uH both
    # typical and maximum for 5 V. 10 uH is more than double the upper limit. The
    # D-CAP2 loop has no external compensation and relies on the LC filter's
    # double pole landing in a given window: with 10 uH and 22 uF the pole sits
    # around 10,7 kHz instead of around 23 kHz.
    #
    # NOW. With low-ESR capacitors (see CP_LOWESR) the ripple current is no
    # longer the constraint: at 4,7 uH it is 0,88 A peak to peak, i.e. 0,25 A
    # rms, which a low-impedance part of that size carries. The peak inductor
    # current is about 1,05 A at a 0,5 A load, so the requirement is
    # Isat >= 1,5 A and DCR <= 0,1 ohm.
    ("L2", "Inductor_THT", L_THT[1], 41, 70, 0, "4u7H", {"1": "SW_3V3", "2": V3}),
    # Converter input and output capacitors. LOW-ESR, not a plain electrolytic -
    # the criterion sits next to CP_LOWESR. C3 is on 12 V (VBUS) and therefore
    # needs >= 25 V, C4 is on 3,3 V so >= 10 V is enough.
    ("C3", "Capacitor_THT", CP_LOWESR[1], 32, 66, 0, "22uF LowESR", {"1": VB, "2": G}),
    ("C4", "Capacitor_THT", CP_LOWESR[1], 40, 66, 0, "22uF LowESR", {"1": V3, "2": G}),
    ("C20", "Capacitor_THT", C_SM[1], 33, 73, 0, "100nF", {"1": VB, "2": G}),
    ("C21", "Capacitor_THT", C_SM[1], 39, 74, 0, "100nF", {"1": "SW_3V3", "2": "BST_3V3"}),
    ("R16", "Resistor_THT", R_THT[1], 45, 70, 0, "51k", {"1": V3, "2": "FB_3V3"}),
    # Lower leg of the feedback divider. Instead of a single 15,4 k resistor
    # there are TWO IN SERIES, 15 k + 470 R = 15,47 k. The reason is sourcing:
    # 15,4 k exists only in the E96 series and cannot be bought locally in a THT
    # package, whereas 15 k and 470 R are ordinary E24 values.
    # Vout = 0,768 x (1 + 51 / 15,47) = 3,300 V, i.e. 11 mV below the designed
    # 3,311 V. Substituting a bare 15 k is out of the question: it yields
    # 3,379 V, and the flash U7 has an absolute maximum of 3,6 V.
    # The series pair does not worsen the tolerance: 15 k +-1 % is +-150 R,
    # 470 R +-1 % is +-4,7 R, together +-154,7 R on 15,47 k, still exactly +-1 %.
    # The purchased ERA3AEB1542V (0603, 0,1 %) therefore stays unused - see README.
    # R17A goes through place_near next to U2.4, as before. R17B is PINNED
    # directly below it, in a spot that was free on the previous (proven
    # routable) board. The reason is twofold:
    #   1. Electrical: it makes FB_MID 3,7 mm long instead of 20+ mm. FB is a
    #      high-impedance node right next to a switching stage at 580 kHz and
    #      must not be stretched across the board.
    #   2. Routability: left to the packer, R17B steals space from its
    #      neighbours and reshuffles the power zone in a chain reaction. The
    #      first attempt pushed C29 into an empty corridor and broke 9 nets, the
    #      second moved C19 (the module's decoupling capacitor) 25 mm away from
    #      its supply pin.
    ("R17A", "Resistor_THT", R_THT[1], 45, 66, 0, "15k", {"1": "FB_3V3", "2": "FB_MID"}),
    ("R17B", "Resistor_THT", R_THT[1], 68.0, 29.25, 0, "470R", {"1": "FB_MID", "2": G}),
    # 12 V branch to J1962 pin 16: resettable fuse plus TVS clamp, so the
    # diagnostic tool draws its supply from the board, as it would in a car.
    # KEPT SMD: the fuse and the TVS are neither a resistor, nor a capacitor, nor
    # an inductor, and those packages solder by hand without trouble, so there is
    # no reason to spend board space on THT substitutes. The purchased
    # 1206L050YR and SMAJ16A-13-F therefore stay in the assembly, and the THT
    # alternatives (Bourns MF-RHT050, P6KE16A) are not needed.
    # The fuse output no longer feeds OBD_12V directly but FUSED_12V, from where
    # the blocking diode D3 passes only the board -> tool direction. See D3.
    ("F1", "Fuse", "Fuse_1206_3216Metric",
     float(os.environ.get("F1_X", "58")), float(os.environ.get("F1_Y", "20")),
     0, "PTC 500mA", {"1": VB, "2": "FUSED_12V"}),
    # TVS on the 12 V branch, SMAJ16A in an SMA package (DO-214AC), not SMB.
    # POLARITY FIXED: pad 1 is the CATHODE (KiCad's diode convention) and goes to
    # OBD_12V, pad 2 (anode) goes to ground. The first prototype had it the other
    # way round, which forward-biases the TVS and shorts the 12 V branch through
    # the PTC.
    ("D2", "Diode_SMD", "D_SMA",
     float(os.environ.get("D2_X", "58")), float(os.environ.get("D2_Y", "25")),
     0, "SMAJ16A", {"1": "OBD_12V", "2": G}),
    # ── Memory + USB ──
    # 208-mil body (5.3 mm), JEITA ED-7311-19 08-001-BBA. The part ACTUALLY
    # ORDERED is the Infineon S25FL128LAGMFM010 (SOC008 package, SOIC-8 208 mil),
    # so that is also the footprint value. The Winbond W25Q128JVSIQ is an
    # equivalent substitute: same package, same pinout and the same command set
    # the driver uses. The narrower 3,9 mm (150 mil) footprint fits NEITHER.
    # Moved from the bottom strip into the band east of the module: the flash
    # hangs only off the SPI bus toward U6, so that is where it belongs, and the
    # bottom strip is now needed by the OBD connector.
    ("U7", "Package_SO", "SOIC-8_5.3x5.3mm_P1.27mm", 64, 48, 0, "S25FL128LAGMFM010", {
        "1": "CS_FLASH", "2": "MISO", "3": V3, "4": G,
        "5": "MOSI", "6": "SCK", "7": V3, "8": V3,
    }),
    ("C13", "Capacitor_THT", C_SM[1], 64, 42, 0, "100nF", {"1": V3, "2": G}),
    # TI's official DRC0010J (VSON-10, 3x3 mm, exposed pad) from the KiCad
    # library - TS3USB221DRCR is the orderable part.
    ("U9", "Package_SON", "Texas_DRC0010J", 62, 22, 0, "TS3USB221", {
        # Pinout verified against TI SCDS220M (table 4-1) 18.07.2026.:
        # 1/2 = 1D+/1D- (port 1), 3/4 = 2D+/2D- (port 2), 5 = GND, 6 = OE
        # (LOW = switch active, per truth table 7-1), 7 = D-, 8 = D+ (common,
        # to the MCU), 9 = S (LOW = port 1), 10 = VCC, EP = GND.
        # S LOW selects port 1, and the firmware drives USB_SEL LOW for the
        # USB-C side, so port 1 = USB-C and port 2 = USB-A.
        "1": "USBC_DP", "2": "USBC_DM", "3": "USBA_DP", "4": "USBA_DM",
        "5": G, "6": G, "7": "USB_DM", "8": "USB_DP", "9": "USB_SEL",
        "10": V3, "11": G,
    }),
    ("C14", "Capacitor_THT", C_SM[1], 68, 22, 0, "100nF", {"1": V3, "2": G}),
    # Pinout verified against the Silergy datasheet 18.07.2026.:
    # 1 = OUT, 2 = GND, 3 = ISET, 4 = EN (active high), 5 = IN. IN comes from
    # the 5 V buck (U11), NOT from VBUS: VBUS carries 12 V after the PD
    # contract and the SY6280 is a 5,5 V part.
    ("U10", "Package_TO_SOT_SMD", "SOT-23-5", 72, 22, 0, "SY6280AAC", {
        "1": "VBUS_STICK", "2": G, "3": "ISET", "4": "USB_HOST_EN", "5": "V5_STICK",
    }),
    ("R19", "Resistor_THT", R_THT[1], 74, 18, 0, "6k8", {"1": "ISET", "2": G}),
    # The 10 uF positions are radial electrolytics, pad 1 = anode (+).
    ("C18", "Capacitor_THT", CP_10[1], 76, 22, 0, "10uF", {"1": "VBUS_STICK", "2": G}),
    # ── 12 V -> 5 V buck for the USB stick (added 18.07.2026.) ──
    # Same proven TPS562201 stage as U2, with the feedback divider set for
    # 5 V: 0,765 V x (1 + 51k / 9,31k) = 4,96 V. Powers SY6280 IN.
    # Moved into the upper power strip next to U2: both converters now share the
    # VBUS input in the same place, and only the V5_STICK net runs downward.
    ("U11", "Package_TO_SOT_SMD", "SOT-23-6", 58, 70, 0, "TPS562201DDCR", {
        "1": G, "2": "SW_5V", "3": VB, "4": "FB_5V", "5": VB, "6": "BST_5V",
    }),
    ("L3", "Inductor_THT", L_THT[1], 63, 70, 0, "4u7H", {"1": "SW_5V", "2": "V5_STICK"}),
    ("C27", "Capacitor_THT", CP_LOWESR[1], 54, 66, 0, "22uF LowESR", {"1": VB, "2": G}),
    ("C28", "Capacitor_THT", CP_LOWESR[1], 62, 66, 0, "22uF LowESR", {"1": "V5_STICK", "2": G}),
    # PINNED. The coordinate is the one the packer chose itself before R17B was
    # introduced, and it has to stay. When R17B entered the power zone it took
    # this spot and C29 ended up at (57, 68) - in a corridor that had been empty
    # until then and that carried SPI (MOSI/MISO/SCK/CS_FLASH/CS_TFT/TFT_DC) plus
    # all three button lines. The result was 9 unrouted nets in all 10 Freerouting
    # attempts, i.e. deterministic rather than bad luck.
    ("C29", "Capacitor_THT", C_SM[1], 79.77, 68.53, 0, "100nF", {"1": "SW_5V", "2": "BST_5V"}),
    # R24/R25 are pinned to the coordinates the packer gave them BEFORE the user
    # interface control changed. When that control's courtyard changed, the packer
    # swapped these two resistors, and the shift broke the routing of net CC2.
    ("R24", "Resistor_THT", R_THT[1], 52.18, 63.08, 0, "51k", {"1": "V5_STICK", "2": "FB_5V"}),
    # 9k31 also moves to THT metal film (the purchased 0805 stays unused).
    ("R25", "Resistor_THT", R_THT[1], 80.8, 28.1, 0, "9k31", {"1": "FB_5V", "2": G}),
    # rot 0 with the anchor at y = 9,3. At rot 180 the opening faced into the
    # board (a stick would lie above the components). At rot 0 it faces south
    # past the bottom edge, and the front of the shell overhangs by ~4,3 mm (the
    # board-edge marker in the Molex footprint sits at local y = 9,27 mm).
    # The two mounting lugs are named "SH" in the Molex footprint, exactly like
    # J1's. They used to be addressed here as "5" and "6", which match no pad at
    # all, so the assignment silently did nothing and the USB-A shell sat on no
    # net. DRC cannot catch that: a pad with no net has nothing to be unconnected
    # from. Found 10.08.2026. by diffing this table against the built board.
    ("J4", "Connector_USB", "USB_A_Molex_67643_Horizontal", 20, 9.3, 0, "USB-A", {
        "1": "VBUS_STICK", "2": "USBA_DM", "3": "USBA_DP", "4": G, "SH": G,
    }),
    # ── Display header (module plugs in above the board) ──
    # Waveshare LCD Module pinout (18.07.2026.): VCC, GND, DIN(MOSI), CLK(SCK),
    # CS, DC, RST, BL. The whole Waveshare small-LCD family (1.8"/2"/2.4")
    # shares this 8-pin interface, so a stock substitution needs only a
    # TFT_eSPI driver flag. MISO is not wired - the module is write-only.
    # J5 stands VERTICAL (rot 0), as a narrow 3,6 x 21,4 mm column east of the
    # module. Laid flat it was a 22 mm wall of eight THT pads right at the module
    # edge and the signals leaving U6 had no escape eastward (JOY_SW and
    # CS_FLASH failed to route in every attempt).
    # The anchor is pin 1 and the pins run downward on a 2,54 mm pitch. At
    # y = 44,2, pin 5 (CS_TFT) lands on y = 34,0, exactly level with pin U6.22
    # where that signal starts, so the trace runs due east. At y = 34 the signal
    # had to cut diagonally through the congested band and did not get through.
    ("J5", "Connector_PinHeader_2.54mm", "PinHeader_1x08_P2.54mm_Vertical", 56, 44.2, 0, "LCD 18366", {
        "1": V3, "2": G, "3": "MOSI", "4": "SCK", "5": "CS_TFT",
        "6": "TFT_DC", "7": "TFT_RST", "8": "TFT_LED",
    }),
    # With the Waveshare module, BL is a logic enable input (the backlight
    # driver is on the module), so R8 is a harmless series resistor that
    # keeps the net protected rather than a LED current limiter.
    ("R8", "Resistor_THT", R_THT[1], 56, 57, 0, "33R", {"1": V3, "2": "TFT_LED"}),
    # ── UI column (right edge) ──
    # ENC1 = BI Technologies EN11-HSB1AQ20 incremental encoder with push-button,
    # 20 pulses and 20 detents per revolution. It replaced the rotary
    # potentiometer of the earlier prototypes: digital relative steps instead of
    # an absolute analogue position, which removes the ADC, its noise filtering
    # and the logarithmic-taper correction from the firmware entirely.
    #
    # The footprint is the STOCK KiCad Alps EC11E-with-switch: EN11 belongs to
    # the same 11 mm encoder family and has the same lead arrangement (A, C, B on
    # a 2,5 mm pitch on one side, two switch contacts on the other, two mounting
    # tabs). BEFORE ORDERING THE BOARD, verify it with calipers against the real
    # part - the footprint is the one item on this board that was not measured
    # from the delivered component.
    #
    # UI AXIS: the push-buttons, the stick and the encoder share one vertical
    # axis, x = 104. What gets aligned to it is the SHAFT, because that is what
    # the user sees and grabs. In the stock footprint the body centre (and the
    # shaft axis) sits at (7,50, -2,50) relative to the origin, so the anchor
    # that puts the shaft on (104, 69) is (104 - 7,50, 69 + 2,50) = (96,50, 71,50).
    #
    # NOTE: the routed .kicad_pcb in the repository still carries the older
    # anchor 96,75, which puts the shaft 0,25 mm off the axis. Correcting it
    # requires a full re-route, and Freerouting is not deterministic at this
    # density, so it is not worth risking a worse trace layout for 0,25 mm. The
    # new anchor enters the board at the next full regeneration
    # (route_board.ps1). The deviation is smaller than the fabrication tolerance
    # (silkscreen about +-0,15 mm, hole position about +-0,07 mm) and than the
    # lead clearance in the holes, so it is invisible on the finished device.
    ("ENC1", "Rotary_Encoder", "RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm",
     96.50, 71.50, 0, "EN11-HSB1AQ20", {
        # The contacts do not go straight to the filtered node but to ENC_*_RAW,
        # from where the series resistor R38-R40 (100 R) leads to the node with
        # the pull-up and the capacitor. See the comment next to R38.
        "A": "ENC_A_RAW", "B": "ENC_B_RAW", "C": G,
        "S1": "ENC_SW_RAW", "S2": G, "MP": G,
    }),
    # SW6 (19.07.2026.) replaced the J3 header + external analog stick: the
    # Alps SKRHABE010 5-way switch is soldered directly to the board. It is a
    # DIGITAL part (4 direction contacts + centre push, one common), so each
    # axis encodes its two directions as ADC levels on the JOY_X/JOY_Y nets:
    # pull-up 6k8 to 3V3 (idle ~3,3 V), the "B/D" contact grounds the net
    # through a 10 k ladder (~1,96 V), the "A/C" contact grounds it directly
    # (0 V). Centre push = JOY_SW (active low, R9 pull-up).
    # Pads per the EasyEDA symbol: 1=A, 2=CEN, 3=C, 4=D, 5=COM, 6=B, 7/8 frame.
    # rot 45 - mounted square, the movement directions came out diagonal, so the
    # whole switch is turned by 45 degrees to give the user up/down/left/right.
    # The mapping of contacts to directions still has to be verified on the real
    # part (it is a firmware constant).
    ("SW6", "obd2", "SKRHABE010", 104, 51, 45, "SKRHABE010", {
        "1": "JOY_X", "2": "JOY_SW", "3": "JOY_Y",
        "4": "JOY_YB", "5": G, "6": "JOY_XB",
        "7": G, "8": G,
    }),
    # Interface push-buttons in a column along the right edge. The courtyard
    # extends 6 mm below and ~4,8 mm to each side of the origin.
    # SW_PUSH_6mm does not have its origin at the body centre: the courtyard
    # centre lies at anchor + (3,25, -2,25). The anchors are therefore offset so
    # that the VISIBLE button centres land exactly on the axis x = 104 and on the
    # heights 17,25 / 29,25 / 41,25 mm, in line with the stick (51) and the
    # encoder shaft (69).
    ("SW1", "Button_Switch_THT", "SW_PUSH_6mm", 100.75, 41.25, 0, "CONFIRM", {"1": "BTN_CONFIRM", "2": G}),
    ("SW2", "Button_Switch_THT", "SW_PUSH_6mm", 100.75, 29.25, 0, "CLEAR", {"1": "BTN_CLEAR", "2": G}),
    ("SW3", "Button_Switch_THT", "SW_PUSH_6mm", 100.75, 17.25, 0, "RETURN", {"1": "BTN_RETURN", "2": G}),
    # Interface pull-ups: a narrow column west of the buttons (the inputs are
    # input-only pins with no internal pull-up - see the R9-R12 documentation).
    # Moving the column to x = 77 was tried and rejected: it cuts the east-west
    # corridor carrying JOY, SPI, UART and USBA_DP, leaving 7 nets unrouted in
    # all 10 attempts. The column sits at x = 82,9, west of the interface axis,
    # and is offset in height so that NO pull-up shares a row with its own
    # button: at the same height the resistor and button pads end up 1,2 mm
    # apart and BTN_CLEAR then fails to route in all 10 attempts.
    # CAUTION: the flat footprint (P10,16) has its origin on the FIRST pad, not
    # at the body centre, so the centre is at anchor + 5,08 mm. Anchor 82,9 puts
    # the body at x 82,9..93,1, which leaves a 6,8 mm corridor to the button pads.
    ("R12", "Resistor_THT", R_THT[1], 82.9, 21, 0, "10k", {"1": V3, "2": "BTN_RETURN"}),
    # y = 33: moving it to 37 was tried and rejected - the pull-up column lies
    # inside the "mcu" zone, so the shift steals the spot from capacitor C25.
    ("R11", "Resistor_THT", R_THT[1], 82.9, 33, 0, "10k", {"1": V3, "2": "BTN_CLEAR"}),
    ("R10", "Resistor_THT", R_THT[1], 82.9, 45, 0, "10k", {"1": V3, "2": "BTN_CONFIRM"}),
    ("R26", "Resistor_THT", R_THT[1], 82.9, 52, 0, "6k8", {"1": V3, "2": "JOY_X"}),
    ("R9",  "Resistor_THT", R_THT[1], 82.9, 58, 0, "10k", {"1": V3, "2": "JOY_SW"}),
    ("R27", "Resistor_THT", R_THT[1], 82.9, 64, 0, "6k8", {"1": V3, "2": "JOY_Y"}),
    # R28/R29 sit north-east of the stick, each next to ITS OWN contact: after
    # the 45 degree rotation SW6 pad 6 (JOY_XB) is at anchor + (3,6, 1,5) and
    # pad 4 (JOY_YB) at anchor + (1,5, 3,6).
    # The ladder goes ABOVE the rotary control: the band between the stick and
    # that control is only 6,5 mm, while a flat resistor needs 12,2 x 3,1 mm.
    # Both resistors sit above its courtyard, which ends at y = 81,5.
    ("R28", "Resistor_THT", R_THT[1], 97, 85, 0, "10k", {"1": "JOY_X", "2": "JOY_XB"}),
    ("R29", "Resistor_THT", R_THT[1], 97, 89, 0, "10k", {"1": "JOY_Y", "2": "JOY_YB"}),
    ("R13", "Resistor_THT", R_THT[1], 56, 53, 0, "10k", {"1": V3, "2": "MCU_EN"}),
    # ── UART programming header ──
    ("J6", "Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical", 57, 84, 0, "UART", {
        "1": "TXD0", "2": "RXD0", "3": G,
    }),
    # ── Programming circuit (added 2026-07-18) ──
    # Firmware is flashed over USB-C through the S3's ROM USB-Serial-JTAG on
    # the fixed OTG pins (GPIO19/20). Three things make that work on this
    # board: R15 holds the TS3USB221 select LOW while no firmware drives it,
    # so the mux sits on the USB-C side at reset and the ROM bootloader is
    # reachable; SW4 pulls the IO0 strapping pin low to force download mode
    # (needed because the running firmware claims the OTG controller for MSC,
    # which hides the USB-Serial-JTAG interface); SW5 resets the module.
    # R14 is the documented external 10 k pull-up on IO0, and R13 + C26 form
    # the usual EN reset RC so the module comes out of reset cleanly.
    # SW_PUSH_6mm has pads at +-6,5 mm, OUTSIDE its own courtyard (9,6 mm), so
    # they have to be kept clear of the rotary control: at x = 74 the right pad
    # ran into it.
    # The SW4/SW5 spacing sits exactly on the limit: the SW_PUSH_6mm courtyard
    # runs from anchor - 6 to + 1,5 mm, so 7 mm of spacing gives a 0,5 mm
    # overlap. SW4 has to stay at 93 (moving it to 95 breaks the routing of all
    # three BTN nets), so the clearance is won by lowering SW5 to 85.
    ("SW4", "Button_Switch_THT", "SW_PUSH_6mm", 84, 93, 0, "BOOT", {"1": "BOOT", "2": G}),
    ("SW5", "Button_Switch_THT", "SW_PUSH_6mm", 84, 85, 0, "RESET", {"1": "MCU_EN", "2": G}),
    ("R14", "Resistor_THT", R_THT[1], 56, 49, 0, "10k", {"1": V3, "2": "BOOT"}),
    ("R15", "Resistor_THT", R_THT[1], 58, 30, 0, "10k", {"1": "USB_SEL", "2": G}),
    ("C26", "Capacitor_THT", C_MED[1], 56, 45, 0, "1uF", {"1": "MCU_EN", "2": G}),
    # ── Decoupling: one 100 nF per supply pin, plus bulk per section ──
    # MCP2515 (SOIC-18W) has a single VDD, pin 18. C10 sits on it; C11 is a
    # second local 100 nF on the same rail, the CAN section being the noisiest.
    ("C10", "Capacitor_THT", C_SM[1], 19, 46, 0, "100nF", {"1": V3, "2": G}),
    ("C11", "Capacitor_THT", C_SM[1], 19, 42, 0, "100nF", {"1": V3, "2": G}),
    ("C12", "Capacitor_THT", C_SM[1], 19, 34, 0, "100nF", {"1": V3, "2": G}),
    ("C5",  "Capacitor_THT", CP_10[1], 19, 30, 0, "10uF", {"1": V3, "2": G}),
    # Module decoupling capacitors: place_near puts them at the supply pin U6.2.
    ("C15", "Capacitor_THT", C_SM[1], 56, 41, 0, "100nF", {"1": V3, "2": G}),
    ("C16", "Capacitor_THT", C_SM[1], 56, 37, 0, "100nF", {"1": V3, "2": G}),
    ("C19", "Capacitor_THT", CP_10[1], 60, 37, 0, "10uF", {"1": V3, "2": G}),
    # SY6280 VIN and the display header had no 100 nF at all in earlier drafts.
    ("C23", "Capacitor_THT", C_SM[1], 72, 18, 0, "100nF", {"1": "V5_STICK", "2": G}),
    ("C24", "Capacitor_THT", C_SM[1], 60, 57, 0, "100nF", {"1": V3, "2": G}),
    ("C25", "Capacitor_THT", CP_10[1], 64, 57, 0, "10uF", {"1": V3, "2": G}),
    # ── Mounting holes ──
    ("H1", "MountingHole", "MountingHole_3.2mm_M3", 5, 5, 0, "M3", {}),
    ("H2", "MountingHole", "MountingHole_3.2mm_M3", 110, 5, 0, "M3", {}),
    ("H3", "MountingHole", "MountingHole_3.2mm_M3", 110, 95, 0, "M3", {}),
    ("H4", "MountingHole", "MountingHole_3.2mm_M3", 5, 95, 0, "M3", {}),

    # ══ Additions from the design review ═════════════════════════════════════
    #
    # 1) Series resistors on SPI. SCK measured 105 mm and MOSI 100 mm, with three
    #    loads (U4, U7, J5) and no termination at all. 33 R at the source damp
    #    the reflection off the end of the line. The value approximates the
    #    ESP32 pin's output impedance (about 40 R) minus itself, which is the
    #    usual series termination.
    #    The net is split: U6 drives SCK_MCU / MOSI_MCU, and the peripherals no
    #    longer hang directly off the microcontroller pin but behind the resistor.
    ("R30", "Resistor_THT", R_THT[1], 60, 30, 0, "33R", {"1": "SCK_MCU",  "2": "SCK"}),
    ("R31", "Resistor_THT", R_THT[1], 60, 26, 0, "33R", {"1": "MOSI_MCU", "2": "MOSI"}),
    #
    # 2) Encoder: pull-up and RC filter. All three contacts used to hang on the
    #    internal pull-ups alone, and A and B are decoded in an interrupt, where
    #    mechanical contact bounce produces phantom steps. 10 k to 3,3 V and a
    #    capacitor to ground is the standard arrangement for EC11/EN11. The
    #    firmware still debounces; this removes the fastest spikes for it.
    ("R32", "Resistor_THT", R_THT[1], 100, 76, 0, "10k",  {"1": V3, "2": "ENC_A"}),
    ("R33", "Resistor_THT", R_THT[1], 100, 72, 0, "10k",  {"1": V3, "2": "ENC_B"}),
    ("R34", "Resistor_THT", R_THT[1], 100, 68, 0, "10k",  {"1": V3, "2": "ENC_SW"}),
    #    VALUE RAISED TO 47 nF. With 10 nF the time constant was
    #    10 k x 10 nF = 100 us, while EN11 contact bounce lasts of the order of a
    #    millisecond. The node has time to return to a full 3,3 V between two
    #    bounces, so the filter rejects practically nothing. With 47 nF the
    #    constant is 470 us and the edge to the threshold is
    #    1,39 x 470 us = 650 us. The fastest realistic turn (5 revolutions per
    #    second, 20 pulses per revolution) gives an edge every 5 ms per channel,
    #    so 650 us uses 13 % of that interval.
    ("C31", "Capacitor_THT", C_SM[1], 104, 76, 0, "47nF", {"1": "ENC_A",  "2": G}),
    ("C32", "Capacitor_THT", C_SM[1], 104, 72, 0, "47nF", {"1": "ENC_B",  "2": G}),
    ("C33", "Capacitor_THT", C_SM[1], 104, 68, 0, "47nF", {"1": "ENC_SW", "2": G}),
    #
    # 2b) A second capacitor on each encoder line, this time AT THE MODULE PIN
    #     ITSELF. The reason was measured on the first routed board: the
    #     C31-C33 filter sits at the encoder, where the contact bounce actually
    #     happens, but past it the signal still travels 115 to 137 mm across the
    #     board, through two or three vias and alongside the SPI bus. The node is
    #     high impedance (10 k pull-up), so that run makes a fine antenna.
    #
    #     THE VALUE IS 1 nF, not 10 nF. This capacitor's job is not debouncing -
    #     C31-C33 at the contact already do that - but shunting picked-up
    #     high-frequency noise to ground right at the input. For that 1 nF is
    #     plenty (160 ohm at 1 MHz against a 10 k pull-up), and the line's total
    #     time constant rises from 100 to only 110 us. With 10 nF it would be
    #     200 us, still usable, but needlessly slowing an edge that is decoded in
    #     an interrupt.
    ("C34", "Capacitor_THT", C_TINY[1], 60, 34, 0, "1nF", {"1": "ENC_A",  "2": G}),
    ("C35", "Capacitor_THT", C_TINY[1], 60, 30, 0, "1nF", {"1": "ENC_B",  "2": G}),
    ("C36", "Capacitor_THT", C_TINY[1], 60, 26, 0, "1nF", {"1": "ENC_SW", "2": G}),
    #
    # 3) Blocking diode in the 12 V branch. The path used to be
    #    VBUS -> F1 -> OBD_12V -> pin 16, and F1 is a PTC that conducts in both
    #    directions, so external 12 V from a vehicle or from a tool that powers
    #    pin 16 itself would flow back into VBUS, into both converter inputs and
    #    onto the USB-C connector. The diode passes only the intended direction:
    #    the board powers the tool.
    #    D_SMA footprint: pad 1 = cathode, pad 2 = anode, so the anode faces the
    #    fuse and the cathode the connector.
    #    THE PART IS SMAJ16A, the same TVS as D2, in forward conduction.
    #
    #    HISTORY. Between 09.08. and 10.08.2026. an SS34 Schottky stood here, on
    #    the argument that a TVS datasheet "gives no rating for continuous
    #    forward current, only IFSM for an 8,3 ms pulse". That argument was too
    #    strict and is withdrawn. The Littelfuse SMAJ datasheet (rev. 10/2020)
    #    does give what bounding the forward case needs: PD = 3,3 W steady state
    #    and RthJA = 120 C/W. The branch is fused at 500 mA by F1, and a scan
    #    tool draws 25 to 50 mA, so the worst case is 0,45 W and a 54 C rise, on
    #    a 125 C headroom. There was never a thermal problem to solve.
    #
    #    What the swap costs: the TVS blocks only to 16 V (breakdown 17,8 to
    #    19,7 V) where the Schottky blocked to 40 V. That matters solely when the
    #    simulator is plugged into a live vehicle, which is not what this board
    #    is for - it SOURCES the 12 V on pin 16. What it gains: reverse leakage
    #    below 1 uA instead of the Schottky's hundreds of uA, rising into
    #    milliamps when hot, and blocking leakage is the entire job of D3.
    #    Forward drop goes from about 0,45 V to about 0,7 V at 50 mA, so the tool
    #    sees about 11,3 V instead of 11,7 V. Tools run from about 9 V.
    #
    #    Same SMA package and pad 1 is the cathode on both, so this is a drop-in:
    #    no footprint, gerber or silkscreen change, and no new part to order.
    ("D3", "Diode_SMD", "D_SMA", 46, 80, 0, "SMAJ16A",
     {"1": "OBD_12V", "2": "FUSED_12V"}),
    #
    # 4) Test points. The design review checklist asks for eight, and the earlier
    #    prototypes had none. THT, because a wire gets soldered to them or a probe
    #    hook clipped on, which an SMD pad does not survive.
    #    The coordinates below are only a starting point: the real position is
    #    chosen by NEAR_OF, which brings each point next to a pad of its own net
    #    so the stub stays short. See the reasoning next to FIXED.
    ("TP1", "TestPoint", "TestPoint_THTPad_2.0x2.0mm_Drill1.0mm", 33.5, 4.0, 0, "3V3",  {"1": V3}),
    ("TP2", "TestPoint", "TestPoint_THTPad_2.0x2.0mm_Drill1.0mm", 38.5, 4.0, 0, "GND",  {"1": G}),
    ("TP3", "TestPoint", "TestPoint_THTPad_2.0x2.0mm_Drill1.0mm", 43.5, 4.0, 0, "CANH", {"1": "CANH"}),
    ("TP4", "TestPoint", "TestPoint_THTPad_2.0x2.0mm_Drill1.0mm", 48.5, 4.0, 0, "CANL", {"1": "CANL"}),
    ("TP5", "TestPoint", "TestPoint_THTPad_2.0x2.0mm_Drill1.0mm", 53.5, 4.0, 0, "MOSI", {"1": "MOSI"}),
    ("TP6", "TestPoint", "TestPoint_THTPad_2.0x2.0mm_Drill1.0mm", 58.5, 4.0, 0, "MISO", {"1": "MISO"}),
    ("TP7", "TestPoint", "TestPoint_THTPad_2.0x2.0mm_Drill1.0mm", 63.5, 4.0, 0, "SCK",  {"1": "SCK"}),
    ("TP8", "TestPoint", "TestPoint_THTPad_2.0x2.0mm_Drill1.0mm", 68.5, 4.0, 0, "VBUS", {"1": VB}),

    # ══ Additions from the second design review ══════════════════════════════
    #
    # 5) Bulk capacitor at the INPUT of the current-limited switch U10.
    #    The checklist asks for 10 uF at both the input and the output of the
    #    switch. The output had C18, the input only the 100 nF C23, and the
    #    nearest electrolytic on the V5_STICK net was C28, 73 mm away. A USB
    #    stick drawing 500 mA at plug-in sees a voltage drop along that run, and
    #    USB requires at least 4,75 V at the socket. A plain electrolytic is
    #    entirely adequate here: this is a charge reservoir for an inrush, not
    #    part of the converter's feedback loop.
    ("C37", "Capacitor_THT", CP_10[1], 70, 14, 0, "10uF", {"1": "V5_STICK", "2": G}),
    #
    # 6) ESD protection on both USB connectors. The CAN pair had D1, while the
    #    two connectors the user plugs into every day had nothing.
    #    USBLC6-2SC6, SOT-23-6. Pinout (ST, table 2): 1 = I/O1, 2 = GND,
    #    3 = I/O2, 4 = I/O2, 5 = Vbus (reference rail), 6 = I/O1.
    #
    #    PIN 5 GOES TO +3,3 V, NOT TO VBUS. That pin's standoff is 5,25 V, and
    #    VBUS on this board carries 12 V after the PD contract, which would
    #    destroy it. The reference rail may be the local supply of the protected
    #    lines, and the data pair never exceeds 3,6 V.
    ("D4", "Package_TO_SOT_SMD", "SOT-23-6", 74, 92, 0, "USBLC6-2SC6", {
        "1": "USBC_DP", "2": G, "3": "USBC_DM", "4": "USBC_DM",
        "5": V3, "6": "USBC_DP",
    }),
    ("D5", "Package_TO_SOT_SMD", "SOT-23-6", 26, 14, 0, "USBLC6-2SC6", {
        "1": "USBA_DP", "2": G, "3": "USBA_DM", "4": "USBA_DM",
        "5": V3, "6": "USBA_DP",
    }),
    #
    # 7) Pull-ups on the chip-select lines. Until the firmware claims the pin,
    #    CS_CAN (GPIO10) and CS_FLASH (GPIO15) float, so the MCP2515 and the
    #    flash can see a spurious selection. 10 k to 3,3 V holds them inactive.
    ("R35", "Resistor_THT", R_THT[1], 22, 38, 0, "10k", {"1": V3, "2": "CS_CAN"}),
    ("R36", "Resistor_THT", R_THT[1], 68, 44, 0, "10k", {"1": V3, "2": "CS_FLASH"}),
    #
    # 8) Pull-down on the enable of switch U10. USB_SEL had R15, USB_HOST_EN had
    #    nothing, and the SY6280's EN is active high. Until the firmware claims
    #    GPIO17 the input floats, so the 5 V feed to the stick could switch on
    #    unbidden.
    ("R37", "Resistor_THT", R_THT[1], 76, 14, 0, "10k", {"1": "USB_HOST_EN", "2": G}),
    #
    # 9) Series resistors in the encoder filter, 100 R right at the contact.
    #    Without them the filter capacitor (C31-C33) hangs directly on the
    #    contact and discharges through it on every closure with no current
    #    limit. At 47 nF and 3,3 V that is a spike of several amperes through a
    #    contact rated for 10 mA, which burns the encoder contact out.
    #    With 100 R the peak current is 33 mA and the falling edge stays fast
    #    (100 R x 47 nF = 4,7 us). The rising edge is still set by the 10 k
    #    pull-up, i.e. 470 us, which is the whole point of the filter.
    #    The low level becomes 3,3 V x 100 / 10100 = 33 mV, still a clean logic
    #    zero.
    #    The footprint is VERTICAL (5,08 mm pitch), see the reasoning at R_VERT.
    ("R38", "Resistor_THT", R_VERT[1], 108, 76, 0, "100R", {"1": "ENC_A_RAW",  "2": "ENC_A"}),
    ("R39", "Resistor_THT", R_VERT[1], 108, 72, 0, "100R", {"1": "ENC_B_RAW",  "2": "ENC_B"}),
    ("R40", "Resistor_THT", R_VERT[1], 108, 68, 0, "100R", {"1": "ENC_SW_RAW", "2": "ENC_SW"}),
]

# ── Shifting the edge-anchored groups out to the new edge ────────────────────
# The coordinates in the table above date from the earlier 115 x 100 outline.
# Instead of rewriting every number by hand, the groups that align to the right
# or the top edge are shifted here. Parts not listed stay where they were, which
# frees the band x = 96..111 and the band y = 84..99, both of which used to be
# the board edge.
RIGHT_EDGE = {"ENC1", "SW6", "SW1", "SW2", "SW3",
              "R9", "R10", "R11", "R12", "R26", "R27", "R28", "R29",
              "H2", "H3"}
TOP_EDGE = {"J1", "J2", "U1", "J6", "SW4", "SW5", "H3", "H4"}

# OPTIONAL: parts the board tolerates being left unpopulated. They get KiCad's
# DNP flag, so the state lives in the board file and not only in the docs.
#
# ONLY D4 AND D5 QUALIFY, and it was measured, not assumed: delete the footprint
# from a copy of the board, run DRC, and nothing goes unconnected. Both are
# genuinely PARALLEL - pads 1 and 6 sit on the same net and pads 3 and 4 on the
# other, and the copper joins them OUTSIDE the package, so the USB pair runs past
# the chip rather than through it.
#
# DO NOT ADD ANYTHING ELSE HERE without repeating that test. The autorouter ran
# other nets through the pads of about a dozen parts, so leaving those off breaks
# copper that has nothing to do with their own function: R32, R34, R36, R37, C4,
# C27, C28, C32 and C37 each carry a foreign net across their pads, R30/R31 are
# in series in the SPI bus and R38-R40 in series at the encoder contacts.
OPTIONAL = {"D4", "D5"}
# The test points are already written in the new coordinates (bottom right
# corner of the enlarged board).
_shifted = []
for _c in COMPONENTS:
    _ref, _lib, _fp, _x, _y, _rot, _val, _pads = _c
    if _ref in RIGHT_EDGE:
        _x += DX_RIGHT
    if _ref in TOP_EDGE:
        _y += DY_TOP
    _shifted.append((_ref, _lib, _fp, _x, _y, _rot, _val, _pads))
COMPONENTS = _shifted

# extra net for the buck switch node
for extra in ["PD_SW2"]:
    ni = pcbnew.NETINFO_ITEM(board, extra)
    board.Add(ni)
    nets[extra] = ni

# ── Placement ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from place import Placer

# Everything that defines the board outline or the user interface is pinned; the
# rest is packed by Placer.
FIXED = {"U6", "J1", "U1", "J2", "J4", "J5", "J6", "H1", "H2", "H3", "H4",
         "ENC1", "SW6", "SW1", "SW2", "SW3", "SW4", "SW5",
         "R9", "R10", "R11", "R12", "R26", "R27", "R28", "R29"}
# R24, R25, C29 and R17B are no longer pinned. They used to be, because on the
# 115 x 100 outline the packer left them without room next to their chip, so
# their coordinates were written in by hand far away from it. Now NEAR_OF drives
# them, bringing each one right up to its pin, and at 130 x 115 there is room.
#
# THE TEST POINTS ARE NOT PINNED, even though a tidy row along the edge would
# look neater. The first attempt had them in a row along the bottom edge and
# measurement showed immediately that this was a mistake: CANH grew from 62 to
# 148 mm and MOSI from 100 to 148 mm, because every net has to run down to the
# bottom of the board and back. The checklist says so explicitly ("test points
# go in line, not on a stub"), and on an earlier revision the test points had
# already broken the MOSI net once. So each point now anchors to a pad of ITS
# OWN net, making the stub a few millimetres long.

# zone rectangles (x1, y1, x2, y2) in board mm
ZONES = {
    # All four zones were widened into the two new bands (x up to 111, y up to
    # 93) opened by shifting the interface and the top edge. Without that the
    # board would simply be bigger while the packer still had exactly as much
    # room as before.
    "can":    (2, 50, 44, 93),     # top left, below the OBD connector
    "power":  (56, 46, 111, 93),   # top right, below USB-C and the PD controller
    # The left edge of the power zone moved from x = 48 to 56. At 48 the packer
    # dropped U2 into the bottom left corner of the zone, which is 6,7 mm from
    # module pin 2 (the 3,3 V supply), so the inductor L2 and the bootstrap C21
    # took the space the module's decoupling capacitors need. The zone was
    # widened rightward to 111, so losing ground on the left costs nothing.
    "mcu":    (52, 20, 111, 45),   # east of the module: flash, decoupling, RC
    "memusb": (34, 2, 111, 18),    # right of USB-A: mux, load switch, decoupling
}
ZONE_OF = {
    "U1": "power", "C1": "power", "C22": "power",
    "R21": "power", "R22": "power", "R23": "power",
    "U2": "power", "L2": "power", "C20": "power", "C21": "power",
    "R16": "power", "R17A": "power", "R17B": "power",
    "C3": "power", "C4": "power",
    "U11": "power", "L3": "power", "C27": "power", "C28": "power",
    "C29": "power", "R24": "power", "R25": "power",
    "U4": "can", "U5": "can", "Y1": "can",
    "C10": "can", "C11": "can", "C12": "can", "C5": "can",
    "C6": "can", "C7": "can",
    "U7": "mcu", "C13": "mcu", "R13": "mcu", "R14": "mcu", "C26": "mcu",
    "C15": "mcu", "C16": "mcu", "C19": "mcu", "C24": "mcu", "C25": "mcu",
    "R8": "mcu",
    "U9": "memusb", "U10": "memusb", "C14": "memusb", "C18": "memusb",
    "C23": "memusb", "R19": "memusb", "R15": "memusb",
    # The added parts. The SPI series resistors and the encoder RC filter have
    # their own anchor in NEAR_OF, so the zone is only a fallback for when there
    # is no room next to the pin. D3 goes into the power zone, next to F1.
    "R30": "mcu", "R31": "mcu",
    "R32": "mcu", "R33": "mcu", "R34": "mcu",
    "C31": "mcu", "C32": "mcu", "C33": "mcu",
    "C34": "mcu", "C35": "mcu", "C36": "mcu",
    "D3": "power",
    "TP1": "mcu", "TP2": "mcu", "TP3": "can", "TP4": "can",
    "TP5": "mcu", "TP6": "mcu", "TP7": "mcu", "TP8": "power",
    # As above, the zone is only a fallback: each of these parts has an anchor in
    # NEAR_OF and that is where it belongs.
    "C37": "memusb", "R37": "memusb", "D5": "memusb",
    "D4": "power",
    "R35": "can", "R36": "mcu",
    "R38": "mcu", "R39": "mcu", "R40": "mcu",
}

# Parts that must sit next to a specific PAD of a device: decoupling caps go
# at the supply pin, crystal load caps at the crystal pins, and so on.
# ref -> (anchor ref, anchor pad number)
NEAR_OF = {
    "C20": ("U2", "3"),                           # TPS562201 VIN decoupling
    "C21": ("U2", "6"),                           # TPS562201 bootstrap cap
    # TPS562201 feedback divider. R17A and R17B form the lower leg built as a
    # series pair (15 k + 470 R), so FB_MID is a short local net between them and
    # must not be stretched across the board - FB is a high-impedance node (about
    # 50 uA) right next to a switching stage at 580 kHz.
    # The divider is CHAINED, not all anchored to the same pin. Electrically it
    # is the string U2.4 - R16.2 | R16.1 to +3,3 V, with FB_3V3 joining U2.4,
    # R16.2 and R17A.1. Anchoring all three to the same pin makes them compete
    # for the same ring and the last one ends up 15 mm away. Chained, each sits
    # next to its predecessor, so the FB node stays compact - which is the only
    # thing that matters electrically.
    "R16": ("U2", "4"), "R17A": ("R16", "2"), "R17B": ("R17A", "2"),
    "C3":  ("U2", "3"), "C4":  ("L2", "2"),       # buck input / output
    "C29": ("U11", "6"),                          # 5 V buck bootstrap
    "R24": ("U11", "4"), "R25": ("R24", "2"),     # 5 V feedback divider (chained)
    "C27": ("U11", "3"), "C28": ("L3", "2"),      # 5 V buck input / output
    # CH224K: VDD cap and its series resistor, the CFG1 voltage-select resistor
    # and the VBUS-sense resistor all belong right at the chip.
    # C1 is the largest passive in the power strip (a 6,9 mm radial
    # electrolytic), so it goes through place_near early, before the shelf
    # packer's shelves fragment the zone. Electrically it is the input bulk
    # capacitor on VBUS.
    # Its anchor moved from U2.3 to the USB-C input. C1 is a 100 uF input bulk
    # and its place is at the source, next to the connector's VBUS pin, where it
    # damps the inrush and holds the voltage while PD negotiates. At U2.3 it only
    # stole the nearest ring around the converter from the parts that genuinely
    # need proximity (bootstrap, input 100 nF, divider), while gaining nothing
    # from it itself.
    "C1":  ("J1", "A4"),
    "C22": ("U1", "1"), "R21": ("U1", "1"),
    "R22": ("U1", "8"), "R23": ("U1", "9"),
    # The crystal load capacitors anchor to THE CRYSTAL ITSELF, not to the OSC
    # pins. Anchoring them to U4.8 / U4.7 was tried and REJECTED: the capacitors
    # squeeze in between the crystal and the controller, steal the corridor the
    # button lines escape through, and Freerouting leaves BTN_CLEAR, BTN_RETURN
    # and BTN_CONFIRM unrouted in all 10 runs. The maze router then adds them at
    # the cost of 36 clearance violations. Anchored to Y1, the board is clean.
    "C6":  ("Y1", "1"), "C7":  ("Y1", "2"),      # crystal load caps
    "C10": ("U4", "18"), "C11": ("U4", "18"),    # MCP2515 VDD (pin 18)
    "C12": ("U5", "3"),  "C5":  ("U5", "3"),     # CAN transceiver VDD
    # Termination and ESD right at the OBD connector.
    #
    # The anchor is pin 14 (CANL), not pin 6 (CANH). The reason is connector
    # geometry, not electronics. The J1962F body is 43,3 x 20,7 mm and its
    # contacts lie INSIDE that body: pin 14 is 6,3 mm from the lower edge of the
    # housing, pin 6 as much as 14,9 mm. Nothing can be placed inside the body,
    # so the smallest possible distance to pin 6 is about 17 mm regardless of
    # placement. Anchoring to pin 14 pulls the pair to the connector's exit,
    # which is as close as physics allows.
    #
    # CONSEQUENCE FOR THE CHECKLIST: the criterion "termination and ESD at most
    # 5 mm from the connector" is NOT achievable now that the J1962F sits on the
    # board. It was written while J2 was still a pin header leading to a
    # front-panel connector. The realistic criterion is "immediately outside the
    # connector body, at the exit of the pair".
    #
    # The anchors are split so the chain has the PHYSICALLY CORRECT ORDER. Both
    # R7 and D1 used to anchor to the same connector pin, which made the
    # termination land closer and the ESD diode sit behind it. Measurement on the
    # first routed board showed the consequence: R7 was a node with three
    # branches and D1 hung off a 13,0 mm stub on CANH and a 4,3 mm stub on CANL.
    # The checklist requires the chain U5 -> R7 -> D1 -> J2 without branching,
    # i.e. ESD closest to the connector and termination behind it toward the
    # transceiver. So D1 now anchors to the connector and R7 to D1. The routing
    # of the pair itself is finished by route_can_chain.py after Freerouting.
    "D1":  ("J2", "14"), "R7": ("D1", "2"),
    # Fuse and TVS at pin 16 (+12 V) of the same connector. D2 ranks ahead of F1
    # in PRIORITY: the TVS has to be as close as possible to the pin it protects,
    # because every millimetre of 0,2 mm trace adds about 10 nH and raises the
    # clamping voltage on a fast strike.
    "F1":  ("J2", "16"), "D2": ("J2", "16"),
    "C13": ("U7", "8"),                          # W25Q128 VCC
    "C14": ("U9", "10"),                         # TS3USB221 VCC (pin 10!)
    "C18": ("U10", "1"), "R19": ("U10", "3"),    # SY6280 OUT / ISET
    "C23": ("U10", "5"),                         # SY6280 IN (5 V) decoupling
    "R13": ("U6", "3"),                          # EN pull-up
    "C26": ("U6", "3"),                          # EN reset RC capacitor
    "R14": ("U6", "27"),                         # IO0 (BOOT) pull-up
    "R15": ("U9", "9"),                          # USB_SEL pull-down at the mux
    "C15": ("U6", "2"), "C16": ("U6", "2"),      # ESP32-S3 3V3 decoupling
    "C19": ("U6", "2"),
    "C24": ("J5", "1"), "C25": ("J5", "1"),      # display header supply
    "R8":  ("J5", "8"),                          # display backlight resistor
    # USB: the mux and the load switch belong right at the USB-A receptacle,
    # so the D+/D- pair stays short.
    "U9":  ("J4", "3"), "U10": ("J4", "1"),

    # ══ Adjacencies required by the design review ════════════════════════════
    # The crystal and its capacitors. Y1 used to be zoned only, so it ended up
    # 7,3 mm from OSC1 and 10,9 mm from OSC2, with C7 as much as 17,1 mm from
    # OSC2. Now Y1 anchors to OSC1 and C6/C7 to Y1, which pulls the whole
    # oscillator loop together. IMPORTANT: Y1 must appear in the component table
    # BEFORE C6/C7, because step 3 follows table order and C6/C7 anchor to an
    # already placed Y1. That holds (Y1, then C6, then C7).
    "Y1": ("U4", "8"),
    # Inductors at the SW pin. SW is the node with the highest dV/dt on the
    # board: on the earlier outline L3 sat 20,9 mm from the pin, i.e. a 42 mm run.
    "L2": ("U2", "2"), "L3": ("U11", "2"),
    # The SPI series resistors go right at the module's output pin, otherwise
    # they are pointless: the termination must be at the source, not somewhere
    # along the way.
    "R30": ("U6", "20"), "R31": ("U6", "19"),
    # The encoder RC filter goes right at the encoder, so it catches the contact
    # bounce before it enters the trace. Pull-up and capacitor each at their own
    # contact. Since the series resistor R38-R40 now sits between the contact and
    # the filter, the pull-up and the capacitor anchor to ITS output pad rather
    # than to the contact. That keeps the whole trio (contact, series resistor,
    # filter) together and in the electrically correct order.
    "R38": ("ENC1", "A"),  "R39": ("ENC1", "B"),  "R40": ("ENC1", "S1"),
    "R32": ("R38", "2"),   "C31": ("R38", "2"),
    "R33": ("R39", "2"),   "C32": ("R39", "2"),
    "R34": ("R40", "2"),   "C33": ("R40", "2"),
    # The other end of the same line: a capacitor right at the module input pin.
    # U6 pin 39 = GPIO1 (ENC_A), 31 = GPIO38 (ENC_B), 32 = GPIO39 (push-button).
    "C34": ("U6", "39"), "C35": ("U6", "31"), "C36": ("U6", "32"),
    # Blocking diode next to the fuse, so the 12 V branch stays one short line
    # VBUS -> F1 -> D3 -> pin 16.
    "D3": ("F1", "2"),
    # Test points: each next to a pad of its own net, to keep the stub short.
    # The CAN pair goes onto the CAN chain line itself rather than to the far end
    # of the board. SPI is tapped at the flash U7, which sits mid-bus. The
    # supplies are tapped at the display header, VBUS at the fuse input.
    "TP1": ("J5", "1"), "TP2": ("J5", "2"),
    # The CAN pair test points anchor to the ESD diode, not to the termination.
    # D1's pads are 1,9 mm apart, so both points land on the same side of the
    # pair and the chain stays parallel. Anchored to R7, whose leads are 10,16 mm
    # apart, TP3 ended up east and TP4 north-west of the termination, so CANH had
    # to run 4,5 mm east and come back while CANL went straight. That alone put
    # the length difference of the pair at 38 mm.
    "TP3": ("D1", "1"), "TP4": ("D1", "2"),
    "TP5": ("U7", "5"), "TP6": ("U7", "2"), "TP7": ("U7", "6"),
    # ══ Anchors of the parts added in the second review ══════════════════════
    # Bulk capacitor at the switch's INPUT pin (pin 5), not the output.
    "C37": ("U10", "5"),
    # ESD arrays right at the connector: the protection only means something if
    # there is as little copper as possible ahead of it on the way in.
    "D4":  ("J1", "A6"), "D5": ("J4", "3"),
    # Chip-select pull-ups, each next to its own slave device.
    "R35": ("U4", "16"), "R36": ("U7", "1"),
    # Pull-down right at the switch's EN pin.
    "R37": ("U10", "4"),
    "TP8": ("F1", "1"),
}

# The packer is given the real board dimensions. They used to be hard-coded in
# place.py, so enlarging the board had no effect at all.
placer = Placer(W, H)

# ── Frozen placement ─────────────────────────────────────────────────────────
# The coordinates of all parts can come from the last fully routed, DRC-clean
# board instead of from the packer. See the extensive reasoning in the module
# itself - in short, the packer is greedy, and introducing a single new resistor
# (R17B) reshuffled half the power zone and broke the routing. If LOCKED is
# missing or empty, everything falls back to the old behaviour (the packer
# arranges the board itself).
try:
    from placement_locked import LOCKED
except ImportError:
    LOCKED = {}
# A locked part is by definition also pinned: the packer may neither move it nor
# arrange neighbours on top of it.
FIXED = FIXED | set(LOCKED)

# ── Smallest drill accepted on this board ────────────────────────────────────
#
# 0,30 mm, which is the cheap end of every fab house's standard two-layer
# process. Nothing on the board asks for less: the default netclass via is
# 0,60/0,30 mm and the widest is 0,80/0,40 mm.
#
# The one exception used to come in from outside. KiCad's ESP32-S3-WROOM-1
# footprint stitches the thermal pad (pad 41, EPAD, GND) with 12 vias drilled
# 0,20 mm, and until 11.08.2026. the board simply carried them: m_MinThroughDrill
# was lowered to 0,2 mm so DRC would accept the imported footprint. Those 12
# holes were the only sub-0,30 mm holes out of 326, and on JLCPCB they alone
# pushed the order into the fine-drill surcharge tier.
#
# Widening them is free. The pad stays 0,60 mm, so the annular ring goes from
# 0,20 to 0,15 mm, still above the 0,13 mm minimum. The nearest two holes in the
# array sit 0,99 mm apart (0,7 mm grid, staggered), so the edge-to-edge gap goes
# from 0,79 to 0,69 mm, far above the 0,25 mm hole-to-hole rule. Thermally it is
# an improvement: a wider barrel is more plated copper between the module's pad
# and the bottom pour. Nothing moves, so the board does not need re-routing.
#
# The floor is applied to every loaded footprint rather than to U6 by name, so
# the next imported library footprint cannot quietly reintroduce the surcharge.
MIN_DRILL_MM = 0.3


def enforce_min_drill(fp):
    """Widen any plated hole in `fp` that is drilled below MIN_DRILL_MM.
    Pad sizes are untouched, so only the barrel grows. Returns the number of
    holes changed."""
    floor = pcbnew.FromMM(MIN_DRILL_MM)
    changed = 0
    for pad in fp.Pads():
        if pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
            continue
        d = pad.GetDrillSize()
        # Oval drills are handled per axis: only the axis below the floor grows.
        nx, ny = max(d.x, floor), max(d.y, floor)
        if (nx, ny) != (d.x, d.y):
            pad.SetDrillSize(pcbnew.VECTOR2I(nx, ny))
            changed += 1
    return changed


missing, unplaced = [], []
loaded = []
widened = 0
for ref, lib, fpname, x, y, rot, value, padmap in COMPONENTS:
    if ref in LOCKED:
        x, y, rot = LOCKED[ref]
    fp = None
    for root in (FP_ROOT, LOCAL_FP):
        libdir = os.path.join(root, lib + ".pretty")
        if not os.path.isdir(libdir):
            continue
        fp = pcbnew.FootprintLoad(libdir, fpname)
        if fp is not None:
            break
    if fp is None:
        missing.append("%s (%s:%s)" % (ref, lib, fpname))
        continue
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetOrientationDegrees(rot)
    if ref in OPTIONAL:
        fp.SetDNP(True)
    widened += enforce_min_drill(fp)
    loaded.append((ref, fp, x, y, padmap))

if widened:
    print("drills widened to %.2f mm: %d" % (MIN_DRILL_MM, widened))

if missing:
    print("MISSING FOOTPRINTS:", missing)
    sys.exit(1)

def courtyard_shape(fp):
    """(w, h, ox, oy): size of the courtyard and the offset of its centre
    from the footprint origin, in board mm (y up)."""
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if bb.GetWidth() == 0:
        bb = fp.GetBoundingBox(False, False)
    w = pcbnew.ToMM(bb.GetWidth())
    h = pcbnew.ToMM(bb.GetHeight())
    pos = fp.GetPosition()
    cx = pcbnew.ToMM(bb.GetCenter().x) - pcbnew.ToMM(pos.x)
    cy = -(pcbnew.ToMM(bb.GetCenter().y) - pcbnew.ToMM(pos.y))   # y up
    return (w, h, cx, cy)

def courtyard_area(fp):
    w, h, _, _ = courtyard_shape(fp)
    return w * h

def pads_bbox(fp):
    xs, ys = [], []
    for pad in fp.Pads():
        p = pad.GetPosition()
        s = pad.GetSize()
        px = pcbnew.ToMM(p.x) - OX
        py = OY - pcbnew.ToMM(p.y)
        xs += [px - pcbnew.ToMM(s.x) / 2, px + pcbnew.ToMM(s.x) / 2]
        ys += [py - pcbnew.ToMM(s.y) / 2, py + pcbnew.ToMM(s.y) / 2]
    return min(xs), min(ys), max(xs), max(ys)

# 0) The board title's spot is reserved BEFORE packing.
#
# The title sits at (70,5, 7,55), where it was placed by hand. That used to be a
# wish only: the packer knew nothing about it, so the first part landing in that
# band pushed the title into a corner. Exactly that happened when R36 (the
# CS_FLASH pull-up) was added: it took (55,4, 11,7) and the title ended up in the
# top right corner. The block is therefore reserved like any other occupied
# rectangle. The numbers must match those in the "board title" section below.
#
# Two lines. A third line carrying the year was removed by hand in KiCad, so
# the script no longer creates it.
# The text is defined HERE rather than below next to the drawing code, because
# the same block width is needed both to reserve the space and to draw it. Two
# separate numbers would drift apart the first time the title changed.
TITLE = "OBD-II SIMULATOR v0.7"
SUB1 = "Designed by Filip Raic"
blk_w = max(len(TITLE) * 1.30, len(SUB1) * 0.85) + 2.0
TITLE_SPOT = (70.5, 7.55)
TITLE_BLOCK = (blk_w, 6.0)        # width x height of the two-line block
placer.block(TITLE_SPOT[0] - TITLE_BLOCK[0] / 2, TITLE_SPOT[1] - TITLE_BLOCK[1] / 2,
             TITLE_SPOT[0] + TITLE_BLOCK[0] / 2, TITLE_SPOT[1] + TITLE_BLOCK[1] / 2)

# 1) fixed parts first - they define the reserved areas
for ref, fp, x, y, padmap in loaded:
    if ref not in FIXED:
        continue
    fp.SetPosition(P(x, y))
    if ref == "U6":
        # Reserve the module body. The footprint's own (Espressif) rule area
        # is dropped in favour of the documented 5 mm keep-out - see the
        # trade-off note at the U6 entry above. The courtyard, which spans the
        # same RF area, is redrawn around the module body so it reflects the
        # space the part actually occupies.
        for z in list(fp.Zones()):
            if z.GetIsRuleArea():
                fp.Remove(z)
        # BUG FIXED HERE.
        #
        # This used to take the extent of the PADS (`pads_bbox`), and that was
        # wrong: the antenna end of the module has no pad at all, so the
        # courtyard came out 6,5 mm shorter than the module itself (pads reach
        # x = 43,7, the body x = 50,8). To the packer that piece of the module
        # looked like empty space.
        #
        # The antenna keep-out block (44,8 .. 50,0 in x, 29 .. 43 in y) covered
        # only the middle of that piece, so the corners below y = 29 and above
        # y = 43 stayed free. R25 ended up there and its courtyard overlapped the
        # real module body by 1,24 x 0,83 mm - a 2,5 mm THT resistor sitting
        # under the module PCB. DRC did not report it, because DRC compares
        # courtyards and the courtyard was too short.
        #
        # Now the REAL BODY OUTLINE from the F.Fab layer is used, so both the
        # courtyard and the block are as large as the module.
        # Do NOT use BOX2I and its Merge. The first attempt did, and gave two
        # different results for the same board in two consecutive runs (50,80 mm
        # once, 44,01 mm in x the next time), because GetBoundingBox() through
        # SWIG returns a temporary object that does not survive the next call.
        # Here every extent is converted to plain numbers immediately.
        fx, fy = [], []
        for g in fp.GraphicalItems():
            if g.GetLayer() != pcbnew.F_Fab:
                continue
            gb = g.GetBoundingBox()
            gx0 = pcbnew.ToMM(gb.GetX())
            gy0 = pcbnew.ToMM(gb.GetY())
            gw = pcbnew.ToMM(gb.GetWidth())
            gh = pcbnew.ToMM(gb.GetHeight())
            fx += [gx0 - OX, gx0 + gw - OX]
            fy += [OY - gy0, OY - (gy0 + gh)]
        px1, py1, px2, py2 = pads_bbox(fp)
        if fx:
            x1, x2 = min(fx + [px1]), max(fx + [px2])
            y1, y2 = min(fy + [py1]), max(fy + [py2])
        else:
            x1, y1, x2, y2 = px1, py1, px2, py2      # fallback, old behaviour
        print("  U6 body extent: x %.2f..%.2f  y %.2f..%.2f" % (x1, x2, y1, y2))
        for g in list(fp.GraphicalItems()):
            if g.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                fp.Remove(g)
        crt = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_RECTANGLE)
        crt.SetStart(P(x1 - 0.25, y1 - 0.25))
        crt.SetEnd(P(x2 + 0.25, y2 + 0.25))
        crt.SetLayer(pcbnew.F_CrtYd)
        crt.SetWidth(pcbnew.FromMM(0.05))
        fp.Add(crt)
        placer.block(x1 - 0.5, y1 - 0.5, x2 + 0.5, y2 + 0.5)
        placer.block(44.8, 29, 50.0, 43)      # documented antenna keep-out
    else:
        placer.block_fp(courtyard_shape(fp), x, y)
        # Some footprints (SW_PUSH_6mm, for instance) have pads OUTSIDE their own
        # courtyard, so the packer would place a neighbour right on top of a pad.
        # The real pad extent is blocked too, not just the courtyard.
        px1, py1, px2, py2 = pads_bbox(fp)
        placer.block(px1 - 0.4, py1 - 0.4, px2 + 0.4, py2 + 0.4)

# 2) pack the zoned parts, largest first (better shelf utilisation)
pos_of = {}
for ref, fp, x, y, padmap in loaded:
    if ref in FIXED:
        pos_of[ref] = (x, y)

zoned = [t for t in loaded if t[0] in ZONE_OF]
zoned.sort(key=lambda t: -courtyard_area(t[1]))

# Anchors (the devices that decoupling caps and pull-ups must hug) go down
# first, then step 3 gets first pick of the space around them, and only then
# does the rest of the zone get packed. Placing the caps last leaves them
# 8-12 mm from the supply pin, which defeats the point of decoupling.
ANCHORS = {a for a, _ in NEAR_OF.values()}

def place_zoned(items):
    for ref, fp, x, y, padmap in items:
        if ref in FIXED or ref in pos_of:   # fixed parts keep table coordinates
            continue
        shape = courtyard_shape(fp)
        zone = ZONES[ZONE_OF[ref]]
        pos = placer.place(shape, zone)
        if pos is None:
            # Fallback: let the part spill just outside its zone instead of
            # failing the whole build. The shelves fragment when the sizes are
            # mixed, so the largest remaining part can be left without a spot
            # even though the board still has room.
            zx1, zy1, zx2, zy2 = zone
            pos = placer.place_near(shape, (zx1 + zx2) / 2.0, (zy1 + zy2) / 2.0, max_r=30.0)
            if pos is not None:
                print("  spill %-4s outside zone %s" % (ref, ZONE_OF[ref]))
        if pos is None:
            unplaced.append("%s (%.1f x %.1f in %s)" % (ref, shape[0], shape[1], ZONE_OF[ref]))
            continue
        fp.SetPosition(P(pos[0], pos[1]))
        pos_of[ref] = pos

# Anchors that are themselves in NEAR_OF (Y1, L2, L3, U9, U10) skip this step:
# step 3 places them next to their own anchor. They used to go through both
# steps, so the first one reserved a spot in the zone that the second never
# used, and that blocked rectangle stayed occupied until the end of packing.
place_zoned([t for t in zoned if t[0] in ANCHORS and t[0] not in NEAR_OF])

# 3) place the "must be adjacent" parts as close to their anchor pad as possible
fp_by_ref = {ref: fp for ref, fp, _, _, _ in loaded}
# Net per pad, so step 3 knows WHICH pad of a part faces its anchor.
padmap_of = {ref: pm for ref, _, _, _, pm in loaded}
near_dist = {}

def pad_pos(ref, num):
    for pad in fp_by_ref[ref].Pads():
        if pad.GetNumber() == num:
            p = pad.GetPosition()
            return (pcbnew.ToMM(p.x) - OX, OY - pcbnew.ToMM(p.y))
    return None

# THE ORDER IS ELECTRICAL, NOT TABLE ORDER.
#
# Step 3 used to follow the order the parts appear in the table, so whichever
# part reached an anchor first took the closest spot whether it needed it or not.
# Nine parts compete around a single SOT-23 converter (bootstrap, input and
# output capacitor, inductor, three divider members, bulk), and a ring of 12 mm
# radius offers about 490 mm2 - just enough for all of them, but only if the most
# important ones pick first. Under table order C1 picked first, a 100 uF bulk
# capacitor to which distance means nothing at all, while the bootstrap C21 ended
# up 12,5 mm away.
#
# Hence parts go by priority. The rule: the faster the loop, the earlier it goes.
PRIORITY = [
    # 0. Anchors that are themselves in NEAR_OF go first, ahead of their
    #    dependants. U9 and U10 anchor to the USB-A receptacle, which is a pinned
    #    part, so nothing stops them from being first, and their decoupling
    #    capacitors (C14, C18, C23) plus R15/R19 anchor to them.
    "U9", "U10",
    # 1. Bootstrap: the BST-SW loop charges the high-side transistor and must be
    #    as small as possible.
    "C21", "C29",
    # 2. Input bulk at the USB-C connector's VBUS pin (see NEAR_OF).
    "C1",
    # 2. Inductor: SW is the node with the highest dV/dt, its run must be short
    #    and wide.
    "L2", "L3",
    # 3. Input capacitors: the VIN-GND loop is the converter's "hot loop", it
    #    carries the entire switching current and is the largest radiator. It
    #    goes before the feedback network: swapping the order was tried and gave
    #    a 2 mm better FB at the cost of a 4 mm worse input, which is a bad trade.
    "C20", "C3", "C27",
    # 4. Feedback: a high-impedance node next to the switching stage. Chained, so
    #    each member sits next to its predecessor (see NEAR_OF).
    "R16", "R17A", "R17B", "R24", "R25",
    # 5. Module decoupling capacitors. They go early because they compete with
    #    the power section for the space around pin 2, and the module has the
    #    largest current steps on the board. They used to sit 14 and 18,5 mm away.
    "C15", "C16",
    # 6. Oscillator: the most sensitive analogue node on the board. Y1 first,
    #    then its capacitors, which anchor to Y1.
    "Y1", "C6", "C7",
    # 7. Output capacitors and the SPI series termination.
    "C4", "C28", "R30", "R31",
    # 7. CAN input and the 12 V branch at the connector.
    #    D1 picks first, because the ESD diode has to be closest to the
    #    connector, and only then the termination R7, which anchors to D1. In the
    #    12 V branch D2 picks first for the same reason (TVS next to the pin it
    #    protects), then F1 and D3.
    "D1", "R7", "D2", "F1", "D3",
    # 7b. ESD arrays of both USB connectors - same logic as D1 and D2.
    "D4", "D5",
    # 8. Decoupling capacitors at the supply pins.
    "C10", "C11", "C12", "C13", "C14", "C5",
    # 8b. Bulk capacitor at the switch input and its pull-down.
    "C37", "R37",
    # 9. Encoder filter. The series resistor first, because the pull-up and the
    #    capacitor anchor to its output pad. Then the capacitor (it is the filter
    #    and has to be at the contact), then the pull-up, which may sit further.
    "R38", "R39", "R40",
    "C31", "C32", "C33", "R32", "R33", "R34",
    # 9b. Chip-select pull-ups.
    "R35", "R36",
    # 10. Test points last. They are small (a 2 x 2 mm pad) and fit into whatever
    #     gap remains, and no other part may be pushed further from its chip on
    #     their account.
    "TP1", "TP2", "TP3", "TP4", "TP5", "TP6", "TP7", "TP8",
    # 11. The encoder capacitors at the module pins go LAST.
    #     The first attempt put them straight after the encoder filter, i.e.
    #     early, and they then sat right against the module's pad row and closed
    #     the corridor the button lines escape through: Freerouting left
    #     BTN_CLEAR and CS_TFT unrouted in all 10 runs. Left until the end they
    #     pick from whatever remains, which is still within a few millimetres of
    #     the pin, because they are small (a 4,3 mm disc).
    "C34", "C35", "C36",
]
_near_order = [r for r in PRIORITY if r in NEAR_OF]
_near_order += [t[0] for t in loaded if t[0] in NEAR_OF and t[0] not in _near_order]
# Safety check: an anchor that is itself in NEAR_OF must be placed before its
# dependant, otherwise the dependant anchors to a part that is not placed yet.
for _r in _near_order:
    _a = NEAR_OF[_r][0]
    if _a in _near_order and _near_order.index(_a) > _near_order.index(_r):
        print("ERROR: %s anchors to %s, but %s comes later" % (_r, _a, _a))
        sys.exit(1)

# NUDGE: a fine offset applied to an already placed part, in millimetres.
#
# WHY IT EXISTS. place_near looks for the nearest FREE spot, but it does not know
# where the router will later pull its traces. A part can end up in a pocket the
# ground pour no longer reaches after routing, leaving its ground pad
# unconnected. That is exactly what happened to C34: its GND pad ended up 0,23 mm
# from the CS_FLASH trace on the bottom layer, which cut it off from the pour.
#
# The same problem used to be solved by nudging C24 by 1 mm by hand, written into
# placement_locked.py. This is the same thing, except the offset does not have to
# overwrite the whole coordinate: it is enough to say how far and which way.
#
# Values can also be swept without touching the file, through environment
# variables (C34_DX / C34_DY, for instance), the same pattern as F1_X / D2_X.
NUDGE = {}
for _r in ("C34", "C35", "C36"):
    _dx = float(os.environ.get(_r + "_DX", "0"))
    _dy = float(os.environ.get(_r + "_DY", "0"))
    if _dx or _dy:
        NUDGE[_r] = (_dx, _dy)
# C34 has to move 2 mm to the left. Without that offset it ends up in a pocket
# between the SCK and CS_FLASH traces, where the ground pour does not reach its
# ground pad.
#
# Every candidate was tried through the whole chain:
#   no offset -> 45 violations
#   (0, -2)   -> 7 unrouted nets, 16 violations
#   (0, +2)   -> 3 unrouted nets, 9 violations
#   (-2, 0)   -> 0 unrouted, 0 unconnected
#
# NOTE ON ZERO: an offset of (0, 0) through the environment variables does NOT
# cancel this default, because an empty value is indistinguishable from an unset
# one. To try it without an offset, comment out the line below.
NUDGE.setdefault("C34", (-2.0, 0.0))

for ref in _near_order:
    fp = fp_by_ref[ref]
    if ref in FIXED:
        # Step 3 used to override pinned parts too, which made the table
        # coordinates of R24/R25 a dead letter. Pinned means pinned - for such a
        # part the neighbourhood is chosen by hand.
        continue
    aref, anum = NEAR_OF[ref]
    ap = pad_pos(aref, anum)
    if ap is None:
        unplaced.append("%s (anchor pad %s.%s not found)" % (ref, aref, anum))
        continue
    # All four rotations are tried, and the distance measured is the one from the
    # anchor pin to whichever PAD of this part shares its net - not to the
    # footprint origin.
    #
    # The difference is not cosmetic. A flat resistor is 10,16 mm long between
    # its holes, so its origin (pad 1) sits at one end. When R16 anchors to the
    # converter's FB pin and it is pad 2 that connects to FB, measuring from the
    # origin says 11,5 mm while the real run is 21,1 mm - the resistor is turned
    # with the wrong end toward the chip. The same holds for every divider,
    # inductor and bootstrap capacitor, i.e. for exactly the parts whose trace
    # length was the problem in the first place.
    anchor_net = padmap_of.get(aref, {}).get(anum)
    my_pads = [n for n, nn in padmap_of.get(ref, {}).items() if nn == anchor_net] \
        if anchor_net else []
    best = None
    for rot_try in (0, 90, 180, 270):
        fp.SetOrientationDegrees(rot_try)
        shape = courtyard_shape(fp)
        cand = placer.place_near(shape, ap[0], ap[1], max_r=26.0, block=False)
        if cand is None:
            continue
        fp.SetPosition(P(cand[0], cand[1]))
        if my_pads:
            ds = []
            for pnum in my_pads:
                pp = pad_pos(ref, pnum)
                if pp is not None:
                    ds.append(((pp[0] - ap[0]) ** 2 + (pp[1] - ap[1]) ** 2) ** 0.5)
            d = min(ds) if ds else 1e9
        else:
            d = ((cand[0] - ap[0]) ** 2 + (cand[1] - ap[1]) ** 2) ** 0.5
        if best is None or d < best[0] - 1e-9:
            best = (d, rot_try, cand, shape)
    pos = None
    if best is not None:
        _, rot_try, pos, shape = best
        fp.SetOrientationDegrees(rot_try)
        placer.block_fp(shape, pos[0], pos[1])
    if pos is None and ref in ZONE_OF:
        fp.SetOrientationDegrees(0)
        # Fallback: if there is no room right at the pin (THT passives on a 5 mm
        # pitch take up considerably more space), place the part anywhere in its
        # zone. For bulk capacitors a larger distance is acceptable.
        pos = placer.place(courtyard_shape(fp), ZONES[ZONE_OF[ref]])
        if pos is not None:
            print("  fallback %-4s -> zone %s (no room next to %s.%s)"
                  % (ref, ZONE_OF[ref], aref, anum))
    if pos is None:
        unplaced.append("%s (no room near %s.%s)" % (ref, aref, anum))
        continue
    if ref in NUDGE:
        ndx, ndy = NUDGE[ref]
        pos = (pos[0] + ndx, pos[1] + ndy)
        placer.block_fp(courtyard_shape(fp), pos[0], pos[1])
        print("  nudge %-4s by (%+.1f, %+.1f) mm" % (ref, ndx, ndy))
    fp.SetPosition(P(pos[0], pos[1]))
    pos_of[ref] = pos
    d = ((pos[0] - ap[0]) ** 2 + (pos[1] - ap[1]) ** 2) ** 0.5
    dp = None
    for pnum in my_pads:
        pp = pad_pos(ref, pnum)
        if pp is not None:
            dd = ((pp[0] - ap[0]) ** 2 + (pp[1] - ap[1]) ** 2) ** 0.5
            dp = dd if dp is None else min(dp, dd)
    near_dist[ref] = (aref, anum, dp if dp is not None else d)
    print("  near %-4s -> %s.%-3s  pad-pad %s" %
          (ref, aref, anum, ("%.1f mm" % dp) if dp is not None else "%.1f mm (origin)" % d))

# 4) everything else in its zone, around what is already down
place_zoned(zoned)

if unplaced:
    print("UNPLACED:", unplaced)
    sys.exit(1)

# 3) add everything to the board and assign nets
for ref, fp, x, y, padmap in loaded:
    board.Add(fp)
    # Reference designators (R1, C3, U6 ...) go on the SILKSCREEN, because the
    # board is hand-soldered and the components have to be findable without
    # opening the project. The text is positioned below (place_silk_refs) so it
    # neither lands on a pad nor overlaps another designator. The value stays on
    # the fabrication layer.
    fp.Value().SetLayer(pcbnew.F_Fab)
    fp.Value().SetVisible(False)
    for pad in fp.Pads():
        num = pad.GetNumber()
        # None = pad deliberately left unconnected (e.g. CH224K CFG2/CFG3/PG)
        if num in padmap and padmap[num] is not None:
            pad.SetNet(nets[padmap[num]])

# ── Silkscreen: reference designators without overlaps ───────────────────────
# For every footprint a handful of candidate positions around the body are tried
# (above, below, left, right, then further out) and the first one is taken that
# lands neither on a pad, nor on an already placed designator, nor off the board.
TXT_H = 0.9          # letter height (mm)
TXT_T = 0.15         # stroke thickness (mm)
CHAR_W = 0.72        # approximate character width at that height

pad_boxes = []
for fp in board.GetFootprints():
    for pad in fp.Pads():
        p, s = pad.GetPosition(), pad.GetSize()
        px = pcbnew.ToMM(p.x) - OX
        py = OY - pcbnew.ToMM(p.y)
        hw = pcbnew.ToMM(s.x) / 2 + 0.45
        hh = pcbnew.ToMM(s.y) / 2 + 0.45
        pad_boxes.append((px - hw, py - hh, px + hw, py + hh))
    # The footprint's own silkscreen (body outlines, pin 1 markers) is an
    # obstacle too - otherwise the designators land on top of the component
    # drawing.
    for g in fp.GraphicalItems():
        if g.GetLayer() != pcbnew.F_SilkS:
            continue
        bb = g.GetBoundingBox()
        gx1 = pcbnew.ToMM(bb.GetX()) - OX
        gx2 = pcbnew.ToMM(bb.GetX() + bb.GetWidth()) - OX
        gy1 = OY - pcbnew.ToMM(bb.GetY() + bb.GetHeight())
        gy2 = OY - pcbnew.ToMM(bb.GetY())
        pad_boxes.append((gx1 - 0.1, gy1 - 0.1, gx2 + 0.1, gy2 + 0.1))

text_boxes = []

def box_free(b):
    x1, y1, x2, y2 = b
    if x1 < 0.5 or y1 < 0.5 or x2 > W - 0.5 or y2 > H - 0.5:
        return False
    for (a1, b1, a2, b2) in pad_boxes:
        if x1 < a2 and a1 < x2 and y1 < b2 and b1 < y2:
            return False
    for (a1, b1, a2, b2) in text_boxes:
        if x1 < a2 and a1 < x2 and y1 < b2 and b1 < y2:
            return False
    return True

def place_silk_refs():
    placed, fallback = 0, 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith("H"):          # mounting holes carry no designator
            fp.Reference().SetVisible(False)
            continue
        rf = fp.Reference()
        rf.SetLayer(pcbnew.F_SilkS)
        rf.SetVisible(True)
        rf.SetTextSize(pcbnew.VECTOR2I_MM(TXT_H, TXT_H))
        rf.SetTextThickness(pcbnew.FromMM(TXT_T))
        rf.SetKeepUpright(True)

        tw = len(ref) * CHAR_W + 0.3
        th = TXT_H + 0.3
        cy_bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if cy_bb.GetWidth() == 0:
            cy_bb = fp.GetBoundingBox(False, False)
        cx = pcbnew.ToMM(cy_bb.GetCenter().x) - OX
        cyy = OY - pcbnew.ToMM(cy_bb.GetCenter().y)
        hw = pcbnew.ToMM(cy_bb.GetWidth()) / 2
        hh = pcbnew.ToMM(cy_bb.GetHeight()) / 2

        def search(tw, th):
            for d in (0.7, 1.4, 2.2, 3.2, 4.4, 5.6, 7.0, 8.5):
                dd = d * 0.7071
                cands = [(cx, cyy + hh + th / 2 + d),      # above
                         (cx, cyy - hh - th / 2 - d),      # below
                         (cx + hw + tw / 2 + d, cyy),      # right
                         (cx - hw - tw / 2 - d, cyy),      # left
                         (cx + hw + tw / 2 + dd, cyy + hh + th / 2 + dd),
                         (cx - hw - tw / 2 - dd, cyy + hh + th / 2 + dd),
                         (cx + hw + tw / 2 + dd, cyy - hh - th / 2 - dd),
                         (cx - hw - tw / 2 - dd, cyy - hh - th / 2 - dd)]
                for (tx, ty) in cands:
                    b = (tx - tw / 2, ty - th / 2, tx + tw / 2, ty + th / 2)
                    if box_free(b):
                        return (tx, ty, b)
            return None

        best = search(tw, th)
        if best is None:
            # This case used to leave the designator at the centre of the part,
            # where it regularly ends up over a pad and DRC reports it as
            # silk_over_copper. Smaller letters are tried first, because a 0,6 mm
            # designator is still legible and fits between the pads.
            small_h = TXT_H * 0.7
            tw_s = len(ref) * CHAR_W * 0.7 + 0.3
            th_s = small_h + 0.3
            best = search(tw_s, th_s)
            if best is not None:
                rf.SetTextSize(pcbnew.VECTOR2I_MM(small_h, small_h))
                rf.SetTextThickness(pcbnew.FromMM(TXT_T * 0.8))
        if best is None:                  # no room - put it at the part centre
            tx, ty = cx, cyy
            b = (tx - tw / 2, ty - th / 2, tx + tw / 2, ty + th / 2)
            fallback += 1
        else:
            tx, ty, b = best
            placed += 1
        rf.SetPosition(P(tx, ty))
        text_boxes.append(b)
    print("silk designators: %d placed without a clash, %d on the part body" % (placed, fallback))

place_silk_refs()

# ── Silkscreen: board title ──────────────────────────────────────────────────
def silk_text(txt, x, y, size, thick, layer=pcbnew.F_SilkS, mirror=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(txt)
    t.SetLayer(layer)
    t.SetPosition(P(x, y))
    t.SetTextSize(pcbnew.VECTOR2I_MM(size, size))
    t.SetTextThickness(pcbnew.FromMM(thick))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    t.SetMirrored(mirror)
    board.Add(t)
    return t

def find_free_spot(w, h):
    """First free rectangle (w x h) for a block of text. Searches top down,
    because the upper part of the board is less crowded, and left to right
    within a row."""
    y = H - 2 - h / 2.0
    while y > 2 + h / 2.0:
        x = 2 + w / 2.0
        while x < W - 2 - w / 2.0:
            if box_free((x - w / 2, y - h / 2, x + w / 2, y + h / 2)):
                return (x, y)
            x += 1.0
        y -= 1.0
    return None

# TITLE, SUB1 and blk_w are defined above, together with the reservation in the
# packer.
#
# The block was moved to this spot by hand (top line at (70,5, 9,0)), so that is
# taken as the preferred position. The automatic search for a free band stays as
# a fallback, in case some future placement change occupies that spot - the title
# then will not end up on top of components. Since the same spot is already
# reserved in the packer (TITLE_SPOT), the band is guaranteed free and the
# alternative-position branch is only a safety net.
PREF = TITLE_SPOT                      # centre of the two-line block
if box_free((PREF[0] - blk_w / 2, PREF[1] - 3.0,
             PREF[0] + blk_w / 2, PREF[1] + 3.0)):
    spot = PREF
    print("title at the preferred (hand-picked) spot")
else:
    spot = find_free_spot(blk_w, 6.0)
    print("WARNING: the preferred title spot is taken, searching for a free one")

if spot is None:
    print("WARNING: no room for the title on the top side")
else:
    tx, ty = spot
    silk_text(TITLE, tx, ty + 1.45, 1.8, 0.30)
    silk_text(SUB1,  tx, ty - 1.45, 1.2, 0.22)
    text_boxes.append((tx - blk_w / 2, ty - 3.0, tx + blk_w / 2, ty + 3.0))
    print("title at (%.1f, %.1f), block width %.1f mm" % (tx, ty, blk_w))

# The bottom side carries the same title, mirrored so it reads from below.
# It used to be fixed at the middle of the board (W/2, 52), where it fell across
# the bottom of THT pads (J5, L2, L3, C26, R26) - nine silk_over_copper reports.
# Now a free spot is searched for, and if there is none for the large letters the
# title is shrunk.
# For the bottom side only pads that HAVE copper on B.Cu get in the way, i.e. THT
# pads and vias. Top-side SMD pads do not block the bottom silkscreen, so a
# separate occupancy map is built for it - otherwise the title needlessly drops
# to the smallest size.
_bot_boxes = []
for _fp in board.GetFootprints():
    for _pad in _fp.Pads():
        if not _pad.GetLayerSet().Contains(pcbnew.B_Cu):
            continue
        _pp, _ps = _pad.GetPosition(), _pad.GetSize()
        _px = pcbnew.ToMM(_pp.x) - OX
        _py = OY - pcbnew.ToMM(_pp.y)
        _hw = pcbnew.ToMM(_ps.x) / 2 + 0.5
        _hh = pcbnew.ToMM(_ps.y) / 2 + 0.5
        _bot_boxes.append((_px - _hw, _py - _hh, _px + _hw, _py + _hh))

def _bot_free(b):
    x1, y1, x2, y2 = b
    if x1 < 1.0 or y1 < 1.0 or x2 > W - 1.0 or y2 > H - 1.0:
        return False
    for (a1, b1, a2, b2) in _bot_boxes:
        if x1 < a2 and a1 < x2 and y1 < b2 and b1 < y2:
            return False
    return True

def _find_bot_spot(w, h):
    y = H - 2 - h / 2.0
    while y > 2 + h / 2.0:
        x = 2 + w / 2.0
        while x < W - 2 - w / 2.0:
            if _bot_free((x - w / 2, y - h / 2, x + w / 2, y + h / 2)):
                return (x, y)
            x += 1.0
        y -= 1.0
    return None

for _size, _sub in ((4.0, 2.6), (3.2, 2.1), (2.5, 1.6), (2.0, 1.3)):
    _bw = max(len(TITLE) * _size * 0.85, len(SUB1) * _sub * 0.85) + 2.0
    _bh = _size + _sub + 3.0
    _spot = _find_bot_spot(_bw, _bh)
    if _spot is not None:
        break
if _spot is None:
    print("WARNING: no room for the title on the bottom side")
else:
    _bx, _by = _spot
    silk_text(TITLE, _bx, _by + _bh / 4.0, _size, _size * 0.15, pcbnew.B_SilkS, True)
    silk_text(SUB1, _bx, _by - _bh / 4.0, _sub, _sub * 0.15, pcbnew.B_SilkS, True)
    print("bottom-side title at (%.1f, %.1f), letters %.1f mm" % (_bx, _by, _size))

# Silkscreen that runs past the board outline (the shell of the USB-A connector
# J4 overhangs the bottom edge) is clipped to the edge. The fabricator would trim
# it anyway, but DRC reports it as silk_edge_clearance.
def clip_silk_to_board():
    MARGIN = 0.2
    x1b, y1b = OX + MARGIN, OY - H + MARGIN
    x2b, y2b = OX + W - MARGIN, OY - MARGIN

    def inside(px, py):
        return x1b <= px <= x2b and y1b <= py <= y2b

    clipped = removed = 0
    for fp in board.GetFootprints():
        for g in list(fp.GraphicalItems()):
            if g.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                continue
            if g.GetShape() != pcbnew.SHAPE_T_SEGMENT:
                continue
            ax, ay = pcbnew.ToMM(g.GetStart().x), pcbnew.ToMM(g.GetStart().y)
            bx, by = pcbnew.ToMM(g.GetEnd().x), pcbnew.ToMM(g.GetEnd().y)
            ia, ib = inside(ax, ay), inside(bx, by)
            if ia and ib:
                continue
            if not ia and not ib:
                fp.Remove(g)
                removed += 1
                continue
            # one end is outside: find the point on the edge by bisection
            if ia:
                kx, ky, ox_, oy_ = ax, ay, bx, by
            else:
                kx, ky, ox_, oy_ = bx, by, ax, ay
            for _ in range(24):
                mx, my = (kx + ox_) / 2.0, (ky + oy_) / 2.0
                if inside(mx, my):
                    kx, ky = mx, my
                else:
                    ox_, oy_ = mx, my
            if ia:
                g.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(kx), pcbnew.FromMM(ky)))
            else:
                g.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(kx), pcbnew.FromMM(ky)))
            clipped += 1
    print("silkscreen past the outline: %d clipped, %d removed" % (clipped, removed))

clip_silk_to_board()

# ── Board outline ────────────────────────────────────────────────────────────
def edge_line(x1, y1, x2, y2):
    seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
    seg.SetStart(P(x1, y1)); seg.SetEnd(P(x2, y2))
    seg.SetLayer(pcbnew.Edge_Cuts); seg.SetWidth(pcbnew.FromMM(0.1))
    board.Add(seg)

# Plain rectangle: a closed, unambiguous outline (rounded corners are a
# cosmetic detail the fab can add via a routing radius).
edge_line(0, 0, W, 0)
edge_line(W, 0, W, H)
edge_line(W, H, 0, H)
edge_line(0, H, 0, 0)

# ── Zones: bottom GND pour (whole board) ─────────────────────────────────────
def add_zone(net, layer, pts, priority, name):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(nets[net])
    z.SetAssignedPriority(priority)
    z.SetZoneName(name)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetLocalClearance(pcbnew.FromMM(0.2))
    z.SetMinThickness(pcbnew.FromMM(0.2))
    # NOTE: ISLAND_REMOVAL_MODE_ALWAYS was tried and rejected. It changes the
    # Specctra export, after which Freerouting leaves SCK, MISO, TFT_DC and
    # TFT_RST unrouted in both attempts. The pour therefore keeps the default
    # behaviour, and the remaining copper scraps are dealt with by ses_import.py
    # (pads) and heal_gnd_fragments.py (pour fragments).
    outline = z.Outline()
    outline.NewOutline()
    for (px, py) in pts:
        outline.Append(P(px, py))
    board.Add(z)
    return z

add_zone("GND", pcbnew.B_Cu, [(0, 0), (W, 0), (W, H), (0, H)], 0, "GND pour")
# (A top-layer GND pour was tried and rejected: on a board this densely routed
# it fragments into isolated islands and creates more problems than it solves.
# The bottom plane plus the stitching-via grid added after routing is enough.)
# No 3V3 pour: a partial pour splits +3V3 into islands that the router then
# leaves unconnected. 3.3 V is distributed as ordinary tracks instead - at the
# default netclass width of 0.20 mm, like every other signal on the board.
# (This comment used to say "0.4 mm tracks", which was never true: +3V3 has no
# net class of its own and has always come out at 0,20 mm.)

# ── Antenna keepout: 5 mm, per the documentation (see the U6 comment) ───────
ADD_EXTRA_KEEPOUT = True
ka = pcbnew.ZONE(board)
ls = pcbnew.LSET()
ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu)
ka.SetLayerSet(ls)
ka.SetIsRuleArea(True)
ka.SetDoNotAllowZoneFills(True)
ka.SetDoNotAllowTracks(True)
ka.SetDoNotAllowVias(True)
ka.SetDoNotAllowPads(False)   # the module's own pads sit next to this area
ka.SetZoneName("ANT keepout")
ko = ka.Outline(); ko.NewOutline()
# 5 mm copper-free strip past the module's antenna end, only as tall as the
# antenna itself so the UI signals keep a corridor above and below it.
for (px, py) in [(44.8, 29), (50.0, 29), (50.0, 43), (44.8, 43)]:
    ko.Append(P(px, py))
if ADD_EXTRA_KEEPOUT:
    board.Add(ka)

# ── Design rules (documentation, table 5): signal 0.15 mm, power 0.5 mm,
#    CAN pair 0.25 mm, signal via 0.3/0.6, clearance 0.15 mm ────────────────
ds = board.GetDesignSettings()
ds.m_MinClearance    = pcbnew.FromMM(0.15)
ds.m_TrackMinWidth   = pcbnew.FromMM(0.15)
ds.m_ViasMinSize     = pcbnew.FromMM(0.5)
# 0.3 mm, matching MIN_DRILL_MM. This used to be 0.2 mm to let the imported
# ESP32-S3-WROOM-1 thermal-pad vias through - enforce_min_drill widens them now,
# so the rule can sit at the fab house's standard minimum and catch a regression.
ds.m_MinThroughDrill = pcbnew.FromMM(MIN_DRILL_MM)
ds.m_MinResolvedSpokes = 1
ds.m_HoleClearance   = pcbnew.FromMM(0.15)
ds.m_HoleToHoleMin   = pcbnew.FromMM(0.25)
ds.m_CopperEdgeClearance = pcbnew.FromMM(0.3)
ds.SetCopperLayerCount(2)

# Default netclass: documentation table 5 permits 0,15 mm signal tracks. This
# uses 0,20 mm (the first prototype used 0,25 mm): with all-THT passives the gap
# between two pads on a 2,54 mm pitch is about 0,94 mm, so 0,05 mm of width
# decides whether a net gets through. Currents are <= 0,5 A per branch and the
# ground is a pour, so 0,20 mm on 35 um copper has enough margin.
nc = ds.m_NetSettings.GetDefaultNetclass()
nc.SetClearance(pcbnew.FromMM(0.15))
nc.SetTrackWidth(pcbnew.FromMM(0.20))
nc.SetViaDiameter(pcbnew.FromMM(0.6))
nc.SetViaDrill(pcbnew.FromMM(0.3))

# DO NOT introduce a separate wider class for OBD_12V (tried and rejected).
# The 12 V branch to connector pin 16 was given a Power12V class with a 0,50 mm
# track width, because a power branch feeding an external tool wants the copper.
# (That came from item PWR-3 of the design review checklist, a document removed on
# 15.08.2026.; the reasoning is kept here because it is what matters.) The trace did
# come out 100 % at 0,50 mm, but the board failed DRC: 0,5 mm closes the corridor
# CS_FLASH and BTN_RETURN pass through, so Freerouting failed to route them in
# all 10 attempts. The fallback maze router finished them and in doing so
# introduced one clearance violation (0,1368 mm) and left pad 40 of module U6
# unconnected to ground.
# Criterion PWR-3 was relaxed instead, because 0,20 mm was never an oversight:
# the documentation explicitly justifies narrowing every track to 0,20 mm on account of
# the THT pitch density, the branch is limited by the 500 mA fuse F1, and
# 0,20 mm on 35 um copper carries about 0,7 A.

# ── The "Power" class: four supply nets at 0,40 mm ───────────────────────────
#
# THIS IS NOT A REPEAT OF THE OBD_12V ATTEMPT. There, 0,50 mm was given to a LONG
# trace crossing the whole board and closing the corridor used by CS_FLASH and
# BTN_RETURN. Here there are four SHORT, LOCAL nets right at the converters and
# at the USB-A receptacle, and they cross no corridor at all:
#
#   SW_3V3, SW_5V  - switching nodes. The TPS562201 datasheet (7.4.1, point 4)
#                    asks to "keep the SW trace as physically short and wide as
#                    practical". They carry the inductor's peak current, ~1 A.
#   V5_STICK       - 5 V to the switch and the USB stick. It used to be 100 mm at
#                    0,20 mm, i.e. about 0,25 ohm, which is a quarter of a volt
#                    of drop at 1 A. USB requires at least 4,75 V at the socket.
#   VBUS_STICK     - the switch output to the socket itself, same current.
#
# The width is 0,40 mm, not 0,50 mm. The reason is the same as for everything
# else on this board: the gap between two adjacent THT contacts on a 2,54 mm
# pitch is about 0,94 mm, so with 0,15 mm of clearance on each side 0,40 mm still
# gets through and 0,50 mm does not. 0,40 mm on 35 um copper carries about 1,1 A
# with a modest temperature rise, and the resistance of V5_STICK drops from 0,25
# to 0,12 ohm.
#
# The class lives in the PROJECT file (.kicad_pro), not in the .kicad_pcb, so it
# is written at the end of this script. ExportSpecctraDSN then hands it to
# Freerouting, which routes those nets wider from the start.
POWER_CLASS_NETS = ["SW_3V3", "SW_5V", "V5_STICK", "VBUS_STICK"]
POWER_CLASS_WIDTH = 0.40

# Thermal vias under the exposed pads are added after routing (ses_import.py):
# the Specctra export strips all copper, so anything created here would be lost.

# ── 3D models and solder-mask colour ─────────────────────────────────────────
# The model list is factored out into scripts/models3d.py, because
# apply_3dmodels.py (attaching models to an already routed board) uses it too.
from models3d import apply_models
print("3D models assigned:", ", ".join(apply_models(board, pcbnew)))

# Solder-mask colour: MATTE BLACK instead of green. This is board stackup data
# (Board Setup -> Physical Stackup), so it also goes to the fabricator as a
# requirement for a black mask, and the render uses it with the
# --use-board-stackup-colors switch. The matte look is a fabricator finish
# (matte black); KiCad only lets a colour be chosen, so a muted black is used
# rather than a pure one, to look matte.
board.Save(OUT)

# The stackup cannot be written through the SWIG interface (GetStackupDescriptor
# returns an opaque object), so the block is inserted into the saved file. That
# yields a BLACK mask and white silkscreen, both in production and in the render
# (kicad-cli pcb render --use-board-stackup-colors).
STACKUP = """		(stackup
			(layer "F.SilkS"
				(type "Top Silk Screen")
				(color "White")
			)
			(layer "F.Paste"
				(type "Top Solder Paste")
			)
			(layer "F.Mask"
				(type "Top Solder Mask")
				(color "Black")
				(thickness 0.01)
			)
			(layer "F.Cu"
				(type "copper")
				(thickness 0.035)
			)
			(layer "dielectric 1"
				(type "core")
				(thickness 1.51)
				(material "FR4")
				(epsilon_r 4.5)
				(loss_tangent 0.02)
			)
			(layer "B.Cu"
				(type "copper")
				(thickness 0.035)
			)
			(layer "B.Mask"
				(type "Bottom Solder Mask")
				(color "Black")
				(thickness 0.01)
			)
			(layer "B.Paste"
				(type "Bottom Solder Paste")
			)
			(layer "B.SilkS"
				(type "Bottom Silk Screen")
				(color "White")
			)
			(copper_finish "ENIG")
			(dielectric_constraints no)
		)
"""

with io.open(OUT, encoding="utf-8") as fh:
    txt = fh.read()
if "(stackup" not in txt:
    marker = "\t(setup\n"
    idx = txt.index(marker) + len(marker)
    txt = txt[:idx] + STACKUP + txt[idx:]
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write(txt)
    print("mask: black, silkscreen: white, finish: ENIG")


# ── The "Power" class in the project file ────────────────────────────────────
# In KiCad 10 net classes live in .kicad_pro, not in .kicad_pcb. The SWIG
# interface does not expose them usably (NET_SETTINGS returns an opaque object),
# so the block is written straight into the JSON, just as the stackup is inserted
# into the .kicad_pcb. pcbnew.LoadBoard() in the next step of the chain loads the
# project along with the board, so ExportSpecctraDSN passes the class width and
# clearance on to Freerouting.
import json as _json

_pro = os.path.splitext(OUT)[0] + ".kicad_pro"
if os.path.isfile(_pro):
    with io.open(_pro, encoding="utf-8") as fh:
        proj = _json.load(fh)
    ns = proj.setdefault("net_settings", {})
    classes = ns.setdefault("classes", [])
    default = next((c for c in classes if c.get("name") == "Default"), None)
    power = next((c for c in classes if c.get("name") == "Power"), None)
    if power is None:
        power = dict(default) if default else {}
        power["name"] = "Power"
        classes.append(power)
    power["track_width"] = POWER_CLASS_WIDTH
    power["clearance"] = 0.15
    power["via_diameter"] = 0.8
    power["via_drill"] = 0.4
    # The priority has to be LOWER than Default's (2147483647), otherwise Default
    # wins and the pattern has no effect.
    power["priority"] = 10
    ns["netclass_patterns"] = [{"pattern": n, "netclass": "Power"}
                               for n in POWER_CLASS_NETS]
    with io.open(_pro, "w", encoding="utf-8") as fh:
        _json.dump(proj, fh, indent=2, ensure_ascii=False)
    print("Power class (%.2f mm) on: %s" % (POWER_CLASS_WIDTH,
                                            ", ".join(POWER_CLASS_NETS)))
else:
    print("WARNING: %s missing, the Power class was not written" % _pro)

print("saved:", OUT)
print("footprints:", len(board.GetFootprints()))
print("nets:", board.GetNetCount())
