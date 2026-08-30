# -*- coding: utf-8 -*-
"""Interactive board view (HTML + SVG) straight from the .kicad_pcb.

    python.exe generate_pcb_html.py <board.kicad_pcb> <out.html>

It draws the real tracks, vias, pads and footprints, with component
descriptions.

The page used to be bilingual, with a Croatian table alongside the English one
and a switch in the header. The Croatian half was removed on 23.08.2026., when
the repository was made English throughout. Component text comes from DESC below.
"""
import sys, os, html
import pcbnew

BOARD = sys.argv[1]
OUT = sys.argv[2]

b = pcbnew.LoadBoard(BOARD)
bb = b.GetBoardEdgesBoundingBox()
X0 = pcbnew.ToMM(bb.GetX())
Y0 = pcbnew.ToMM(bb.GetY())
W = pcbnew.ToMM(bb.GetWidth())
H = pcbnew.ToMM(bb.GetHeight())

def mm(v): return pcbnew.ToMM(v)
def X(v): return round(mm(v) - X0, 3)
def Y(v): return round(mm(v) - Y0, 3)

F_CU, B_CU = pcbnew.F_Cu, pcbnew.B_Cu


# ── component descriptions ───────────────────────────────────────────────────
DESC = {
 "U1":  ("CH224K, USB-C PD sink controller (ESSOP-10)",
         "Negotiates the 12 V profile with the charger, which the charger then puts on VBUS. A single resistor picks the voltage: R23 (24 kΩ) from pin CFG1 to ground (6.8 k = 9 V, 56 k = 15 V, NC = 20 V). R21 (1 kΩ) and C22 (1 µF) feed VDD, while R22 (10 kΩ) goes to the VBUS sense pin. The Rd resistors on the CC lines are built into the chip. It replaced the IP2368, which is a lithium battery charger and cannot do this job."),
 "U2":  ("TPS562201, step-down converter (SOT-23-6)",
         "Brings VBUS down to 3.3 V at up to 2 A. The 4.5 - 17 V input range covers both the 5 V that VBUS carries before the PD contract and the 12 V after it, so the logic comes up either way. The divider R16 / (R17A + R17B) sets the output to 3.300 V, C20 is the decoupling and C21 the bootstrap capacitor."),
 "F1":  ("F1, resettable PTC fuse 500 mA",
         "Limits the current the simulator gives the diagnostic tool through pin 16 of the J1962 connector."),
 "D2":  ("D2, TVS diode SMAJ16A",
         "Absorbs the voltage spike on the 12 V branch when the diagnostic tool is unplugged."),
 "U4":  ("MCP2515, CAN controller (SO-18)",
         "CAN 2.0B controller with an SPI interface. Wired to the ESP32-S3: CS on GPIO10, the INT interrupt on GPIO9. The 8 MHz crystal Y1 provides the clock from which 500 kbit/s is derived."),
 "U5":  ("SN65HVD230, CAN transceiver (SOIC-8)",
         "Converts logic levels into the CAN-H and CAN-L differential pair per ISO 11898, running directly on 3.3 V. The RS pin is grounded, so high-speed mode. It replaced the discontinued MCP2551 (same pinout)."),
 "U6":  ("ESP32-S3-WROOM-1, microcontroller",
         "Dual core 240 MHz, 8 MB of flash. The only SPI master: MOSI GPIO11, MISO GPIO13, SCK GPIO12. The antenna faces the right edge, with a copper keep-out. Programmed over the USB-C USB-Serial-JTAG interface, with the BOOT (SW4) and RESET (SW5) service buttons."),
 "U7":  ("S25FL128L, external NOR flash (SOIC-8 208 mil)",
         "16 MB, carries the FAT filesystem with the scenarios and logs. The CS-FLASH select line is on GPIO15."),
 "U9":  ("TS3USB221, USB mux",
         "Switches the module's single USB OTG controller between the USB-C port (link to a computer) and the USB-A socket (stick). Driven by USB-SEL (GPIO16), while the pull-down R15 holds the mux on the USB-C side during reset. Pinout checked against the TI datasheet (18.07.2026.): S low = USB-C, OE grounded = mux enabled."),
 "U10": ("SY6280, current limited switch",
         "Powers the USB stick in the USB-A socket with 5 V from converter U11, current limited to 1 A (R19). Enabled by USB-HOST-EN (GPIO17). Pinout checked against the Silergy datasheet (18.07.2026.): OUT/GND/ISET/EN/IN."),
 "U11": ("TPS562201, 5 V step-down converter (SOT-23-6)",
         "A second instance of the same converter as U2, with the divider R24/R25 (51 k / 9.31 k) set to 5 V. It powers the USB stick through switch U10, because after the PD contract VBUS carries 12 V, too much for both the SY6280 (max 5.5 V) and the stick."),
 "L3":  ("L3, inductor 10 µH", "Choke of the 5 V converter U11 that powers the USB stick."),
 "D1":  ("PESD1CAN, CAN bus ESD protection (SOT-23)",
         "A dedicated CAN ESD pair (replaced the PRTR5V0U2X): protects CAN-H and CAN-L from electrostatic discharge when the cable is plugged in. Placed right next to the connector. Pins: I/O1 / I/O2 / ground, with no VCC pin."),
 "J1":  ("J1, USB-C receptacle (GCT USB4085-GF-A)",
         "Power input and the link to a computer in USB disk mode. CC1 and CC2 go straight to the CH224K, which has the Rd resistors built in."),
 "J2":  ("J2, J1962F connector (OBD-II)",
         "Towards the diagnostic tool. Pins 6 and 14 carry CAN-H and CAN-L, pins 4 and 5 the ground, and pin 16 carries the 12 V that powers the tool, just as in a vehicle."),
 "SW6": ("SW6, 5-way switch (Alps SKRHABE010)",
         "Replaced the analogue joystick and header J3. The X and Y axes are read as three voltage levels on GPIO2 and GPIO4 (ADC1) through the R26-R29 ladder (6.8 k pull-up + 10 k), the centre click on GPIO5."),
 "R26": ("R26, resistor 6.8k", "Pull-up of the X axis of switch SW6 to 3.3 V."),
 "R27": ("R27, resistor 6.8k", "Pull-up of the Y axis of switch SW6 to 3.3 V."),
 "R28": ("R28, resistor 10k", "X axis ladder: contact B of switch SW6 pulls JOY_X to about 1.96 V."),
 "R29": ("R29, resistor 10k", "Y axis ladder: contact D of switch SW6 pulls JOY_Y to about 1.96 V."),
 "J4":  ("J4, USB-A socket", "For importing and exporting scenarios with an ordinary USB stick."),
 "J5":  ("J5, TFT module header",
         "A 2.4 inch module (Waveshare 18366, no touch), ILI9341, 320 × 240. CS on GPIO14, DC/RS on GPIO21, RESET on GPIO47, sharing the SPI bus (with no MISO line)."),
 "ENC1": ("ENC1, incremental encoder EN11-HSB1AQ20",
         "Replaced the potentiometer RV1 (06.08.2026.). Gives relative steps, 20 pulses and 20 detents per revolution, with a built-in push button. Channels A and B on GPIO1 and GPIO38, the button on GPIO39, common lead to ground. The pull-up is internal to the ESP32 and debouncing is done by the firmware, so there are no external passives."),
 "SW1": ("SW1, CONFIRM button", "Confirms the selection. Input GPIO6, active low, with an external pull-up resistor."),
 "SW2": ("SW2, CLEAR button", "Reverts an edit, and on the fault screen erases the DTC memory. Input GPIO7."),
 "SW3": ("SW3, RETURN button", "Returns to the previous screen. Input GPIO8."),
 "SW4": ("SW4, BOOT button", "Programming circuit. Service button on the strapping pin GPIO0 (pull-up R14). Held while RESET is briefly pressed to enter the ROM bootloader download mode by hand."),
 "SW5": ("SW5, RESET button", "Programming circuit. Service button on the module's EN pin (pull-up R13 and capacitor C26). A short press resets the microcontroller."),
 "R13": ("R13, resistor 10k", "Pull-up on the module's EN pin. Together with C26 it forms the reset RC network."),
 "R14": ("R14, resistor 10k", "Programming circuit. Pull-up on the strapping pin GPIO0 (BOOT button)."),
 "R15": ("R15, resistor 10k", "Programming circuit. Pull-down on the USB-SEL line: holds mux U9 on the USB-C side until the firmware takes over, so the ROM bootloader is reachable from a computer over USB-C (USB-Serial-JTAG)."),
 "C26": ("C26, capacitor 1 µF", "Programming circuit. RC capacitor on the module's EN pin, together with the pull-up R13, for a clean release from reset."),
 "J6":  ("J6, UART header (1×3)",
         "TX0 (GPIO43), RX0 (GPIO44) and ground. Serial monitor at 115200 baud and a fallback programming channel through an external USB-UART converter."),
 "Y1":  ("Y1, crystal 8 MHz", "Clock of the CAN controller, with the load capacitors C6 and C7 (22 pF)."),
 "R7":  ("R7, termination 120 Ω", "End of the CAN bus, right next to the connector. The other end point is the diagnostic tool."),
 "L2":  ("L2, inductor 10 µH", "Choke of the TPS562201 converter on the 3.3 V branch."),
}

