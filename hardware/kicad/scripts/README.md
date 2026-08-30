# Board scripts

The board is **generated, not drawn**. There is no `.kicad_sch` in this project
and the `.kicad_pcb` is an output, so everything about the board that is a
decision lives in these scripts. Anything adjusted by hand in KiCad disappears
the next time `build_board.py` runs, with one deliberate exception noted below.

Wiki page for the hardware: **Building the device**, on the repository wiki.
The design reasoning behind the board is in [`../../README.md`](../../README.md).
The "if you change X, check Y" table lives in the project's working notes
(`docs/MAPA-POVEZANIH-DATOTEKA.md`), which are Croatian and not part of this
repository.

## The interpreter these scripts need

Almost every script here imports `pcbnew`, which only exists inside KiCad's own
Python. It is not the `python` on PATH:

```powershell
& "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin\python.exe" build_board.py board.kicad_pcb
```

The two PowerShell entry points set that up themselves, so calling them needs
nothing but PowerShell. `make_fab_zip.py` and the `docx/` tools are the
exceptions: they touch no board object and run on any Python 3.

## The two entry points

Everything else in this directory is called by one of these two, or is run by
hand for a one-off job.

| Run this | When | What it does |
|---|---|---|
| `route_board.ps1` | a part, a net, a value or the placement changed | Rebuilds the board from nothing and routes it: `build_board.py` → CAN chain → Freerouting (up to 10 attempts, best one kept) → ground repair → DRC. Takes minutes and **throws away the hand-tuned silkscreen** |
| `regen_outputs.ps1` | the board file is already right and the derived files are stale | Touches no placement and no routing. Re-exports renders, gerbers, the fabrication zip, the dimensioned drawing, the interactive HTML view and the schematics |

```powershell
powershell -ExecutionPolicy Bypass -File route_board.ps1
powershell -ExecutionPolicy Bypass -File regen_outputs.ps1
```

> **Do not reach for `route_board.ps1` by reflex.** It ends by calling
> `place_silk_after_route.py`, which puts all 103 reference designators back on
> computed coordinates. Two rounds of hand-tuning (10.08. and 11.08.2026., 59
> designators in the second) live in the `.kicad_pcb` and nowhere else. If
> nothing moved on the copper, edit the `.kicad_pcb` directly, run DRC, and then
> run **only** `regen_outputs.ps1`. Mirror that same edit back into
> `build_board.py`, or the next full regeneration undoes it.

## What `route_board.ps1` runs, in order

Each of these has a "why it exists" header of its own. The short version:

| Step | Script | Why it is a separate step |
|---|---|---|
| 1 | `build_board.py` | The single source of truth: nets, footprints, placement, zones, silkscreen. Aborts the chain on failure, so a stale board is never routed |
| 2 | `route_can_chain.py` | Routes the CAN pair as a chain first, while the board is empty. Freerouting routes a minimal tree and knows nothing about the required transceiver → termination → ESD → connector order |
| 3 | `dsn_export.py` | Specctra export, with the CAN pair handed over as a fixed obstacle |
| 4 | `tools/freerouting.jar` | The autorouter. Randomised, so it runs up to ten times and the best attempt wins |
| 5 | `ses_import.py` | Imports the result and rebuilds everything the Specctra round-trip discards: thermal vias, pours, island bridging |
| 6 | `route_can_chain.py --replay` | Restores the chain, because the router lays its own trace alongside a protected one |
| 7 | `route_one_net.py` | A small maze router for the one net Freerouting occasionally leaves open |
| 8 | `heal_gnd_fragments.py`, `stitch_gnd_pad.py` | Bottom-layer tracks cut the ground pour into islands. Which pad ends up cut off changes with every placement |
| 9 | `dedup_vias.py`, `clean_dangling.py` | Two repair rounds can pick the same point, and a dead stub reads to DRC as an unconnected item |
| 10 | `place_silk_after_route.py` | Designators can only dodge tracks once the copper exists |

The chain is **not** reproducible run for run. Freerouting gives the same track
layout, but the number of ground-repair rounds depends on how the pour fell
apart, so via and segment counts move. Every number quoted anywhere about this
board is therefore re-measured from the `.kicad_pcb`, never carried over from an
earlier version of a text.

