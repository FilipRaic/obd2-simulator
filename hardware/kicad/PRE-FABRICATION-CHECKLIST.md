# State of revision v0.7

The numbers are measured from the board itself.

| Item | State |
|---|---|
| Outline | 130 x 115 mm, unchanged |
| Footprints | **107** (95 parts to solder + 8 test points + 4 mounting holes), of which **16 SMD** |
| Netlist | **64 nets**, ground included (new: ENC_A_RAW, ENC_B_RAW, ENC_SW_RAW) |
| Routing | **892 segments** (639 top layer, 253 bottom), **73 vias** |
| DRC | **0 errors, 0 warnings, 0 unconnected** |
| Net classes | Default 0,20 mm + **Power 0,40 mm** (SW_3V3, SW_5V, V5_STICK, VBUS_STICK) |
| Track widths | 849 x 0,20 mm, 37 x 0,40 mm, 6 x 0,25 mm (ground bridges) |
| Vias | 72 x 0,60 / 0,30 mm + **1 x 0,80 / 0,40 mm** (net V5_STICK, Power class) |
| Drill | **326 holes**, 17 tools |
| Smallest hole | **0,30 mm** (since 11.08.2026.; before that 0,20 mm on 12 thermal vias under the EPAD of module U6) |
| Smallest hole spacing | **0,400 mm** overall, **0,450 mm** between different nets (it was 0,272 mm before the last repair round) |
| CAN pair | routed by its own script **before** Freerouting: a chain with no stub, **0 vias**, entirely on the top layer. CANH 83,9 mm, CANL 62,2 mm, **0 branch points**, two ends each (transceiver pin and connector pin) |

## BUG IN REVISION v0.7 - the pinout of SW6 (found 21.08.2026.)

**This must be fixed before any future fabrication.** It was found by measuring
on the assembled board, after four directions of the five-way switch did not
work.

The pinout in footprint `SKRHABE010.kicad_mod` **does not match the real part**.
What the netlist calls pad 2, that is net `JOY_SW`, is in reality the **common
contact** of the switch, and the centre contact is on one of the pads the board
ties to ground.

Consequences on the assembled board:

- **All four directions are dead.** Pressing connects the common contact to
  `JOY_X`, `JOY_XB`, `JOY_Y` or `JOY_YB`, but the common contact is `JOY_SW`,
  which R9 holds at 3,3 V through 10k. Two nets that are both already high get
  connected, so the voltage does not move. Measured by the firmware: both axes
  sit at 3159 mV across all 64 samples, without a single bit of deviation.
- **The centre works, but by accident.** Pressing connects the common contact to
  a grounded pad, so `JOY_SW` drops to zero and the firmware reports Select. The
  outcome is the designed one, but the mechanism is entirely different.

The measurement that proves it, a multimeter in continuity mode with the board
unpowered: probes on **pad 2 and pad 1**, moving the stick **left** beeps. No
direction beeps against ground, while `JOY_SW` against ground does.

**Workaround for this board, without a single wire.** The common contact is on
GPIO5, that is on a pin the firmware can drive. `firmware/src/ui/input.cpp`
holds it low, which turns the common contact into the ground the schematic
always assumed, so the directions work exactly as drawn, either through zero or
through the 10k ladder. The centre is read by briefly returning the pin to an
input with a pull-up. The pin **must never be driven high**, because with the
centre pressed that would be a short to ground.

**For the next revision:** pad 2 goes to ground and the centre contact to a
GPIO. Before routing, check the real pinout both against the datasheet and by
**buzzing out a physical part**, because the check in section 2, the one from
18.07.2026., was done from datasheets only and missed this.

---

## Note for the fabricator (the "remarks" field of the order)

The board sits right at the process limit in four places, deliberately. The
problem is not that a fabricator cannot make it, but that an automatic DFM check
will "fix" those items and thereby ruin a part that was drawn that way for a
reason. So they have to be stated up front. The numbers were measured from the
`.kicad_pcb` on 11.08.2026.