# The two dictionaries describe the same board, so a key present in one and
# missing from the other is always a mistake, not a choice.

GENERIC = ("%s, capacitor %s", "Decoupling or bulk capacitor at a supply pin.",
           "%s, resistor %s", "Pull-up resistor or part of a divider.")

def desc(ref, val):
    if ref in DESC:
        return DESC[ref]
    cap_n, cap_d, res_n, res_d = GENERIC
    if ref.startswith("C"): return (cap_n % (ref, val), cap_d)
    if ref.startswith("R"): return (res_n % (ref, val), res_d)
    return ("%s (%s)" % (ref, val), "")

# ── kopar ───────────────────────────────────────────────────────────────────
tracks_f, tracks_b, vias = [], [], []
for t in b.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        vias.append((X(t.GetPosition().x), Y(t.GetPosition().y), mm(t.GetWidth(F_CU)) / 2))
    else:
        s, e = t.GetStart(), t.GetEnd()
        seg = (X(s.x), Y(s.y), X(e.x), Y(e.y), round(mm(t.GetWidth()), 3))
        (tracks_f if t.GetLayer() == F_CU else tracks_b).append(seg)

pads, comps = [], []
for fp in b.GetFootprints():
    ref = fp.GetReference()
    if ref.startswith("H"):
        continue
    for p in fp.Pads():
        pos = p.GetPosition()
        sz = p.GetSize()
        pads.append((X(pos.x), Y(pos.y), round(mm(sz.x), 3), round(mm(sz.y), 3), round(p.GetOrientationDegrees(), 1)))
    r = fp.GetBoundingBox(False, False)
    comps.append((ref, fp.GetValue(), X(r.GetX()), Y(r.GetY()),
                  round(mm(r.GetWidth()), 2), round(mm(r.GetHeight()), 2)))

