# Рисует иконку, заставку и макет интерфейса Nika в её же палитре.
# Запуск: pwsh -File tools/make_assets.ps1

Add-Type -AssemblyName System.Drawing

$root   = Split-Path -Parent $PSScriptRoot
$accent = [System.Drawing.Color]::FromArgb(200, 30, 58)
$bg     = [System.Drawing.Color]::FromArgb(13, 13, 15)
$black  = [System.Drawing.Color]::FromArgb(0, 0, 0)
$muted  = [System.Drawing.Color]::FromArgb(122, 74, 82)
$userFg = [System.Drawing.Color]::FromArgb(168, 130, 138)
$bubble = [System.Drawing.Color]::FromArgb(20, 20, 24)
$bubbleMine = [System.Drawing.Color]::FromArgb(30, 20, 23)
$chipBg = [System.Drawing.Color]::FromArgb(24, 24, 29)
$line   = [System.Drawing.Color]::FromArgb(44, 30, 35)
$field  = [System.Drawing.Color]::FromArgb(18, 18, 22)

function New-RoundPath([double]$x, [double]$y, [double]$w, [double]$h, [double]$r) {
    $p = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = [Math]::Min($r * 2, [Math]::Min($w, $h))
    if ($d -le 0) { $p.AddRectangle((New-Object System.Drawing.RectangleF($x, $y, $w, $h))); return $p }
    $p.AddArc($x, $y, $d, $d, 180, 90)
    $p.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
    $p.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90)
    $p.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
    $p.CloseFigure()
    return $p
}

function Fill-Round($g, $color, $x, $y, $w, $h, $r) {
    $path = New-RoundPath $x $y $w $h $r
    $brush = New-Object System.Drawing.SolidBrush($color)
    $g.FillPath($brush, $path)
    $brush.Dispose(); $path.Dispose()
}

function Stroke-Round($g, $color, $x, $y, $w, $h, $r, $width) {
    $path = New-RoundPath $x $y $w $h $r
    $pen = New-Object System.Drawing.Pen($color, $width)
    $g.DrawPath($pen, $path)
    $pen.Dispose(); $path.Dispose()
}

function New-Font([string]$name, [double]$size, [bool]$bold) {
    $style = if ($bold) { [System.Drawing.FontStyle]::Bold } else { [System.Drawing.FontStyle]::Regular }
    return New-Object System.Drawing.Font($name, $size, $style, [System.Drawing.GraphicsUnit]::Pixel)
}

function Draw-Text($g, [string]$text, $font, $color, [double]$x, [double]$y, [double]$w, [double]$h, [string]$align) {
    $fmt = New-Object System.Drawing.StringFormat
    $fmt.Alignment = $align
    $fmt.LineAlignment = 'Near'
    $fmt.Trimming = 'None'
    $brush = New-Object System.Drawing.SolidBrush($color)
    $rect = New-Object System.Drawing.RectangleF($x, $y, $w, $h)
    $g.DrawString($text, $font, $brush, $rect, $fmt)
    $brush.Dispose(); $fmt.Dispose()
}

# ======================================================================
#  Иконка 512x512
# ======================================================================
$icon = New-Object System.Drawing.Bitmap(512, 512)
$g = [System.Drawing.Graphics]::FromImage($icon)
$g.SmoothingMode = 'AntiAlias'
$g.TextRenderingHint = 'AntiAliasGridFit'
$g.Clear([System.Drawing.Color]::Transparent)

Fill-Round $g $black 0 0 512 512 96
Fill-Round $g $accent 10 10 492 492 88
Fill-Round $g $black 16 16 480 480 84
Fill-Round $g $bg 22 22 468 468 80

$letterFont = New-Font 'Segoe UI' 300 $true
$fmt = New-Object System.Drawing.StringFormat
$fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
$brush = New-Object System.Drawing.SolidBrush($accent)
$g.DrawString('N', $letterFont, $brush, (New-Object System.Drawing.RectangleF(0, -14, 512, 512)), $fmt)
$brush.Dispose()
# маленькая точка как знак «на связи»
Fill-Round $g $accent 372 372 54 54 27

$icon.Save((Join-Path $root 'assets\icon.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $icon.Dispose()

# ======================================================================
#  Заставка 720x1280
# ======================================================================
$splash = New-Object System.Drawing.Bitmap(720, 1280)
$g = [System.Drawing.Graphics]::FromImage($splash)
$g.SmoothingMode = 'AntiAlias'
$g.TextRenderingHint = 'AntiAliasGridFit'
$g.Clear($bg)

Stroke-Round $g $accent 16 16 688 1248 24 2
$nameFont = New-Font 'Segoe UI' 118 $true
$tagFont = New-Font 'Segoe UI' 30 $false
$fmt = New-Object System.Drawing.StringFormat
$fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
$brush = New-Object System.Drawing.SolidBrush($accent)
$g.DrawString('Nika', $nameFont, $brush, (New-Object System.Drawing.RectangleF(0, 520, 720, 160)), $fmt)
$brush.Dispose()
$brush = New-Object System.Drawing.SolidBrush($muted)
$brush.Dispose()

$splash.Save((Join-Path $root 'assets\presplash.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $splash.Dispose()
Write-Output "готово: assets/icon.png, assets/presplash.png"