Three are mandatory, the rest is useful:

1. **Hole spacing 0,400 mm**, and 0,450 mm between holes of different nets. Those
   0,450 mm are inside the official footprint of the GCT USB4085 USB-C connector
   and must not be changed.
2. **Copper clearance is exactly 0,150 mm everywhere**, without a single
   micrometre of margin. No automatic track spreading may be run.
3. **The mask is drawn with expansion 0**, so the mask bridge between the
   contacts of the USB-C connector is 0,150 mm and the openings may merge. That
   is expected and acceptable, the openings must not be enlarged.

Worth stating alongside: the smallest annular ring is **0,150 mm** (0,60/0,30 mm
vias and 0,70 mm pads over a 0,40 mm hole on J1), the silkscreen has **1688 lines
0,120 mm wide** and one of 0,060 mm on the SW6 footprint, the board has **22
plated slots** and **8 non-plated holes**, impedance is not controlled and no
stencil is ordered.

| Slots (plated) | Non-plated holes |
|---|---|
| 16 x 1,20 x 3,00 mm (J2, OBD-II) | 4 x Ø3,20 mm (H1-H4, M3) |
| 2 x 2,80 x 1,50 mm (ENC1) | 2 x Ø2,60 mm (J2, locating) |
| 2 x 0,60 x 2,10 mm (J1, shield) | 1 x Ø1,20 mm (SW6) |
| 2 x 0,60 x 1,40 mm (J1, shield) | 1 x Ø0,90 mm (SW6) |

### Text to paste

**The remarks field at JLCPCB takes at most 200 characters**, so only what is
critical fits. This text is **196 characters** and covers all three items above:

> Do NOT auto-adjust the design. It is intentionally at process limits:
> hole-to-hole 0.40mm, copper clearance 0.15mm, mask expansion 0 (USB-C mask
> openings may merge). Fabricate exactly as supplied.

Paste it as a single line, without breaks. A shorter version, if the field turns
out tighter still, is 139 characters:

> Do NOT auto-adjust. Intentional: hole-to-hole 0.40mm, clearance 0.15mm, mask
> expansion 0 (USB-C openings may merge). Fabricate as supplied.

**The rest does not go into the field, it waits until they ask.** The annular
ring, the slots, the non-plated holes, the silkscreen and impedance need no
advance note. If the automatic check raises a question, answer in the
correspondence with these details:

> - Minimum annular ring is 0.15 mm (0.60/0.30 mm vias, and 0.70 mm pads over
>   0.40 mm holes on the USB-C connector). Please do not shrink any pad.
> - The 0.45 mm hole pairs are inside the official USB-C connector footprint
>   (GCT USB4085) and cannot be changed.
> - Silkscreen line width is 0.12 mm on most items. If this is below your
>   minimum, please print as is rather than removing items.
> - 22 plated slots: 16 x 1.2 x 3.0 mm (OBD-II connector), 2 x 2.8 x 1.5 mm,
>   2 x 0.6 x 2.1 mm, 2 x 0.6 x 1.4 mm.
> - 8 non-plated holes: 4 x 3.2 mm (M3 mounting), 2 x 2.6 mm, 1 x 1.2 mm,
>   1 x 0.9 mm. These must stay non-plated.
> - No controlled impedance required. No stencil required, the paste layers are
>   deliberately not in the package.

What needs **no** mention at all: the hole diameter (the smallest is 0,30 mm, so
a standard process since 11.08.2026.), the layer count, thickness, copper weight
and surface finish, because all of those are picked in the order form itself.

## To check when ordering and soldering

