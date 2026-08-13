# Reading-interest collector - install (Windows, PowerShell)
# Usage:  powershell -ExecutionPolicy Bypass -File scripts/install.ps1
#
# Creates a venv next to the repo, installs deps, and writes a default
# config.json if none exists.

param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$venv = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "Creating venv at $venv"
    python -m venv $venv
}

$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt

# Default config if missing
$cfgDir = Join-Path $env:USERPROFILE ".reading-collector"
$cfgPath = Join-Path $cfgDir "config.json"
if (-not (Test-Path $cfgPath)) {
    New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
    Copy-Item (Join-Path $RepoRoot "config.default.json") $cfgPath
    Write-Host "Wrote default config to $cfgPath"
} else {
    Write-Host "Config already exists: $cfgPath"
}

Write-Host "Install complete. Edit hotkeys in $cfgPath"
Write-Host "Run with:  .\run.ps1   (or  scripts\run.ps1)"