## What `regen_outputs.ps1` writes, and where

Three destinations, and the split is deliberate: the repository is in English
and public, the written documentation is in Croatian and private, the website is
neither.

| Output | Destination | Note |
|---|---|---|
| `render-top.png`, `render-bottom.png` | `../` (`hardware/kicad/`) | `kicad-cli pcb render`, also used as a documentation figure |
| Gerbers, Excellon drill, gbrjob | `../../gerber/` | see [`../../gerber/README.md`](../../gerber/README.md) |
| `obd2-simulator-v07-for-fabrication.zip` | `../../gerber/` | `make_fab_zip.py`, exactly nine production layers and no auxiliary ones |
| `schema1-4.svg`, `blok.svg`, `canchain.svg` | `../../` (`hardware/`) | `generate_figures.py`, English. The only schematics a GitHub visitor gets |
| `fig/zones.svg`, `fig/nets.svg`, `fig/ip2368.svg` | `fig/` | tracked in git since 30.08.2026. and embedded in `hardware/README.md` |
| `tehnicki-crtez-pcb-v07.svg` / `.png` | `../../../../Pisani dio/Slike za rad/crtezi-ploce/` | `generate_drawing.py`, Croatian, a documentation figure. **Outside the repository** |
| `OBD2-board-v0.7/index.html` | `../../../../Website and GitHub/` | `generate_pcb_html.py`. **Outside the repository**, and never edited by hand |

Two traps worth knowing before running it:

- **The PNG of the dimensioned drawing is rasterised by headless Chrome**, at a
  scale factor picked to land on the size the documentation was laid out around.
  If Chrome is missing the script says so and leaves the old PNG in place, which
  is how a stale drawing once survived a regeneration.
- **The interactive HTML view is generated, so a hand edit vanishes.** Its text
  is edited in `generate_pcb_html.py`: English in the template beside its
  `data-i18n` key, Croatian in the `HR` dictionary in the same template. Its
  final line prints the number of tracks, vias and footprints it drew (892, 73,
  103). If those differ from the numbers in `hardware/README.md`, the board was
  regenerated and the text was not.

## Run by hand, not part of either chain

| Script | When |
|---|---|
| `generate_figures.py` | a schematic changed. It draws **by hand**, not from the board, so it never follows a board change on its own. `--lang hr` still works and nothing calls it |
| `generate_drawing.py` | the outline or a footprint position changed. Compare the result against `../render-top.png`, which is the same board and the only quick way to see whether the layout is right |
| `generate_pcb_html.py` | only that page needs refreshing, without the rest of a regeneration |
| `gen_3dmodels.py` | a custom VRML model changed. Two parts have no model in KiCad's library |
| `apply_3dmodels.py` | only the models changed. It attaches them to the **already routed** board, so the routing survives |
| `route_one_net.py`, `stitch_gnd_pad.py` | finishing one specific net or pad on a board that is otherwise done |
| `make_fab_zip.py` | repacking the fabricator's zip on its own |

## Modules, not scripts

`place.py` (the shelf packer), `models3d.py` (the list of models to attach by
hand) and `placement_locked.py` (frozen coordinates, **currently empty on
purpose**, see `hardware/README.md`) are imported by the generators. Running
them does nothing.

## Subdirectories

| Path | What it is |
|---|---|
| `fig/` | every figure `generate_figures.py` draws. Six are copied up into `hardware/`, three are used from here |
| `docx/` | `.docx` tooling for a machine with no Word. Has its own [`README.md`](docx/README.md) |
| `../tools/` | where `freerouting.jar` goes. Not in the repository, see [`../tools/README.md`](../tools/README.md) |
| `../footprints/obd2.pretty/` | the four custom footprints: CH224K, SEP-A-OBD-D2, SKRHABE010, RK12L12C0A0G |

## Before ordering fabrication

[`../PRE-FABRICATION-CHECKLIST.md`](../PRE-FABRICATION-CHECKLIST.md), without
exception. The custom footprints above were drawn from datasheets, and the
checklist is what catches the one that is wrong.