> **The passive packages are through-hole, not SMD.** The resistors are axial
> DIN0207 on a 10,16 mm pitch (except R38-R40, vertical on 5,08 mm), the ceramics
> are discs on a 5 mm pitch, the electrolytics are radial. The authoritative
> purchase list is `../bom/bom-pcb.csv`. Section 0 below mentions 0603, 0805,
> 1210 and tantalum EIA-3528 - **those are packages from the older, mixed build
> and those parts do not fit these footprints.** SMD remains 16 footprints: U1,
> U2, U4, U5, U6, U7, U9, U10, U11, D1, D2, D3, D4, D5, F1 and **SW6**. Without
> D4 and D5, which carry the DNP flag and may be left unsoldered, that is 14
> parts.

- **The smallest drill is 0,30 mm, so no fine-drill surcharge applies.** Until
  11.08.2026. the board carried 12 holes of 0,20 mm (thermal vias under the EPAD
  of module U6, inherited from the KiCad footprint) and they alone pushed a
  JLCPCB order into the more expensive class. They were widened to 0,30 mm
  without re-routing. **What still has to be checked when ordering is the hole
  spacing**, because the smallest is 0,400 mm while JLCPCB asks for 0,50 mm in
  its standard process. Those are two separate parameters and have to be looked
  at separately in the calculator. See `../gerber/README.md`.
- **The shield of USB-A socket J4 has been on ground since 10.08.2026.** Before
  that it was not, because `build_board.py` assigned ground to pads "5" and "6"
  while the Molex 67643 footprint calls its two mounting tabs **`SH`**. The
  assignment had no effect and the socket housing floated. DRC cannot catch that:
  a pad with no net has nothing to be unconnected from. On J1 the same thing had
  been written correctly. It was fixed both in the script and in the board
  itself, without re-routing, because both pads lie inside the ground pour on the
  bottom layer so the zone fill catches them with thermal spokes.
- **L2, L3 are now 4,7 µH, not 10 µH, and RADIAL.** The 10 µH inductors already
  bought do not fit this board. Ask for Isat ≥ 1,5 A and DCR ≤ 0,1 Ω, a body up
  to Ø8,5 mm, **5,00 mm lead pitch**. On 10.08.2026. the footprint was changed
  from an axial one mounted vertically to
  `L_Radial_D8.7mm_P5.00mm_Fastron_07HCP`, because an axial footprint draws the
  body over one hole while a radial part sits centred between two. Before that
  the footprint was also too small (Ø5,0 and then Ø7,5 mm), so the courtyard did
  not match the actual part.
- **C3, C4, C27, C28 are LOW ESR capacitors**, not plain electrolytics. The
  criterion is impedance, not chemistry: **ESR at 100 kHz ≤ 0,15 Ω** and a
  **rated ripple current ≥ 0,35 A rms**. A polymer part meets that, and so does
  an electrolytic marked "low ESR" or "low impedance". A plain electrolytic does
  **not**, because its 1 Ω gives 878 mV of ripple and pushes the ESP32-S3 and the
  flash out of specification. The footprint is Ø6,3 mm / 2,5 mm pitch, the same
  as C1, but it also takes a part on a 2,0 mm pitch with the leads eased apart.
  **Polarised.**
- **D4 and D5 are OPTIONAL on a first build**, they carry the DNP flag in the
  `.kicad_pcb` and their footprints may stay empty. Measured: removing the
  footprint leaves 0 unconnected items, because they sit in parallel on their
  pair. See `../bom/bom-pcb.md`, the section on optional parts. **No other part
  may be left out** - the router took other nets through the pads of a dozen of
  them.
- **D3 is an SMAJ16A**, the same part as D2, in the forward direction. **Pad 1 is
  the cathode** and goes to OBD_12V. Both pieces of the SMAJ16A already ordered
  are used, D2 and D3, and both sit in the same orientation, so they cannot be
  mixed up. From 09.08. to 10.08.2026. a Schottky SS34 was required here, but
  that requirement was withdrawn - the reasoning is in `../README.md`, section
  "D3 is an SMAJ16A, not a Schottky".
