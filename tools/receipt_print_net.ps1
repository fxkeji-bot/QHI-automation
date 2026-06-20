# receipt_print_net.ps1
# .NET PrintDocument 方式打印 80mm 热敏小票
# 用法: powershell -File receipt_print_net.ps1 -TextFile <path> -PrinterName <name>
param(
    [Parameter(Mandatory=$true)]
    [string]$TextFile,

    [Parameter(Mandatory=$true)]
    [string]$PrinterName
)

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

# ── 纸张尺寸：80 × 297 mm（热敏纸） ──
$paperWidthMM  = 80
$paperHeightMM = 297

# ── 边距（英寸） ──
$marginLeft   = 10 / 72.0   # 10pt → 英寸
$marginRight  = 10 / 72.0
$marginTop    = 2 / 72.0
$marginBottom = 2 / 72.0

# ── 字体 ──
$fontName = "SimSun"
$fontSize = 9
$font = New-Object System.Drawing.Font($fontName, $fontSize, [System.Drawing.FontStyle]::Regular)

# ── 读取文本 ──
if (-not (Test-Path $TextFile)) {
    Write-Error "File not found: $TextFile"
    exit 1
}
$lines = Get-Content -Path $TextFile -Encoding UTF8

# ── 构建 PrintDocument ──
$doc = New-Object System.Drawing.Printing.PrintDocument
$doc.DocumentName = "QHI Receipt"
$doc.PrinterSettings.PrinterName = $PrinterName

# 设置纸张大小（80 × 297 mm）
$paperSize = New-Object System.Drawing.Printing.PaperSize("80x297mm", 
    [int]($paperWidthMM * 100 / 25.4), 
    [int]($paperHeightMM * 100 / 25.4))
$doc.DefaultPageSettings.PaperSize = $paperSize

# 设置边距
$doc.DefaultPageSettings.Margins = New-Object System.Drawing.Printing.Margins(
    [int]($marginLeft * 100),
    [int]($marginRight * 100),
    [int]($marginTop * 100),
    [int]($marginBottom * 100))

# 行计数器
$lineIndex = 0

# PrintPage 事件
$doc.Add_PrintPage({
    param($sender, $e)

    $graphics = $e.Graphics
    $pageWidth = $e.PageBounds.Width
    $leftMargin = $e.MarginBounds.Left
    $topMargin = $e.MarginBounds.Top
    $printableWidth = $e.MarginBounds.Width

    $brush = [System.Drawing.Brushes]::Black
    $lineHeight = $font.GetHeight($graphics)
    $y = $topMargin

    while ($lineIndex -lt $lines.Count) {
        $line = $lines[$lineIndex]
        $graphics.DrawString($line, $font, $brush, $leftMargin, $y)
        $y += $lineHeight
        $lineIndex++

        if ($y + $lineHeight -gt $e.MarginBounds.Bottom) {
            $e.HasMorePages = ($lineIndex -lt $lines.Count)
            return
        }
    }
    $e.HasMorePages = $false
})

# 打印
try {
    $doc.Print()
    Write-Output "PRINT_OK:$PrinterName"
} catch {
    Write-Error "Print failed: $_"
    exit 1
} finally {
    $doc.Dispose()
    $font.Dispose()
}
