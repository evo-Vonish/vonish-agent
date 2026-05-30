# VonishAgent Tray Launcher
# Requires: powershell -ExecutionPolicy Bypass -File tray.ps1
# Right-click tray icon for: Open | Restart Backend | Stop Backend | Exit

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"
$url = "http://127.0.0.1:8000"
$backendProcess = $null

# ── Helpers ──────────────────────────────────────────
function Start-Backend {
    param([bool]$wait = $true)
    $running = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
    if ($running) {
        Write-Host "[VonishAgent] 后端已在运行"
        return $true
    }
    Write-Host "[VonishAgent] 启动后端..."
    $proc = Start-Process -FilePath $venvPython -ArgumentList $mainPy `
        -WorkingDirectory $backend -WindowStyle Minimized -PassThru
    $script:backendProcess = $proc

    if ($wait) {
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 1
            $check = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
            if ($check) { Write-Host "[VonishAgent] 就绪"; return $true }
        }
        Write-Host "[VonishAgent] 启动超时"
    }
    return $false
}

function Stop-Backend {
    $proc = Get-Process | Where-Object {
        $_.ProcessName -eq "python" -and $_.MainWindowTitle -like "*VonishAgent*"
    }
    if ($proc) {
        $proc | ForEach-Object { $_.Kill() }
        Write-Host "[VonishAgent] 后端已停止"
    }
    # Also kill by port
    $conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
    if ($conn) {
        $pid = $conn.OwningProcess
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    }
}

function Open-Browser { Start-Process $url }

# ── Tray Icon ────────────────────────────────────────
$icon = [System.Drawing.Icon]::ExtractAssociatedIcon(
    [System.Windows.Forms.Application]::ExecutablePath
)
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = $icon
$notify.Text = "VonishAgent"
$notify.Visible = $true
$notify.BalloonTipTitle = "VonishAgent"
$notify.BalloonTipText = "后端运行中 — 点击打开"
$notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info

# Context menu
$menu = New-Object System.Windows.Forms.ContextMenuStrip

$openItem = New-Object System.Windows.Forms.ToolStripMenuItem
$openItem.Text = "打开 VonishAgent"
$openItem.Add_Click({ Open-Browser })

$restartItem = New-Object System.Windows.Forms.ToolStripMenuItem
$restartItem.Text = "重启后端"
$restartItem.Add_Click({
    Stop-Backend; Start-Sleep -Seconds 1; Start-Backend
})

$stopItem = New-Object System.Windows.Forms.ToolStripMenuItem
$stopItem.Text = "停止后端"
$stopItem.Add_Click({ Stop-Backend })

$sep = New-Object System.Windows.Forms.ToolStripSeparator

$exitItem = New-Object System.Windows.Forms.ToolStripMenuItem
$exitItem.Text = "退出"
$exitItem.Add_Click({
    Stop-Backend
    $notify.Visible = $false
    $notify.Dispose()
    [System.Windows.Forms.Application]::Exit()
})

$menu.Items.AddRange(@($openItem, $restartItem, $stopItem, $sep, $exitItem))
$notify.ContextMenuStrip = $menu
$notify.Add_MouseClick({
    if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
        Open-Browser
    }
})

# ── Start ────────────────────────────────────────────
if (-not (Test-Path $venvPython)) {
    [System.Windows.Forms.MessageBox]::Show(
        "虚拟环境未找到: $venvPython`n请先安装依赖。",
        "VonishAgent", "OK", "Error"
    )
    exit 1
}
$mainPy = Join-Path $backend "main.py"
Start-Backend

if ($notify.BalloonTipText) { $notify.ShowBalloonTip(2000) }

# Keep alive
[System.Windows.Forms.Application]::Run()
