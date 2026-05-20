$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
$distRoot = Join-Path $projectRoot "dist"
$distDir = Join-Path $distRoot "WhisperTamas"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

& $pythonExe -m PyInstaller `
  --noconfirm `
  --distpath $distRoot `
  --workpath (Join-Path $projectRoot "build") `
  whisper-tamas-ui.spec

Copy-Item `
  -LiteralPath (Join-Path $projectRoot "config.toml") `
  -Destination (Join-Path $distDir "config.toml") `
  -Force

Copy-Item `
  -LiteralPath (Join-Path $projectRoot "install_startup.ps1") `
  -Destination (Join-Path $distDir "install_startup.ps1") `
  -Force

Copy-Item `
  -LiteralPath (Join-Path $projectRoot "uninstall_startup.ps1") `
  -Destination (Join-Path $distDir "uninstall_startup.ps1") `
  -Force