- **D4, D5 (USBLC6-2SC6, SOT-23-6)** - ESD protection for the USB connectors.
  Pin 5 goes to +3,3 V, **not** to VBUS.
- **C31-C33 are 47 nF**, not 10 nF.
- **R38, R39, R40 (100 Ω) stand VERTICALLY**, 5,08 mm pitch. They are the only
  resistors on the board that are not horizontal. One lead is bent downwards.
- **R35, R36, R37 (10 kΩ)** - pull-ups on CS_CAN and CS_FLASH, pull-down on
  USB_HOST_EN. The same value as R9-R15.
- **C37 (10 µF)** - bulk at the input of switch U10.
- **Pins 4 and 5 of U1 (DP/DM) are deliberately unconnected.** If the board is
  ever drawn again, do not "fix" that by connecting them to the USB-C pair - the
  CH224 datasheet, section 5.5, explicitly requires them to be disconnected if
  the A-port protocols are not used. **DEVIATION, established 21.08.2026.:** the
  same sentence in section 5.5 has a second half that the board does not meet.
  Verbatim: "the DP/DM pin on CH224K/CH224D is required to be disconnected from
  the DP/DM on the Type-C connector, **and the DP pin on CH224 is required to be
  shorted to the DM on CH224**." Here both pins are `None` in the netlist, so
  each floats on its own isolated pad. Note that this is not a soldering matter.
  The pins are soldered, each to its own pad, but there is no copper between
  those two pads and the datasheet asks for exactly that connection. The fix is a
  shared net on pins 4 and 5, which are adjacent on a 1 mm pitch, so the trace is
  short. It was not applied to v0.7 because the board was already fabricated and
  soldered, and the PD contract runs purely over the CC lines.

---

# KiCad PCB - status and what to check before fabrication

Project: `obd2-simulator.kicad_pcb` (KiCad 10), revision **v0.7**. It opens in
KiCad, is fully routed and passes DRC **without a single electrical error**.
Even so, this is a **machine-generated design** (the scripts in `scripts/`) and
the checks in section 2 have to be done before ordering fabrication.

> **How to read what follows.** The authoritative board state is in the table at
> the top of this document and in `../README.md`. The sections below explain
> **why a given part was chosen** and **what has to be verified on each part
> against the delivered component**. That still holds unchanged, because those
> parts have not changed. The figures about dimensions, footprint, segment and
> via counts mentioned in those sections come from earlier development steps and
> **are not valid**.

## 0. Alignment with the TME and LCSC orders

The board is aligned with the parts actually ordered:

- **D1 = PESD1CAN** (SOT-23, 1 = CANH, 2 = CANL, 3 = ground) instead of the
  unavailable PRTR5V0U2X. A purpose-made CAN ESD pair, it has no VCC pin so
  **C30 was removed**. *Check the pinout against the Nexperia datasheet before
  fabrication.*
- **J1 = GCT USB4085-GF-A** instead of the LCSC-only HRO connector, with the
  official KiCad footprint. The position (23,15, 74,2) was chosen by a sweep
  (J1_X/J1_Y in `build_board.py`), because at 23,65 the router dropped USBC_DP
  every time. *Check the mechanical fit of the front tab over the board edge on
  the delivered connector.*
- **SW6 = Alps SKRHABE010** (five-way switch) directly on the board instead of an
  analogue joystick and header J3. Custom footprint in
  `footprints/obd2.pretty/` (derived from EasyEDA/LCSC C139794). The axes are
  read as three voltage levels: 6,8 kΩ pull-up (R26/R27), 10 kΩ ladder
  (R28/R29), a direct contact to ground, and the centre click on JOY_SW. *Check
  which direction closes which contact (A/B/C/D) on the real part - swapping the
  pair is a constant in `firmware/src/ui/input.cpp`.* **See the bug at the top of
  this document: this check was done from datasheets only and got the common
  contact wrong.**
