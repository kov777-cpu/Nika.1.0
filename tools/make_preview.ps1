# Макет интерфейса Nika на BeeWare (Toga): тот же вид, что строит nika/app.py.
# Рисуется, потому что Toga не умеет отдавать скриншот виджета, как Kivy.
# Запуск: powershell -ExecutionPolicy Bypass -File tools/make_preview.ps1

Add-Type -AssemblyName System.Drawing

$root   = Split-Path -Parent $PSScriptRoot
$accent = [System.Drawing.Color]::FromArgb(200, 30, 58)
$bg     = [System.Drawing.Color]::FromArgb(13, 13, 15)
$bubble = [System.Drawing.Color]::FromArgb(20, 20, 24)
$mine   = [System.Drawing.Color]::FromArgb(30, 20, 23)
$chipBg = [System.Drawing.Color]::FromArgb(24, 24, 29)
$field  = [System.Drawing.Color]::FromArgb(18, 18, 22)
$muted  = [System.Drawing.Color]::FromArgb(122, 74, 82)
$mutedL = [System.Drawing.Color]::FromArgb(154, 106, 115)
$userFg = [System.Drawing.Color]::FromArgb(168, 130, 138)
$line   = [System.Drawing.Color]::FromArgb(44, 30, 35)

function New-Font([string]$name, [double]$size, [bool]$bold) {
    $style = if ($bold) { [System.Drawing.FontStyle]::Bold } else { [System.Drawing.FontStyle]::Regular }
    return New-Object System.Drawing.Font($name, $size, $style, [System.Drawing.GraphicsUnit]::Pixel)
}

function Draw-Text($g, [string]$text, $font, $color, [double]$x, [double]$y, [double]$w, [double]$h, [string]$align) {
    $fmt = New-Object System.Drawing.StringFormat
    $fmt.Alignment = $align
    $fmt.LineAlignment = 'Near'
    $brush = New-Object System.Drawing.SolidBrush($color)
    $rect = New-Object System.Drawing.RectangleF($x, $y, $w, $h)
    $g.DrawString($text, $font, $brush, $rect, $fmt)
    $brush.Dispose(); $fmt.Dispose()
}

function Fill-Rect($g, $color, $x, $y, $w, $h) {
    $brush = New-Object System.Drawing.SolidBrush($color)
    $g.FillRectangle($brush, $x, $y, $w, $h)
    $brush.Dispose()
}

$W = 525; $H = 1050
$img = New-Object System.Drawing.Bitmap($W, $H)
$g = [System.Drawing.Graphics]::FromImage($img)
$g.SmoothingMode = 'AntiAlias'
$g.TextRenderingHint = 'AntiAliasGridFit'
$g.Clear($bg)

$titleFont  = New-Font 'Segoe UI' 30 $true
$buttonFont = New-Font 'Segoe UI' 15 $false
$bodyFont   = New-Font 'Segoe UI' 17 $false
$smallFont  = New-Font 'Segoe UI' 14 $false
$timerFont  = New-Font 'Segoe UI' 15 $false

# ---------- шапка: только Nika и кнопки, без «рядом» ----------
Draw-Text $g 'Nika' $titleFont $accent 16 16 200 40 'Near'
Fill-Rect $g $accent 355 14 92 34
Draw-Text $g 'голос' $buttonFont $bg 355 22 92 24 'Center'
Fill-Rect $g $chipBg 455 14 44 34
Draw-Text $g '?' $buttonFont $mutedL 455 22 44 24 'Center'

# ---------- полоса таймера ----------
Fill-Rect $g $bubble 0 60 $W 36
Fill-Rect $g $accent 0 60 3 36
Draw-Text $g 'таймер  04:58' $timerFont $accent 16 68 300 24 'Near'
Fill-Rect $g $chipBg 448 66 62 24
Draw-Text $g 'стоп' $smallFont $mutedL 448 70 62 20 'Center'

# ---------- лента сообщений (полосы на всю ширину, как в Toga) ----------
function Add-Row($g, [string]$text, [double]$y, [bool]$mineRow) {
    $fmt = New-Object System.Drawing.StringFormat
    $fmt.Alignment = 'Near'; $fmt.LineAlignment = 'Near'
    $size = $g.MeasureString($text, $bodyFont, [int]($W - 48), $fmt)
    $h = [Math]::Ceiling($size.Height) + 18
    $color = if ($mineRow) { $mine } else { $bubble }
    Fill-Rect $g $color 8 $y ($W - 16) $h
    $align = if ($mineRow) { 'Far' } else { 'Near' }
    $fg = if ($mineRow) { $userFg } else { $accent }
    Draw-Text $g $text $bodyFont $fg 22 ($y + 8) ($W - 44) ($h - 12) $align
    return $y + $h + 6
}

$y = 112
$y = Add-Row $g 'привет) я снова тут. как ты?' $y $false
$y = Add-Row $g 'нормально. позвони маме' $y $true
$y = Add-Row $g "набираю «Мама» — +7 999 000-11-22.`nнажми зелёную кнопку)" $y $false
$y = Add-Row $g "сеть «Home_5G»`nпароль: secret123" $y $false
$y = Add-Row $g 'спасибо)' $y $true
$y = Add-Row $g 'не за что) приятно быть полезной.' $y $false

# ---------- подсказки ----------
$chipY = 902
$chips = @('как дела', 'что ты умеешь', 'пошути')
$x = 10
foreach ($c in $chips) {
    $size = $g.MeasureString($c, $buttonFont)
    $cw = [Math]::Ceiling($size.Width) + 26
    Fill-Rect $g $chipBg $x $chipY $cw 34
    Draw-Text $g $c $buttonFont $mutedL ($x + 13) ($chipY + 8) ($cw - 20) 22 'Near'
    $x += $cw + 10
}

# ---------- строка ввода ----------
$fieldY = 956
Fill-Rect $g $field 10 $fieldY ($W - 20) 60
Draw-Text $g 'напиши или нажми «мик.»' $smallFont $muted 24 ($fieldY + 20) ($W - 40) 26 'Near'
Fill-Rect $g $chipBg ($W - 124) ($fieldY + 10) 56 40
Draw-Text $g 'мик.' $smallFont $mutedL ($W - 124) ($fieldY + 20) 56 24 'Center'
Fill-Rect $g $accent ($W - 60) ($fieldY + 8) 50 44
Draw-Text $g '→' $bodyFont $bg ($W - 60) ($fieldY + 14) 50 28 'Center'

$img.Save((Join-Path $root 'docs\preview.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $img.Dispose()
Write-Output "готово: docs/preview.png"
