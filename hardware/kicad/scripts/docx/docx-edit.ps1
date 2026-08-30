Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.Drawing

$script:docPath = $null
$script:xml = $null
$script:media = @{}      # entry name (e.g. 'word/media/image12.png') -> byte[]
$script:log = @()

function Xml-Escape([string]$s) { $s.Replace('&','&amp;').Replace('<','&lt;').Replace('>','&gt;') }
function Xml-Unescape([string]$s) {
    $s.Replace('&lt;','<').Replace('&gt;','>').Replace('&quot;','"').Replace('&apos;',"'").Replace('&amp;','&')
}

function Open-Doc([string]$path) {
    $script:docPath = $path
    $script:media = @{}
    $script:log = @()
    $zip = [System.IO.Compression.ZipFile]::OpenRead($path)
    $entry = $zip.GetEntry('word/document.xml')
    $reader = New-Object System.IO.StreamReader($entry.Open(), [System.Text.Encoding]::UTF8)
    $script:xml = $reader.ReadToEnd()
    $reader.Close(); $zip.Dispose()
}

# Full rebuild in Create mode: copies every entry from the original zip in order,
# substituting word/document.xml and any replaced media.
function Save-AndClose {
    $null = [xml]$script:xml   # throws if edits broke well-formedness - nothing is written then
    $tmp = [System.IO.Path]::GetTempFileName()
    Remove-Item $tmp -Force
    $src = [System.IO.Compression.ZipFile]::OpenRead($script:docPath)
    $dst = [System.IO.Compression.ZipFile]::Open($tmp, 'Create')
    foreach ($e in $src.Entries) {
        $ne = $dst.CreateEntry($e.FullName)
        $os = $ne.Open()
        if ($e.FullName -eq 'word/document.xml') {
            $w = New-Object System.IO.StreamWriter($os, (New-Object System.Text.UTF8Encoding($false)))
            $w.Write($script:xml); $w.Flush(); $w.Close()
        } elseif ($script:media.ContainsKey($e.FullName)) {
            $b = $script:media[$e.FullName]
            $os.Write($b, 0, $b.Length); $os.Close()
        } else {
            $is = $e.Open(); $is.CopyTo($os); $is.Close(); $os.Close()
        }
    }
    $dst.Dispose(); $src.Dispose()
    Copy-Item $tmp $script:docPath -Force
    Remove-Item $tmp -Force
    $script:xml = $null; $script:docPath = $null; $script:media = @{}
}

# --- fragment primitives ---
$script:reWT   = [regex]'<w:t(?: [^>]*)?>(.*?)</w:t>'
$script:rePara = [regex]::new('<w:p(?: [^>]*)?>.*?</w:p>', 'Singleline')
$script:reRow  = [regex]::new('<w:tr(?: [^>]*)?>.*?</w:tr>', 'Singleline')
$script:reCell = [regex]::new('<w:tc(?: [^>]*)?>.*?</w:tc>', 'Singleline')

function Frag-Text([string]$frag) {
    $sb = New-Object System.Text.StringBuilder
    foreach ($m in $script:reWT.Matches($frag)) { [void]$sb.Append((Xml-Unescape $m.Groups[1].Value)) }
    $sb.ToString()
}

function Frag-ReplaceRunAware([string]$frag, [string]$find, [string]$replace) {
    $nodes = $script:reWT.Matches($frag)
    $texts = @(); foreach ($n in $nodes) { $texts += ,(Xml-Unescape $n.Groups[1].Value) }
    $full = ($texts -join '')
    $at = $full.IndexOf($find)
    if ($at -lt 0) { return $null }
    $mEnd = $at + $find.Length
    $sb = New-Object System.Text.StringBuilder; $pos = 0; $off = 0
    for ($i = 0; $i -lt $nodes.Count; $i++) {
        $n = $nodes[$i]; $t = $texts[$i]; $s = $off; $e = $off + $t.Length; $off = $e
        [void]$sb.Append($frag.Substring($pos, $n.Index - $pos)); $pos = $n.Index + $n.Length
        if ($e -le $at -or $s -ge $mEnd) { [void]$sb.Append($n.Value); continue }
        $pre = if ($at -gt $s) { $t.Substring(0, $at - $s) } else { '' }
        $ins = if ($s -le $at) { $replace } else { '' }
        $post = if ($mEnd -lt $e) { $t.Substring($mEnd - $s) } else { '' }
        [void]$sb.Append('<w:t xml:space="preserve">' + (Xml-Escape ($pre + $ins + $post)) + '</w:t>')
    }
    [void]$sb.Append($frag.Substring($pos))
    $sb.ToString()
}

