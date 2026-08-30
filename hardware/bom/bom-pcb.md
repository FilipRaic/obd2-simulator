# Bill of materials, board v0.7

How much of what goes on the final board (**v0.7**, 130 x 115 mm), by group and
by individual value. The counts are taken from
`../kicad/obd2-simulator.kicad_pcb`, not copied from an earlier text.

Alongside this file, the other purchase list is `bom-pcb.csv` in the same
directory, which carries suppliers, order codes and prices. Quantities, values,
tolerances and packages live here.

---

## Total part count for the whole board

| Group | Qty | References |
|---|---|---|
| Resistors | 33 | R7 - R16, R17A, R17B, R19, R21 - R40 |
| Capacitors | 32 | C1, C3 - C7, C10 - C16, C18 - C29, C31 - C37 |
| Inductors | 2 | L2, L3 |
| Diodes | 5 | D1, D2, D3, **D4, D5 (optional)** |
| ICs and modules | 9 | U1, U2, U4 - U7, U9 - U11 |
| Connectors | 5 | J1, J2, J4, J5, J6 |
| Buttons and switches | 6 | SW1 - SW6 |
| Encoder | 1 | ENC1 |
| Crystal | 1 | Y1 |
| Fuse | 1 | F1 |
| **Total to solder** | **95** | |

**The board carries 107 footprints and 95 parts are soldered.** The difference is
12 footprints with no component on them: eight test points TP1 to TP8 and four
mounting holes H1 to H4. Of those 95 parts, D4 and D5 are optional on a first
build, so **93 parts** are enough for a working board.

Passives are 67 of those 95, that is 33 resistors, 32 capacitors and 2
inductors. The other 28 are connectors, semiconductors and electromechanics.

**The display is not counted in the 95.** The 2,4" TFT module with the ILI9341
controller is not on the board but plugs into header J5, and it is listed in
`bom-pcb.csv`.

Reference numbering has gaps (there is no R17 but R17A and R17B, no R18, R20,
J3, U3, U8 and so on), so the part count must not be read off the highest
reference.

### How much of each value to have

#### Resistors, 33 pieces in 11 values

| Value | On board | References | Tolerance | Alternative and note |
|---|---|---|---|---|
| 10 kΩ | 16 | R9 - R15, R22, R28, R29, R32 - R37 | 1 % (5 % passes) | pull-ups for buttons, joystick and encoder, RC on the EN pin, VBUS sense, pull-ups on CS_CAN and CS_FLASH, pull-down on USB_HOST_EN |
| 33 Ω | 3 | R8, R30, R31 | 5 % passes | backlight input (R8), series termination of SCK and MOSI at the module's output pin (R30, R31) |
| 100 Ω | 3 | R38, R39, R40 | 5 % passes | in series in the encoder filter, **the only vertical resistors**, 5,08 mm pitch |
| 6,8 kΩ | 3 | R19, R26, R27 | 1 % | R19 sets the SY6280 current limit to about 1 A, the value matters |
| 51 kΩ | 2 | R16, R24 | **1 %, mandatory** | upper members of the feedback dividers of both converters |
| 120 Ω | 1 | R7 | 1 % | CAN termination, the tolerance defines the bus impedance. 124 Ω or 127 Ω (E96) also pass |
| 1 kΩ | 1 | R21 | 1 % | series VBUS towards the VDD of the CH224K controller. 910 Ω and 1,05 kΩ work equally well |
| 9,31 kΩ | 1 | R25 | **1 %, mandatory, E96** | lower member of the 5 V divider. Substituting 9,1 kΩ gives 5,07 V instead of 4,98 V, which is acceptable |
| 15 kΩ | 1 | R17A | **1 %, mandatory** | upper half of the lower member of the 3,3 V divider, in series with R17B |
| 470 Ω | 1 | R17B | **1 %, mandatory** | lower half, with R17A it gives 15,47 kΩ. 15 kΩ on its own is **not** enough, it gives 3,38 V |
| 24 kΩ | 1 | R23 | **1 %, mandatory** | CH224K CFG1, selects the 12 V PD profile |
| **Total** | **33** | | | |

Where a value is marked "mandatory" the tolerance sets an output voltage or the
selected PD profile, so 5 % is no substitute. Elsewhere 5 % is fine. For every
value it pays to buy two to four spares, because an axial resistor is easily
damaged when its leads are bent, and the price difference is a few cents.

#### Capacitors, 32 pieces in 8 values

| Value | On board | References |
|---|---|---|
| 100 nF | 12 | C10 - C16, C20, C21, C23, C24, C29 |
| 10 µF | 5 | C5, C18, C19, C25, C37 |
| 22 µF low ESR | 4 | C3, C4, C27, C28 |
| 47 nF | 3 | C31, C32, C33 |
| 1 nF | 3 | C34, C35, C36 |
| 1 µF | 2 | C22, C26 |
| 22 pF | 2 | C6, C7 |
| 100 µF | 1 | C1 |
| **Total** | **32** | |

#### Which capacitor type goes with which value

This is the table to buy from. The footprints come from
`../kicad/scripts/build_board.py`, where they are defined.