HOT = {"U1", "U2", "F1", "D2", "J2"}
# programming circuit (added 2026-07-18) gets its own highlight
PROG = {"SW4", "SW5", "R14", "R15", "C26", "J6"}

svg = []
A = svg.append
A('<rect x="0" y="0" width="%.2f" height="%.2f" rx="1" fill="url(#boardGrad)" stroke="#0a2a0d" stroke-width="0.3"/>' % (W, H))
# bottom layer: ground
A('<g id="lay-b" opacity="0.45">')
A('<rect x="1" y="1" width="%.2f" height="%.2f" fill="#0f3d15"/>' % (W - 2, H - 2))
for x1, y1, x2, y2, w in tracks_b:
    A('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#7a6a2a" stroke-width="%s" stroke-linecap="round"/>' % (x1, y1, x2, y2, w))
A('</g>')
# top layer: tracks
A('<g id="lay-f">')
for x1, y1, x2, y2, w in tracks_f:
    A('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="url(#copperGrad)" stroke-width="%s" stroke-linecap="round"/>' % (x1, y1, x2, y2, w))
A('</g>')
# vias
A('<g id="lay-v">')
for x, y, r in vias:
    A('<circle cx="%s" cy="%s" r="%.3f" fill="#c9a23c"/><circle cx="%s" cy="%s" r="%.3f" fill="#15320f"/>' % (x, y, r, x, y, r * 0.45))