- **Passive sizes as ordered**: R19 6,8 kΩ in 0603, R25 9,31 kΩ in 0805, 22 µF in
  1210 (C3/C4/C27/C28), 10 µF as tantalum B EIA-3528 16 V (C5/C18/C19/C25 -
  **polarised**, anode to the supply). *Mind the tantalum polarity when
  soldering.*
- **The USB-A connector is a TME USB-A-S-RA**, while the footprint stayed Molex
  67643. *Compare the hole pitch with the delivered connector before
  fabrication.*
- The module was ordered as an **ESP32-S3-WROOM-1-N8R2** (8 MB flash, 2 MB
  PSRAM), same footprint and pinout.

## 1. How the board reached this state

Addition of 18.07.2026.: a **programming block** was added - service buttons SW4
(BOOT, GPIO0 + pull-up R14) and SW5 (RESET, EN + R13/C26), pull-down R15 on the
USB-SEL line (holding mux U9 on the USB-C side during reset, so the ROM
bootloader is reachable over the USB-Serial-JTAG interface) and net BOOT. The
same day the footprints were corrected to the actual order codes: **F1 to 1206**
(an 0805 PTC rated ≥ 16 V does not exist), **U9 to Texas_DRC0010J** (VSON-10, the
only package the TS3USB221 really comes in), **U7 to SOIC-8 5,3 mm** (208 mil,
the ordered Infineon S25FL128LAGMFM010, the same package as the W25Q128JVSIQ) and
**D2 to D_SMA** (the correction of 16.07. had gone into the .kicad_pcb only and
not into the script, so regeneration had undone it). The board was re-placed and
re-routed with the same scripts. A note on determinism: on the same placement
Freerouting gives an identical result on every run, so a placement either passes
100 % or fails every time. That is why, alongside C15/C16/C19/C24/C25 (v0.5
coordinates, otherwise CC2 fails), U7 (22, 5), F1 (59, 63) and D2 (52.8, 70.4)
are now fixed as well - the candidate positions for F1/D2 were found by a sweep
(environment variables F1_X/F1_Y/D2_X/D2_Y in `build_board.py`).

The pins of module **U6 were verified against the datasheet** of the
ESP32-S3-WROOM-1 v1.8 (table 3-1) and match the firmware configuration
(`firmware/include/pins_custom_s3.h`).

The pins of controller **U1 (CH224K) were verified against the reference
schematic in the official WCH CH224DS1 datasheet**, section 6.1. Note: the pin
table in that same datasheet lists "2, 3, 9 -> CFG1, CFG2, CFG3", from which one
would conclude that CFG1 is pin 2. **That is wrong.** The reference schematic
shows `2 = CFG2`, `3 = CFG3`, `9 = CFG1`. The schematic is what counts.

The voltage selection table on CFG1 was checked on 21.08.2026. in the same
datasheet, section 5.2.1, and reads verbatim: 6,8 kΩ -> 9 V, 24 kΩ -> 12 V,
56 kΩ -> 15 V, **NC -> 20 V**. The same table is repeated next to the reference
schematic in section 6.1. So R23 of 24 kΩ asks for 12 V, and an open CFG1 does
not give 5 V but 20 V. If the board sits at 5 V, the cause is not CFG1. A
diagnostic note: 5 V is the default state of USB-C before any PD contract, so a
board at 5 V means the contract was not made (a source without PD, a source
without a 12 V profile, a cable from an A-port) or that U1 is not running at all.
Per section 7.5, VDD is an internal shunt regulator at 3,24 to 3,36 V that takes
up to 30 mA, so the series R21 of 1 kΩ from VBUS is the correct way to supply it,
and the voltage on pin 1 must be about 3,3 V.

## 2. Pinout checks - RESOLVED 18.07.2026. against the official datasheets

All four previously assumed pinouts were checked against the official datasheets
and three were WRONG and were corrected in the netlist (`build_board.py`) and
re-routed:

