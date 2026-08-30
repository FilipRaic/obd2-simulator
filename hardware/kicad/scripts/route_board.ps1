# Board routing chain: build -> dsn -> freerouting (up to 10 attempts) ->
# ses_import -> DRC. Keeps the best result (best.kicad_pcb -> board).
# Derived from the script location, so the chain runs from any clone.
$hw   = (Resolve-Path "$PSScriptRoot\..").Path
$work = Join-Path $env:TEMP "claude\obd2-fr"
$k    = "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin"
$java = "C:\Program Files\Eclipse Adoptium\jdk-25.0.4.7-hotspot\bin\java.exe"
$env:KICAD_SHARE = "$env:LOCALAPPDATA\Programs\KiCad\10.0\share\kicad"
$env:U6_ROT = "-90"
$pcb  = "$hw\obd2-simulator.kicad_pcb"
New-Item -ItemType Directory -Force $work | Out-Null

# IMPORTANT: build_board must abort the whole chain when it fails. Otherwise the
# OLD .kicad_pcb gets routed and the DRC report describes a placement that no
# longer exists in the script (this happened on 2026-08-04, when C1 no longer
# fitted inside its zone).
& "$k\python.exe" "$hw\scripts\build_board.py" $pcb
if ($LASTEXITCODE -ne 0) { Write-Output "build_board.py FAILED - aborting"; exit 1 }
# The CAN pair goes FIRST, while the board is still empty. Freerouting routes a
# minimum spanning tree and knows nothing about the required transceiver ->
# termination -> ESD -> connector order, so on the first routed board the ESD
# diode hung off a 13 mm stub and CANL carried a via. Routing it first gives the
# pair the whole top layer, and dsn_export hands it to the router as a fixed
# obstacle. See route_can_chain.py.
& "$k\python.exe" "$hw\scripts\route_can_chain.py" $pcb
if ($LASTEXITCODE -ne 0) { Write-Output "route_can_chain.py did NOT close the chain - continuing, but check it" }
& "$k\python.exe" "$hw\scripts\dsn_export.py" $pcb "$work\board.dsn" | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Output "dsn_export.py FAILED - aborting"; exit 1 }
Copy-Item $pcb "$work\placed.kicad_pcb" -Force

$bestScore = 99999
# NOTE 2026-08-04: on this dense THT board Freerouting is NOT deterministic -
# the same .dsn yields a different number of unrouted nets from run to run.
# Hence several attempts and picking the best one.
for ($i = 1; $i -le 10; $i++) {
    $ses = "$work\r$i.ses"
    $out = & $java -jar "$hw\tools\freerouting.jar" -de "$work\board.dsn" -do $ses -mp 300 2>&1
    $nets = @($out | Select-String -Pattern "^  Net '" | ForEach-Object { ($_ -split "'")[1] })
    $signal = @($nets | Where-Object { $_ -ne "GND" })

    Copy-Item "$work\placed.kicad_pcb" $pcb -Force
    & "$k\python.exe" "$hw\scripts\ses_import.py" $pcb $ses | Out-Null
    & "$k\kicad-cli.exe" pcb drc -o "$work\drc.json" --format json $pcb | Out-Null
    $j = Get-Content "$work\drc.json" -Raw | ConvertFrom-Json
    $v = @($j.violations).Count
    $u = @($j.unconnected_items).Count
    $score = $v * 10 + $u + $signal.Count * 5
    Write-Output ("run {0}: unrouted=[{1}]  violations={2}  unconnected={3}" -f $i, ($nets -join ","), $v, $u)

    if ($score -lt $bestScore) {
        $bestScore = $score
        Copy-Item $pcb "$work\best.kicad_pcb" -Force
        Write-Output "   -> new best"
    }
    if ($v -eq 0 -and $u -eq 0 -and $signal.Count -eq 0) { Write-Output "   PERFECT"; break }
}
Copy-Item "$work\best.kicad_pcb" $pcb -Force
# Restore the CAN chain. Freerouting did not rip it up (it was marked "protect"),
# but it laid its own trace alongside, so CANH came out as 42 segments with 19
# branches instead of 11 segments without a branch. The space was reserved anyway.
& "$k\python.exe" "$hw\scripts\route_can_chain.py" $pcb --replay
# At this density Freerouting occasionally leaves one signal net unconnected, and
# any placement shift that fixes it usually breaks another net. Such leftovers are
# finished with our own maze router (0.2 mm grid, both layers).
$rest = (& "$k\kicad-cli.exe" pcb drc -o "$work\drc-pre.json" --format json $pcb) | Out-Null
$pre = Get-Content "$work\drc-pre.json" -Raw | ConvertFrom-Json
$open = @($pre.unconnected_items | ForEach-Object { $_.items } |
          ForEach-Object { $_.description } |
          Select-String -Pattern '\[([A-Za-z0-9_+\-]+)\]' -AllMatches |
          ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } |
          Where-Object { $_ -ne 'GND' } | Select-Object -Unique)