| Value | References | **Type you must have** | Footprint and pitch | Polarised | Voltage |
|---|---|---|---|---|---|
| 22 pF | C6, C7 | **ceramic disc NP0/C0G** | Ø4,3 x 1,9 mm, RM 5 mm | no | ≥ 50 V |
| 1 nF | C34, C35, C36 | **ceramic disc NP0/C0G**, X7R passes | Ø4,3 x 1,9 mm, RM 5 mm | no | ≥ 50 V |
| 47 nF | C31, C32, C33 | **ceramic disc X7R**, MKT film passes if the body fits | Ø5,0 x 2,5 mm, RM 5 mm | no | ≥ 50 V |
| 100 nF | C10-C16, C20, C21, C23, C24, C29 | **ceramic disc X7R** | Ø5,0 x 2,5 mm, RM 5 mm | no | ≥ 50 V |
| 1 µF | C22, C26 | **ceramic disc or MLCC X7R** | Ø6,0 x 2,5 mm, RM 5 mm | no | ≥ 16 V, 50 V better |
| 10 µF | C5, C18, C19, C25, C37 | **plain aluminium electrolytic, radial** | Ø5,0 mm, up to 7 mm tall, RM 2,0 mm | **yes** | ≥ 25 V, ≥ 10 V is enough for C37 |
| 22 µF | C3, C4, C27, C28 | **low ESR or polymer, radial** | Ø6,3 mm, RM 2,5 mm, also takes RM 2,0 mm | **yes** | C3 and C27 ≥ 25 V, C4 and C28 ≥ 10 V |
| 100 µF | C1 | **aluminium electrolytic, radial** | Ø6,3 mm, RM 2,5 mm | **yes** | ≥ 25 V |

Three rules the table does not show on its own:

- **Polymer parts exist only from 22 µF upwards.** That family starts at a few
  µF, so 47 nF or 1 nF in a polymer type do not exist. Everything up to 1 µF is
  ceramic or film.
- **Never Y5V or Z5U.** Those dielectrics lose up to 80 % of their capacitance
  with voltage and temperature. At 47 nF the encoder filter would be left without
  a time constant, and at 100 nF the supply decoupling would be gone.
- **Ten positions are polarised** (C1, C3, C4, C5, C18, C19, C25, C27, C28,
  C37). The anode, the plus, goes to the supply. All ceramic positions are
  unpolarised and may be soldered either way round.

Why that split: the 22 µF parts are the input and output capacitors of the
converters, where ESR matters and 0,25 to 0,31 A of ripple current flows, so low
ESR or polymer is required. C1 is the 100 µF input reservoir on VBUS, where ESR
is not critical. The 10 µF electrolytics are local reservoirs and a plain type is
enough for them. Everything below 1 µF is ceramic, because it has to work at the
switching frequency of 580 kHz and above, where an electrolytic has no business.

#### Inductors, 2 pieces in 1 value

| Value | On board | References | Note |
|---|---|---|---|
| 4,7 µH | 2 | L2, L3 | Isat ≥ 1,5 A, DCR ≤ 0,1 Ω, **radial**, 5,00 mm pitch, body up to Ø8,5 mm. Table 7-2 of the TPS562201 datasheet gives 4,7 µH as the maximum for both 3,3 V and 5 V |

That makes the passives **67 pieces in 20 different values**. The other 28 parts
are semiconductors, connectors and electromechanics, and each of them goes in one
or two pieces:

| Part | Qty | References |
|---|---|---|
| SMAJ16A, TVS | 2 | D2, D3 |
| USBLC6-2SC6, ESD array (optional) | 2 | D4, D5 |
| TPS562201DDCR, buck converter | 2 | U2, U11 |
| PESD1CAN, ESD for CAN | 1 | D1 |
| CH224K, USB-C PD sink | 1 | U1 |
| MCP2515-I/SO, CAN controller | 1 | U4 |
| SN65HVD230DR, CAN transceiver | 1 | U5 |
| ESP32-S3-WROOM-1-N8R2, module | 1 | U6 |
| S25FL128L, flash | 1 | U7 |
| TS3USB221, USB mux | 1 | U9 |
| SY6280AAC, current switch | 1 | U10 |
| Crystal 8 MHz | 1 | Y1 |
| PTC fuse 500 mA | 1 | F1 |
| Connectors USB-C, USB-A, J1962F, LCD, UART | 5 | J1, J4, J2, J5, J6 |
| Buttons CONFIRM, CLEAR, RETURN, BOOT, RESET | 5 | SW1 - SW5 |
| Joystick SKRHABE010 | 1 | SW6 |
| Encoder EN11-HSB1AQ20 | 1 | ENC1 |

Full data for every value, that is tolerance, voltage and package, is in the
tables above, and suppliers and prices are in `bom-pcb.csv`. Those two documents
are the only purchase lists.

### Optional parts D4 and D5

D4 and D5 are USBLC6-2SC6 ESD arrays on the USB lines and carry the DNP flag, so
they may be skipped on a first build. The board works without them, the USB lines
are simply left without electrostatic discharge protection. If they are fitted,
the note about pin 5 in the soldering section below applies.

---

## What to watch out for when soldering

- **Ten positions are polarised: C1, C3, C4, C5, C18, C19, C25, C27, C28 and
  C37.** The anode (plus) goes to the supply. Those are all the `CP_Radial_*`
  footprints on the board, while ceramics are unpolarised and may be soldered
  either way round. Ø5 mm capacitors with 2,0 mm pitch fit footprints C3, C4,
  C27 and C28, their leads just need easing out to 2,5 mm.
- **D3 is an SMAJ16A, the same part as D2, and pad 1 is the cathode**, which goes
  to OBD_12V, that is towards the connector. A diode fitted the wrong way round
  cuts the tool's supply on pin 16.
- **D4 and D5 are optional.** If they are fitted: **pin 5 goes to +3,3 V, not to
  VBUS.** The reverse standoff voltage of that pin is 5 V, and after the PD
  contract VBUS carries 12 V.
- **R38, R39, R40 stand vertically.** The only three such parts on the board.
- **Pins 4 and 5 of U1 (DP, DM) are deliberately not connected.** Do not "fix"
  that.
