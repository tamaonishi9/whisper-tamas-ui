$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
$distDir = Join-Path $projectRoot "dist\whisper-tamas-ui"

pyinstaller `
  main.py `
  --name whisper-tamas-ui `
  --onedir

Copy-Item `
  -LiteralPath (Join-Path $projectRoot "config.toml") `
  -Destination (Join-Path $distDir "config.toml") `
  -Force
