# Reading-interest collector - start the background daemon (Windows, PowerShell)
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\run.ps1
#
# Launches the collector hidden in the background. It runs until stopped.
# Check it is alive and see recent rows with scripts\manage.py.

param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$venv = Join-Path $RepoRoot ".venv"
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No venv found. Run scripts\install.ps1 first."
    exit 1
}

$log = Join-Path $RepoRoot "collector.log"
# -u = unbuffered so the log is readable live
Start-Process -FilePath $py -ArgumentList "-u", "-m", "collector.main" `
    -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $log

Write-Host "Collector launched (hidden). Log: $log"
Write-Host "Verify:  python scripts\manage.py stats"

# Note: stop the daemon with:
#   Get-Process python | Where-Object { $_.Path -like "*$venv*" } | Stop-Process