| Ref | Component | Finding | Status |
|---|---|---|---|
| U9 | TS3USB221 (USB mux) | **The pinout was wrong** (VCC was on pin 1, SEL on pin 10). Actually (TI SCDS220M, table 4-1): 1/2 = 1D± (port 1 = USB-C), 3/4 = 2D± (port 2 = USB-A), 5 = GND, 6 = OE (low = active), 7 = D-, 8 = D+ (towards the MCU), 9 = S (low = port 1), 10 = VCC, EP = GND. Package: **Texas_DRC0010J** (VSON-10), order the **TS3USB221DRCR**. | Fixed |
| U10 | SY6280AAC (load switch) | **The pinout was mirrored.** Actually (Silergy): 1 = OUT, 2 = GND, 3 = ISET, 4 = EN (active high), 5 = IN. On top of that the input was connected to VBUS (12 V) while the chip takes 5,5 V - it is now fed by the new 5 V converter U11. | Fixed |
| D1 | PRTR5V0U2X (ESD) | **The pinout was wrong** (CANH on the GND pin, 12 V on an I/O pin). Actually (Nexperia, table 2): 1 = GND, 2 = I/O1, 3 = I/O2, 4 = VCC. VCC was then put on +3,3 V (with C30). **Note for v0.7:** on 19.07.2026. D1 was replaced by a PESD1CAN (SOT-23, no VCC pin), so both that pinout and C30 are history - see section 0. | Replaced in v0.7 |
| U2 | TPS562201 (buck converter) | The pinout was **confirmed correct** (TI: 1 = GND, 2 = SW, 3 = VIN, 4 = VFB, 5 = EN, 6 = VBST). | Confirmed |
| U1 | CH224K, **footprint** | The footprint was drawn by hand from the package drawing in the datasheet (ESSOP-10, body 3,9 x 5,0 mm, 1,0 mm pitch, EP 2,3 x 3,2 mm) and does not come from an official library. Compare it against the mechanical drawing. | Medium |
| F1, D2 | 500 mA PTC fuse and TVS SMAJ16A on the 12 V branch towards pin 16 | Check the tool current and the breakdown voltage. **The D2 footprint was corrected on 16.07.2026.**: it had been `D_SMB`, while the SMAJ16A is SMA (DO-214AC) - it is now `D_SMA` (pads 2,5 x 1,8 mm at ±2,0 mm, footprint from the official `Diode_SMD.pretty` library). DRC after the swap was identical to before (the same 3 findings). **The F1 footprint was enlarged to 1206 (applied 18.07.2026.)** - an 0805 PTC with Vmax ≥ 16 V does not exist on the market (the 0805L series goes to 6 - 15 V). The matching part is a Littelfuse 1206L050/24WR (1206, 0,5 A, 24 V). The same regeneration enlarged the U7 footprint from 3,9 mm to **SOIC-8 5,3 x 5,3 mm (208 mil)**, so the ordered flash actually fits. The part fitted is an **Infineon S25FL128LAGMFM010** (package SOC008, SOIC-8 208 mil); the Winbond W25Q128JVSIQ is an equivalent replacement and the firmware accepts both JEDEC ids. | Medium |

**New 5 V stage (U11, 18.07.2026.)**: a second TPS562201 with divider R24/R25 =
51 k / 9,31 k (0,765 V x 6,478 = 4,96 V), inductor L3 (2,2 µH) and capacitors
C27/C28 (22 µF) + C29 (bootstrap). It supplies the SY6280 and the USB stick,
because VBUS carries 12 V after the PD contract. C23 was moved to the 5 V rail as
decoupling at the input of U10.

