# Fixed drawing worker. Labels are JSON stdin data; never PowerShell source.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$scene = [Console]::In.ReadToEnd() | ConvertFrom-Json
$bitmap = [System.Drawing.Bitmap]::new(1000, 860)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$stream = [System.IO.MemoryStream]::new()

function Paint-Text([string]$text, [float]$x, [float]$y, [float]$width, [float]$height,
                    [float]$size, [string]$color, [bool]$rtl = $true, [bool]$center = $false) {
    $font = [System.Drawing.Font]::new('Segoe UI', $size, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
    $brush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($color))
    $format = [System.Drawing.StringFormat]::new()
    try {
        if ($rtl) { $format.FormatFlags = [System.Drawing.StringFormatFlags]::DirectionRightToLeft }
        if ($center) { $format.Alignment = [System.Drawing.StringAlignment]::Center }
        $measured = $graphics.MeasureString($text, $font, [System.Drawing.SizeF]::new($width, 4096), $format)
        if ($measured.Height -gt $height -or $measured.Width -gt ($width + 1)) { throw 'text_does_not_fit' }
        $graphics.DrawString($text, $font, $brush, [System.Drawing.RectangleF]::new($x, $y, $width, $height), $format)
    } finally { $format.Dispose(); $brush.Dispose(); $font.Dispose() }
}

try {
    $graphics.Clear([System.Drawing.ColorTranslator]::FromHtml($scene.colors.background))
    Paint-Text $scene.title 60 15 880 45 28 $scene.colors.text
    Paint-Text $scene.subtitle 60 59 880 32 18 $scene.colors.muted
    foreach ($edge in $scene.edges) {
        $pen = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml($edge.color), 2.5)
        try {
            if ($edge.relation -eq 'parameter_update') { $pen.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dash }
            if ($edge.relation -eq 'preparation') { $pen.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dot }
            for ($i = 1; $i -lt $edge.points.Count; $i++) {
                $a = $edge.points[$i - 1]; $b = $edge.points[$i]
                $graphics.DrawLine($pen, [float]$a[0], [float]$a[1], [float]$b[0], [float]$b[1])
            }
            $a = $edge.points[$edge.points.Count - 2]; $b = $edge.points[$edge.points.Count - 1]
            $angle = [Math]::Atan2(($b[1] - $a[1]), ($b[0] - $a[0]))
            $brush = [System.Drawing.SolidBrush]::new($pen.Color)
            try {
                $points = [System.Drawing.PointF[]]@(
                    [System.Drawing.PointF]::new($b[0], $b[1]),
                    [System.Drawing.PointF]::new(($b[0] - 10 * [Math]::Cos($angle - 0.45)), ($b[1] - 10 * [Math]::Sin($angle - 0.45))),
                    [System.Drawing.PointF]::new(($b[0] - 10 * [Math]::Cos($angle + 0.45)), ($b[1] - 10 * [Math]::Sin($angle + 0.45)))
                )
                $graphics.FillPolygon($brush, $points)
            } finally { $brush.Dispose() }
            if ($null -ne $edge.label_position) {
                Paint-Text $edge.label_ar ($edge.label_position[0] - 110) ($edge.label_position[1] - 19) 220 28 15 $edge.color $true $true
            }
        } finally { $pen.Dispose() }
    }
    foreach ($node in $scene.nodes) {
        $brush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($scene.colors.surface))
        $border = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml($scene.colors.border), 2)
        try {
            $graphics.FillRectangle($brush, $node.x, $node.y, $node.width, $node.height)
            $graphics.DrawRectangle($border, $node.x, $node.y, $node.width, $node.height)
        } finally { $brush.Dispose(); $border.Dispose() }
        Paint-Text $node.label_ar ($node.x + 20) ($node.y + 8) 210 36 24 $scene.colors.text
        Paint-Text $node.term_en ($node.x + 20) ($node.y + 43) 210 28 18 $scene.colors.muted $false
        if ($node.status) {
            Paint-Text $node.status ($node.x + 20) ($node.y + 75) 210 25 16 $node.status_color
        }
    }
    Paint-Text $scene.footer 60 786 880 32 17 $scene.colors.muted
    Paint-Text $scene.source_ref 60 819 880 28 16 $scene.colors.muted $false
    $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
    [Console]::Out.Write([Convert]::ToBase64String($stream.ToArray()))
} finally { $stream.Dispose(); $graphics.Dispose(); $bitmap.Dispose() }