function Frag-SetText([string]$frag, [string]$newText) {
    $nodes = $script:reWT.Matches($frag)
    if ($nodes.Count -eq 0) { return $null }
    $sb = New-Object System.Text.StringBuilder; $pos = 0
    for ($i = 0; $i -lt $nodes.Count; $i++) {
        $n = $nodes[$i]
        [void]$sb.Append($frag.Substring($pos, $n.Index - $pos)); $pos = $n.Index + $n.Length
        if ($i -eq 0) { [void]$sb.Append('<w:t xml:space="preserve">' + (Xml-Escape $newText) + '</w:t>') }
        else { [void]$sb.Append('<w:t></w:t>') }
    }
    [void]$sb.Append($frag.Substring($pos))
    $sb.ToString()
}

function Splice([int]$index, [int]$length, [string]$replacement) {
    $script:xml = $script:xml.Substring(0, $index) + $replacement + $script:xml.Substring($index + $length)
}

function Note([string]$ok, [string]$what) {
    $script:log += ("{0}  {1}" -f $(if ($ok) {'OK  '} else {'FAIL'}), $what)
    if (-not $ok) { Write-Host ("FAIL: " + $what) -ForegroundColor Red }
}

# --- public operations (each returns $true/$false and logs) ---
function Replace-Text([string]$find, [string]$replace) {
    foreach ($m in $script:rePara.Matches($script:xml)) {
        $new = Frag-ReplaceRunAware $m.Value $find $replace
        if ($null -ne $new) { Splice $m.Index $m.Length $new; Note $true "Replace-Text '$find'"; return $true }
    }
    Note $false "Replace-Text '$find'"; return $false
}

# Replace ALL occurrences across the document (loops until no more matches).
function Replace-TextAll([string]$find, [string]$replace) {
    $n = 0
    while (Replace-TextQuiet $find $replace) { $n++ ; if ($n -gt 60) { break } }
    Note ($n -gt 0) "Replace-TextAll '$find' x$n"
    return $n
}
function Replace-TextQuiet([string]$find, [string]$replace) {
    foreach ($m in $script:rePara.Matches($script:xml)) {
        $new = Frag-ReplaceRunAware $m.Value $find $replace
        if ($null -ne $new) { Splice $m.Index $m.Length $new; return $true }
    }
    return $false
}

function Replace-Paragraph([string]$anchor, [string]$newText) {
    foreach ($m in $script:rePara.Matches($script:xml)) {
        if ((Frag-Text $m.Value).Contains($anchor)) {
            $new = Frag-SetText $m.Value $newText
            if ($null -eq $new) { Note $false "Replace-Paragraph '$anchor'"; return $false }
            Splice $m.Index $m.Length $new; Note $true "Replace-Paragraph '$anchor'"; return $true
        }
    }
    Note $false "Replace-Paragraph '$anchor'"; return $false
}

function Insert-ParagraphAfter([string]$anchor, [string]$newText) {
    foreach ($m in $script:rePara.Matches($script:xml)) {
        if ((Frag-Text $m.Value).Contains($anchor)) {
            $clone = Frag-SetText $m.Value $newText
            if ($null -eq $clone) { Note $false "Insert-ParagraphAfter '$anchor'"; return $false }
            Splice ($m.Index + $m.Length) 0 $clone; Note $true "Insert-ParagraphAfter '$anchor'"; return $true
        }
    }
    Note $false "Insert-ParagraphAfter '$anchor'"; return $false
}

function Set-RowCells([string]$marker, [string[]]$cells) {
    foreach ($m in $script:reRow.Matches($script:xml)) {
        if (-not (Frag-Text $m.Value).Contains($marker)) { continue }
        $row = $m.Value
        $tcs = $script:reCell.Matches($row)
        $sb = New-Object System.Text.StringBuilder; $pos = 0
        for ($i = 0; $i -lt $tcs.Count; $i++) {
            $tc = $tcs[$i]
            [void]$sb.Append($row.Substring($pos, $tc.Index - $pos)); $pos = $tc.Index + $tc.Length
            if ($i -lt $cells.Count -and $null -ne $cells[$i]) {
                $newTc = Frag-SetText $tc.Value $cells[$i]
                [void]$sb.Append($(if ($null -ne $newTc) { $newTc } else { $tc.Value }))
            } else { [void]$sb.Append($tc.Value) }
        }
        [void]$sb.Append($row.Substring($pos))
        Splice $m.Index $m.Length $sb.ToString(); Note $true "Set-RowCells '$marker'"; return $true
    }
    Note $false "Set-RowCells '$marker'"; return $false
}

