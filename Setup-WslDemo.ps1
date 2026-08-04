# PowerShell helper: prepare keys, run WSL target setup, write .env
# Usage:
#   cd D:\Flytxt\CCAD\ssh-service-demo
#   .\Setup-WslDemo.ps1

$ErrorActionPreference = "Stop"
$DemoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$KeyPath = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
$PubKeyPath = "$KeyPath.pub"

function Convert-ToWslPath([string]$WindowsPath) {
    # Prefer wslpath when available
    try {
        $converted = (wsl -d Ubuntu -e wslpath -a $WindowsPath 2>$null)
        if ($converted) { return $converted.Trim() }
    } catch { }

    $full = (Resolve-Path $WindowsPath).Path
    $drive = $full.Substring(0, 1).ToLower()
    $rest = $full.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$rest"
}

Write-Host "==> Ensuring SSH key exists on Windows" -ForegroundColor Cyan
if (-not (Test-Path $KeyPath)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $env:USERPROFILE ".ssh") | Out-Null
    ssh-keygen -t ed25519 -f $KeyPath -N '""'
}

Write-Host "==> Installing public key into WSL authorized_keys" -ForegroundColor Cyan
$pub = ((Get-Content $PubKeyPath -Raw) -replace "`r", "").Trim()
# Single-line bash avoids PowerShell CRLF leaking into Linux paths
wsl -d Ubuntu -e bash -lc "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && grep -qxF '$pub' ~/.ssh/authorized_keys || echo '$pub' >> ~/.ssh/authorized_keys"

Write-Host "==> Running WSL target setup script" -ForegroundColor Cyan
$wslScript = Convert-ToWslPath (Join-Path $DemoRoot "setup-wsl-target.sh")
Write-Host "  Script path in WSL: $wslScript"
wsl -d Ubuntu -e bash -lc "sed -i 's/\r`$//' '$wslScript' && bash '$wslScript'"

Write-Host "==> Reading WSL user + IP" -ForegroundColor Cyan
$wslUser = (wsl -d Ubuntu -e bash -lc "whoami").Trim()
$wslIp = (wsl -d Ubuntu -e bash -lc "hostname -I | awk '{print `$1}'").Trim()

if (-not $wslIp) {
    throw "Could not read WSL IP. Is Ubuntu running? Try: wsl -d Ubuntu"
}

$envPath = Join-Path $DemoRoot ".env"
# Write .env without UTF-8 BOM (PowerShell 5 "utf8" adds BOM and breaks dotenv keys)
$envBody = @(
    "SSH_HOST=$wslUser@$wslIp"
    "SSH_IDENTITY_FILE=$KeyPath"
    "SSH_PORT=22"
    "SSH_WORKING_DIR=/tmp"
    "SSH_ALLOW_UNKNOWN_HOSTS=true"
    "SERVICE_NAME=billing-api.service"
    "LOG_FILE_PATH=/var/log/billing-api/application.log"
    "SUMMARY_OUTPUT_PATH=$DemoRoot\reports\healing-summary.json"
    "RESTART_COOLDOWN_SECONDS=300"
    "MAX_RETRY_ATTEMPTS=3"
    "STARTUP_TIMEOUT_SECONDS=120"
) -join "`n"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($envPath, $envBody + "`n", $utf8NoBom)

Write-Host ""
Write-Host "Wrote $envPath" -ForegroundColor Green
Write-Host "  SSH_HOST = $wslUser@$wslIp"
Write-Host ""
Write-Host "Test SSH:" -ForegroundColor Cyan
Write-Host "  ssh -i `"$KeyPath`" $wslUser@$wslIp"
Write-Host ""
Write-Host "Then install agent deps and run:" -ForegroundColor Cyan
Write-Host "  cd `"$DemoRoot`""
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  pip install -r requirements.txt"
Write-Host "  python self_healing_agent.py"
