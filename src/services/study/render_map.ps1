# Fixed drawing program. Paper/model text is JSON stdin data, never PowerShell code.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
$height = 180 + 190 * $payload.nodes.Count
$bitmap = New-Object System.Drawing.Bitmap(1000, $height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$font = New-Object System.Drawing.Font('Segoe UI', 22)
$small = New-Object System.Drawing.Font('Segoe UI', 14)
$white = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
$muted = New-Object System.Drawing.SolidBrush([System.Drawing.ColorTranslator]::FromHtml('#b3c7d4'))
$panel = New-Object System.Drawing.SolidBrush([System.Drawing.ColorTranslator]::FromHtml('#1d4253'))
$accent = New-Object System.Drawing.Pen([System.Drawing.ColorTranslator]::FromHtml('#56d4b1'), 3)
$rtl = New-Object System.Drawing.StringFormat
$rtl.FormatFlags = [System.Drawing.StringFormatFlags]::DirectionRightToLeft
$rtl.Alignment = [System.Drawing.StringAlignment]::Near
$stream = New-Object System.IO.MemoryStream
try {
    $graphics.Clear([System.Drawing.ColorTranslator]::FromHtml('#102332'))
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $graphics.DrawString([string]$payload.title, $font, $white, [System.Drawing.RectangleF]::new(60, 30, 880, 50), $rtl)
    $graphics.DrawString([string]$payload.subtitle, $small, $muted, [System.Drawing.RectangleF]::new(60, 88, 880, 40), $rtl)
    for ($index = 0; $index -lt $payload.nodes.Count; $index++) {
        $top = 145 + 190 * $index
        $graphics.FillRectangle($panel, 60, $top, 880, 150)
        $graphics.DrawRectangle($accent, 60, $top, 880, 150)
        $node = $payload.nodes[$index]
        $graphics.DrawString([string]$node.label, $font, $white, [System.Drawing.RectangleF]::new(80, $top + 10, 840, 45), $rtl)
        $graphics.DrawString([string]$node.body, $small, $muted, [System.Drawing.RectangleF]::new(80, $top + 55, 840, 60), $rtl)
        $graphics.DrawString([string]$node.refs, $small, $muted, [System.Drawing.PointF]::new(80, $top + 121))
        if ($index -lt $payload.nodes.Count - 1) {
            $graphics.DrawLine($accent, 500, $top + 154, 500, $top + 184)
            $graphics.DrawLine($accent, 493, $top + 176, 500, $top + 184)
            $graphics.DrawLine($accent, 507, $top + 176, 500, $top + 184)
        }
    }
    $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
    [Console]::Out.Write([Convert]::ToBase64String($stream.ToArray()))
}
finally {
    $stream.Dispose(); $graphics.Dispose(); $bitmap.Dispose(); $font.Dispose(); $small.Dispose()
    $white.Dispose(); $muted.Dispose(); $panel.Dispose(); $accent.Dispose(); $rtl.Dispose()
}