# Delete the whole <w:p> that contains $anchor.
function Remove-Paragraph([string]$anchor) {
    foreach ($m in $script:rePara.Matches($script:xml)) {
        if ((Frag-Text $m.Value).Contains($anchor)) {
            Splice $m.Index $m.Length ''; Note $true "Remove-Paragraph '$anchor'"; return $true
        }
    }
    Note $false "Remove-Paragraph '$anchor'"; return $false
}

# --- media ---
function Get-MediaMap {
    $relsPath = 'word/_rels/document.xml.rels'
    $zip = [System.IO.Compression.ZipFile]::OpenRead($script:docPath)
    $e = $zip.GetEntry($relsPath)
    $r = New-Object System.IO.StreamReader($e.Open(), [System.Text.Encoding]::UTF8)
    [xml]$rels = $r.ReadToEnd(); $r.Close(); $zip.Dispose()
    $map = @{}
    foreach ($rel in $rels.Relationships.Relationship) {
        if ($rel.Target -like 'media/*') { $map[$rel.Id] = 'word/' + $rel.Target }
    }
    return $map
}

function Set-Media([string]$entryName, [string]$pngPath) {
    $script:media[$entryName] = [System.IO.File]::ReadAllBytes($pngPath)
    Note $true "Set-Media $entryName <- $(Split-Path $pngPath -Leaf)"
}

# Rewrite every wp:extent (and its matching a:ext) so the displayed aspect ratio
# equals the PNG's native aspect ratio. Width is kept; height is recomputed.
# $newSizes: optional hashtable image-index (1-based, document order) -> native ratio override.
function Fix-ImageAspect([hashtable]$overrideRatio) {
    $map = Get-MediaMap
    $rx = [regex]'(?s)<wp:extent cx="(\d+)" cy="(\d+)"/>(.*?)r:embed="(rId\w+)"'
    $sb = New-Object System.Text.StringBuilder
    $pos = 0; $i = 0
    foreach ($m in $rx.Matches($script:xml)) {
        $i++
        $cx = [double]$m.Groups[1].Value
        $cy = [double]$m.Groups[2].Value
        $rid = $m.Groups[4].Value
        $entry = $map[$rid]
        $ratio = $null
        if ($null -ne $overrideRatio -and $overrideRatio.ContainsKey($i)) {
            $ratio = [double]$overrideRatio[$i]
        } elseif ($script:media.ContainsKey($entry)) {
            $ms = New-Object System.IO.MemoryStream(,$script:media[$entry])
            $img = [System.Drawing.Image]::FromStream($ms)
            $ratio = $img.Width / $img.Height
            $img.Dispose(); $ms.Dispose()
        } else {
            $zip = [System.IO.Compression.ZipFile]::OpenRead($script:docPath)
            $e = $zip.GetEntry($entry)
            $ms = New-Object System.IO.MemoryStream
            $s = $e.Open(); $s.CopyTo($ms); $s.Close(); $zip.Dispose()
            $ms.Position = 0
            $img = [System.Drawing.Image]::FromStream($ms)
            $ratio = $img.Width / $img.Height
            $img.Dispose(); $ms.Dispose()
        }
        $newCy = [math]::Round($cx / $ratio)
        # cap total height at 20 cm (7 200 000 EMU); shrink width proportionally if needed
        $newCx = $cx
        if ($newCy -gt 7200000) { $newCy = 7200000; $newCx = [math]::Round(7200000 * $ratio) }
        $old = $m.Groups[0].Value
        $new = $old -replace '<wp:extent cx="\d+" cy="\d+"/>', ('<wp:extent cx="' + [int]$newCx + '" cy="' + [int]$newCy + '"/>')
        [void]$sb.Append($script:xml.Substring($pos, $m.Index - $pos))
        [void]$sb.Append($new)
        $pos = $m.Index + $m.Length
        $script:log += ("OK    aspect img#{0} {1}: cy {2} -> {3} (cx {4} -> {5})" -f $i, $entry, [int]$cy, [int]$newCy, [int]$cx, [int]$newCx)
    }
    [void]$sb.Append($script:xml.Substring($pos))
    $script:xml = $sb.ToString()
    # the a:ext inside a:xfrm must mirror wp:extent
    $rx2 = [regex]'(?s)(<wp:extent cx="(\d+)" cy="(\d+)"/>)(.*?)(<a:ext cx="\d+" cy="\d+"/>)'
    $script:xml = $rx2.Replace($script:xml, {
        param($m)
        $m.Groups[1].Value + $m.Groups[4].Value + ('<a:ext cx="' + $m.Groups[2].Value + '" cy="' + $m.Groups[3].Value + '"/>')
    })
}

function Show-Log { $script:log | ForEach-Object { Write-Host $_ } }