**Display (18.07.2026.)**: J5 is an **eight-pin** header for the Waveshare 18366
(2,4" ILI9341 without touch, TME symbol WSH-18366), in the order VCC / GND / DIN
/ CLK / CS / DC / RST / BL - with no MISO line (the module is write-only). The
whole Waveshare series of small LCDs shares that order, so it is interchangeable
with one TFT_eSPI flag.

**Note for v0.7:** this sentence used to say that J2, RV1, J3 and J5 were all pin
headers. On this board that no longer holds. **J2 carries a custom footprint of
the real J1962F connector** (MINITOOLS SEP-A-OBD-D2, directly on the board), and
**RV1 and J3 are gone** along with the potentiometer and the analogue joystick,
which were replaced by encoder ENC1 and switch SW6, both also directly on the
board. The only pin header left is **J5 (TFT)**, eight pins, because the display
is mounted on the front panel and wired. J6 is the UART header: a serial monitor
at 115200 baud and a fallback programming channel through an external USB-serial
converter. The primary programming path is USB-C (USB-Serial-JTAG in the
ESP32-S3 ROM), with buttons BOOT (SW4) and RESET (SW5) for entering download mode
by hand.

## 3. The compromise around the antenna keepout

The ESP32-S3-WROOM-1 footprint carries Espressif's RF keepout (~21 x 48 mm). The
decision was made while the board was 100 x 80 mm: with the user interface along
the right edge, that zone sat exactly between the microcontroller and the UI
column, so no display or interface signal could get through. The zone from the
**project documentation (3-5 mm)** was applied instead and Espressif's was
removed. The outline is 130 x 115 mm today and there is more room, but the zone
was not restored, because restoring it would require re-routing the entire right
half of the board. The firmware does not use Wi-Fi or BLE. **If the radio is ever
needed**, the module has to move to the board edge so that the antenna sticks out
beyond it.

## 4. Procedure before ordering

1. Check the pinouts and the footprint from the table in section 2 and correct
   the connections.
2. Run DRC (Inspect -> Design Rules Checker) - it must stay free of electrical
   errors.
3. Check the CAN pair (CANH/CANL): unbroken, no vias, no branches, termination R7
   at the connector.
4. Re-export the Gerber and drill files (`../gerber/`) and send them for
   fabrication.

## 5. History of the power section

The power section used to be designed around the **IP2368**, described in the
documentation as "a USB-C PD controller with an integrated buck converter".
**That was a component selection error.** According to the official datasheet
(Injoinic v1.40), the IP2368 is a *lithium battery charger* (2-5 cells in series,
QFN-48 7 x 7 mm), it needs a battery pack and it has no feedback divider of the
kind the documentation described. Because of that the PD stage was never actually
drawn, and bridge **R20 (0 Ω)** quietly fed the buck straight from the 5 V VBUS.

The IP2368 was therefore replaced by the **CH224K**, which is a real PD sink: it
negotiates 12 V with the charger and the charger puts it on VBUS. That dropped L1
(4,7 µH), C2 (100 µF), R3 (PROG), R4 (EN), R5/R6 (feedback divider), bridge R20
and R1/R2 (5,1 kΩ on the CC lines, since the CH224K has Rd built in) out of the
design. R21 (1 kΩ), R22 (10 kΩ), R23 (24 kΩ, selecting the 12 V profile) and C22
(1 µF) were added.

## 6. How the project is generated

The scripts in `scripts/` (KiCad Python API + Freerouting):

- `build_board.py` - outline, footprints, netlist, placement by zones, zones,
  design rules. Decoupling capacitors are placed **before** the rest of the
  components in a zone, so they really do end up next to their supply pin
  (2 - 6 mm) rather than 8-12 mm away as in earlier drafts,
- `place.py` - placement without overlaps,
- `dsn_export.py` / `ses_import.py` - Specctra export/import, thermal vias, GND
  bridges, zone filling,
- `generate_figures.py`, `generate_drawing.py`, `generate_pcb_html.py` -
  schematics, the dimensioned drawing and the interactive view, all from the
  actual board.

The custom CH224K footprint is in `footprints/obd2.pretty/`.