if ($open) {
    Write-Output ("finishing nets: " + ($open -join ", "))
    & "$k\python.exe" "$hw\scripts\route_one_net.py" $pcb @open
}
# The GND pour tends to end up in 2-3 fragments (B.Cu traces cut it up): bridge
# the secondary fragments onto the main one with a pair of vias plus a short F.Cu
# trace, then remove floating islands and dead trace leftovers.
& "$k\python.exe" "$hw\scripts\heal_gnd_fragments.py" $pcb
# Reference designators are placed in build_board.py BEFORE routing, so at that
# point they can only avoid pads, not traces. Only now, with copper on the board,
# can they be moved clear of a trace and set horizontal.
# If bridging the pour left a dangling ground island (typically around a THT pad
# that ended up in a pocket between traces), finish it with the maze router.
# GND used to be excluded from that step, because an "unrouted ground" is usually
# just a pour fragment. But when heal_gnd_fragments.py reports that NOT everything
# was bridged, the remainder is a real break and must be routed like any other net.
$g = (& "$k\kicad-cli.exe" pcb drc -o "$work\drc-gnd.json" --format json $pcb) | Out-Null
$gj = Get-Content "$work\drc-gnd.json" -Raw | ConvertFrom-Json
if (@($gj.unconnected_items).Count -gt 0) {
    Write-Output "finishing ground"
    & "$k\python.exe" "$hw\scripts\route_one_net.py" $pcb GND
}
& "$k\python.exe" "$hw\scripts\clean_dangling.py" $pcb
# Final ground repair round (2026-08-09). clean_dangling.py refills the zones at
# the end, and that can create a new isolated island that did not exist before it
# ran - the board would then finish with unconnected ground even though the repair
# step already passed. So after it we check once more and, if needed, repeat the
# bridging and finishing. Two rounds are enough: each further one works on ever
# smaller leftovers.
for ($r = 1; $r -le 2; $r++) {
    & "$k\kicad-cli.exe" pcb drc -o "$work\drc-r$r.json" --format json $pcb | Out-Null
    $rj = Get-Content "$work\drc-r$r.json" -Raw | ConvertFrom-Json
    if (@($rj.unconnected_items).Count -eq 0) { break }
    Write-Output ("final ground repair, round {0}: {1} unconnected" -f $r, @($rj.unconnected_items).Count)
    & "$k\python.exe" "$hw\scripts\heal_gnd_fragments.py" $pcb
    & "$k\python.exe" "$hw\scripts\route_one_net.py" $pcb GND
    & "$k\python.exe" "$hw\scripts\clean_dangling.py" $pcb
    # Two repair rounds can pick the same bridging point, so two vias end up in
    # the same spot. DRC reports that as a 0.0000 mm hole clearance, which sounds
    # dramatic and is only a duplicate entry.
    & "$k\python.exe" "$hw\scripts\dedup_vias.py" $pcb
}
# If a dangling ground pad is still left after that, stitch it onto the main pour
# individually. This happens when a pad has only a millimetre or two of top-layer
# escape, so the via at the end of that escape lands in an island instead of the
# main pour - that is how pad 1 of module U6 ended up on the final revision.
& "$k\kicad-cli.exe" pcb drc -o "$work\drc-pads.json" --format json $pcb | Out-Null
$pj = Get-Content "$work\drc-pads.json" -Raw | ConvertFrom-Json
$pads = @($pj.unconnected_items | ForEach-Object { $_.items } |
          ForEach-Object { $_.description } |
          Select-String -Pattern '^Pad (\S+) \[GND\] of (\S+)' -AllMatches |
          ForEach-Object { "$($_.Matches[0].Groups[2].Value).$($_.Matches[0].Groups[1].Value)" } |
          Select-Object -Unique)
foreach ($p in $pads) {
    Write-Output "stitching ground pad $p onto the main pour"
    & "$k\python.exe" "$hw\scripts\stitch_gnd_pad.py" $pcb $p
}
# WARNING: this overwrites the position of every reference designator on the
# silkscreen. On 11.08.2026. 59 of them were moved by hand in KiCad, and running
# this line throws that work away. If the board on disk carries hand-placed
# labels, comment the line out, or accept that the labels go back to whatever
# the script computes and redo the manual pass afterwards. Nothing else in this
# file touches the silkscreen.
& "$k\python.exe" "$hw\scripts\place_silk_after_route.py" $pcb
& "$k\kicad-cli.exe" pcb drc -o "$work\drc-final.json" --format json $pcb | Out-Null
$j = Get-Content "$work\drc-final.json" -Raw | ConvertFrom-Json
Write-Output ("FINAL: violations={0} unconnected={1}" -f @($j.violations).Count, @($j.unconnected_items).Count)