A('</g>')
# padovi
A('<g id="lay-p">')
for x, y, w, h, rot in pads:
    A('<rect x="%.3f" y="%.3f" width="%s" height="%s" rx="0.12" fill="#e0bb55" transform="rotate(%s %s %s)"/>'
      % (x - w / 2, y - h / 2, w, h, rot, x, y))
A('</g>')
# komponente + tooltip
A('<g id="lay-c">')
for ref, val, x, y, w, h in comps:
    nm, ds = desc(ref, val)
    hot = ref in HOT
    prog = ref in PROG
    fill = "rgba(255,176,0,0.18)" if hot else ("rgba(60,190,220,0.18)" if prog else "rgba(10,20,12,0.45)")
    stroke = "#ffb000" if hot else ("#3cbedc" if prog else "#8fb79a")
    txt = "#ffd27a" if hot else ("#9adcec" if prog else "#cfe6d5")
    A('<g class="component" data-ref="%s" data-name="%s" data-desc="%s">' % (
        html.escape(ref), html.escape(nm), html.escape(ds)))
    A('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="0.3" fill="%s" stroke="%s" stroke-width="0.12"/>'
      % (x, y, w, h, fill, stroke))
    if w > 3 and h > 1.6:
        A('<text x="%.2f" y="%.2f" font-size="%.2f" text-anchor="middle" fill="%s" font-family="Courier New">%s</text>'
          % (x + w / 2, y + h / 2 + 0.5, min(1.6, h * 0.5), txt, ref))
    A('</g>')
A('</g>')

n_hot = len(HOT)
page = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OBD-II Simulator PCB v0.7</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0c0f0d;min-height:100vh;display:flex;flex-direction:column;align-items:center;
     padding:32px 20px;font-family:'Courier New',monospace;color:#aaa}
