# Regenerates every derived file from the finished, routed board.
# Does not touch placement or routing - route_board.ps1 does that.
#
#   powershell -ExecutionPolicy Bypass -File kicad\scripts\regen_outputs.ps1
# Derived from the script location, so the chain runs from any clone.
$repo = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$hw   = Join-Path $repo "hardware"
$k    = "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin"
$env:KICAD_SHARE = "$env:LOCALAPPDATA\Programs\KiCad\10.0\share\kicad"
$pcb  = "$hw\kicad\obd2-simulator.kicad_pcb"
$REV  = "v07"
# The dimensioned drawing belongs to the written documentation rather than to
# this repository, so it is written straight out of it. The repository keeps
# the English schematics. Override the destination with OBD2_DRAWING_DIR.
$fig  = if ($env:OBD2_DRAWING_DIR) { $env:OBD2_DRAWING_DIR }
        else { Join-Path $repo "..\Pisani dio\Slike za rad\crtezi-ploce" }
New-Item -ItemType Directory -Force $fig | Out-Null
# The interactive board view is a website artefact and lives with the rest of
# the website material. Override the destination with OBD2_WEB_DIR.
$web  = if ($env:OBD2_WEB_DIR) { $env:OBD2_WEB_DIR }
        else { Join-Path $repo "..\Website and GitHub" }
if (-not (Test-Path $web)) { throw "website folder not found: $web" }

Write-Output "== renders =="
& "$k\kicad-cli.exe" pcb render -o "$hw\kicad\render-top.png" --side top `
    --width 1700 --height 1500 --use-board-stackup-colors $pcb | Out-Null
& "$k\kicad-cli.exe" pcb render -o "$hw\kicad\render-bottom.png" --side bottom `
    --width 1700 --height 1500 --use-board-stackup-colors $pcb | Out-Null

Write-Output "== gerbers and drill =="
& "$k\kicad-cli.exe" pcb export gerbers -o "$hw\gerber" $pcb | Out-Null
& "$k\kicad-cli.exe" pcb export drill -o "$hw\gerber" --format excellon $pcb | Out-Null
# Fabrication package: production layers only, no auxiliary ones. See
# make_fab_zip.py for the list and the reasoning.
& "$k\python.exe" "$hw\kicad\scripts\make_fab_zip.py" "$hw\gerber" `
    "$hw\gerber\obd2-simulator-$REV-for-fabrication.zip"

Write-Output "== dimensioned drawing =="
& "$k\python.exe" "$hw\kicad\scripts\generate_drawing.py" $pcb "$fig\tehnicki-crtez-pcb-$REV.svg"
# The Croatian documentation embeds the PNG, not the SVG, so the SVG is
# rasterised right here. Without this step the PNG silently keeps showing an
# older board - that is exactly what happened on 10.08.2026.
# Chrome is the rasteriser because this machine has neither Inkscape nor
# cairosvg. The scale factor turns the 1289 x 841 SVG into a 1500 x 979 PNG,
# which is the size the documentation was laid out around.
$chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
if (Test-Path $chrome) {
    $svgUri = ([System.Uri]"$fig\tehnicki-crtez-pcb-$REV.svg").AbsoluteUri
    & $chrome --headless --disable-gpu --hide-scrollbars `
        --screenshot="$fig\tehnicki-crtez-pcb-$REV.png" `
        --window-size=1289,841 --force-device-scale-factor=1.16369 `
        --default-background-color=FFFFFFFF $svgUri | Out-Null
} else {
    Write-Output "   !! Chrome not found, tehnicki-crtez-pcb-$REV.png NOT refreshed"
}

Write-Output "== interactive view =="
# The page is a web artefact, not something needed to build the board, so since
# 15.08.2026. it lives with the rest of the website material. Regenerating it
# from here keeps it in step with the board. It carries its own EN/HR switch,
# with English as the default, like every other page in that folder.
# The output path is the one index.html links to from its Hardware section. If
# it is ever changed, change it there too, and in Website and GitHub\README.md.
& "$k\python.exe" "$hw\kicad\scripts\generate_pcb_html.py" $pcb "$web\OBD2-board-v0.7\index.html"

Write-Output "== schematics and diagrams, English (repository) =="
# Only the English set is generated. Until 15.08.2026. this step ran twice and
# copied a Croatian set into $fig as well, but nothing ever read it: the written
# documentation embeds a separate figure set from its own generator, and the
# only drawing it takes from here is the dimensioned one above. Verified by MD5
# against every image inside the .docx. The Croatian mode itself is untouched
# and still available on demand:
#     python.exe generate_figures.py --lang hr
Push-Location "$hw\kicad\scripts"
& "$k\python.exe" "$hw\kicad\scripts\generate_figures.py"
Pop-Location
# Only the circuit figures are copied up into hardware\, because those are the
# ones a GitHub visitor gets as "the schematic". The zone map, the net table and
# the CH224K detail stay in fig\, but since 30.08.2026. that directory is tracked
# in git too and hardware\README.md embeds all three, so nothing here is
# throwaway output any more.
foreach ($f in @("blok", "canchain", "schema1", "schema2", "schema3", "schema4")) {
    $src = "$hw\kicad\scripts\fig\$f.svg"
    if (Test-Path $src) { Copy-Item $src "$hw\$f.svg" -Force }
}

Write-Output "== done =="