.header{text-align:center;margin-bottom:18px}
.header h1{color:#b8e8c4;font-size:22px;letter-spacing:3px}
.header p{font-size:11px;color:#5a8a6a;letter-spacing:1.5px;margin-top:6px}
.header .note{max-width:900px;margin:10px auto 0;font-size:11px;color:#4a7a58;line-height:1.7}
.pcb-frame{position:relative;border:1px solid #1e3a24;padding:10px;background:#0a1a0d;border-radius:4px}
.component{cursor:pointer}
.component:hover rect{stroke:#ffb000;stroke-width:0.25}
.tooltip{position:fixed;pointer-events:none;background:#0d1f12;border:1px solid #2a5a34;
         padding:8px 10px;border-radius:3px;max-width:340px;display:none;z-index:9}
.tooltip .t-ref{font-size:10px;color:#4a8a5a;letter-spacing:1px}
.tooltip .t-name{font-weight:bold;color:#b8e8c4;font-size:12px;margin-top:2px}
.tooltip .t-desc{color:#7aa88a;font-size:10.5px;margin-top:5px;line-height:1.6}
.controls{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap;justify-content:center}
.controls button{background:#12251a;border:1px solid #2a5a34;color:#8fc79f;font-family:inherit;
                 font-size:10px;letter-spacing:1px;padding:6px 12px;border-radius:3px;cursor:pointer}
.controls button.off{opacity:.4}
.legend{display:flex;gap:16px;margin-top:14px;flex-wrap:wrap;justify-content:center;
        font-size:9.5px;color:#3a5a42;letter-spacing:.5px}
.legend i{display:inline-block;width:9px;height:9px;border-radius:1px;margin-right:5px}
.info-bar{display:flex;gap:20px;margin-top:10px;font-size:9px;color:#273d2c;letter-spacing:1.5px}
</style>
</head>
<body>
<div class="header">
  <h1>OBD-II SIMULATOR</h1>
  <p>PCB v0.7 &nbsp;·&nbsp; __BW__ × __BH__ mm &nbsp;·&nbsp; TWO-LAYER FR4 1.6 mm &nbsp;·&nbsp; ESP32-S3-WROOM-1</p>
  <p class="note">This view is generated straight from the board project file
  (hardware/kicad/obd2-simulator.kicad_pcb), so it matches the real placement and the real tracks: __NT__ tracks on the
  top layer, __NV__ vias, __NC__ footprints. Yellow marks the power section: PD sink U1 (CH224K), step-down converter
  U2 (TPS562201), resettable fuse F1 and TVS diode D2, through which 12 V reaches pin 16 of connector J2 and powers the
  diagnostic tool. Blue marks the programming circuit: the BOOT (SW4) and RESET (SW5) buttons, pull-up R14, pull-down
  R15 on the USB-SEL line, capacitor C26 on the EN pin and the UART header J6. Hover a component for its
  description.</p>
</div>

<div class="pcb-frame">
<svg id="pcb" viewBox="-4 -4 __VW__ __VH__" width="880" height="720" xmlns="http://www.w3.org/2000/svg">
<defs>
  <linearGradient id="boardGrad" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#19551e"/><stop offset="100%" stop-color="#123d16"/>
  </linearGradient>
  <linearGradient id="copperGrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#d4aa48"/><stop offset="100%" stop-color="#b8902e"/>
  </linearGradient>
</defs>
__SVG__
</svg>
</div>

<div class="controls">
  <button data-l="lay-f">TRACKS (TOP)</button>
  <button data-l="lay-b">GROUND (BOTTOM)</button>
  <button data-l="lay-v">VIAS</button>
  <button data-l="lay-p">PADS</button>
  <button data-l="lay-c">COMPONENTS</button>
</div>

<div class="legend">
  <span><i style="background:#d4aa48"></i><span>copper, top layer</span></span>
  <span><i style="background:#7a6a2a"></i><span>ground, bottom layer</span></span>
  <span><i style="background:#e0bb55"></i><span>pads</span></span>
  <span><i style="background:#ffb000"></i><span>power section (U2, F1, D2, J2)</span></span>
  <span><i style="background:#3cbedc"></i><span>programming circuit (SW4, SW5, R14, R15, C26, J6)</span></span>
</div>
<div class="info-bar">
  <span>BUS 500 kbit/s</span><span>PIN 16 = 12 V</span><span>SPI 40 MHz</span><span>DRC: 0 UNCONNECTED</span>
</div>

<div class="tooltip" id="tip"><div class="t-ref"></div><div class="t-name"></div><div class="t-desc"></div></div>

<script>
const tip = document.getElementById('tip');
document.querySelectorAll('.component').forEach(function (g) {
  g.addEventListener('mousemove', function (e) {
    tip.style.display = 'block';
    tip.style.left = Math.min(e.clientX + 16, window.innerWidth - 360) + 'px';
    tip.style.top = (e.clientY + 16) + 'px';
    tip.querySelector('.t-ref').textContent = g.dataset.ref;
    tip.querySelector('.t-name').textContent = g.dataset.name;
    tip.querySelector('.t-desc').textContent = g.dataset.desc;
  });
  g.addEventListener('mouseleave', function () { tip.style.display = 'none'; });
});
document.querySelectorAll('.controls button').forEach(function (btn) {
  btn.addEventListener('click', function () {
    const layer = document.getElementById(btn.dataset.l);
    const off = btn.classList.toggle('off');
    layer.style.display = off ? 'none' : '';
  });
});

/* English is the default, always. The choice is deliberately not remembered,
   so every load starts in English. */
applyLang('en');
</script>
</body>
</html>
"""
page = (page.replace("__SVG__", "\n".join(svg))
            .replace("__VW__", "%.1f" % (W + 8))
            .replace("__VH__", "%.1f" % (H + 8))
            .replace("__NT__", str(len(tracks_f)))
            .replace("__NV__", str(len(vias)))
            .replace("__NC__", str(len(comps)))
            .replace("__BW__", "%d" % round(pcbnew.ToMM(b.GetBoardEdgesBoundingBox().GetWidth())))
            .replace("__BH__", "%d" % round(pcbnew.ToMM(b.GetBoardEdgesBoundingBox().GetHeight()))))
open(OUT, "w", encoding="utf-8").write(page)
print("HTML:", OUT, "| tracks:", len(tracks_f) + len(tracks_b), "| vias:", len(vias), "| footprints:", len(comps))
