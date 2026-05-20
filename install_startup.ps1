$ErrorActionPreference = "Stop"

$appName = "WhisperTamas"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$exePath = Join-Path $scriptRoot "WhisperTamas.exe"
$venvPython = Join-Path $scriptRoot ".venv\Scripts\python.exe"
$mainPy = Join-Path $scriptRoot "main.py"

if (Test-Path -LiteralPath $exePath) {
    $command = '"' + $exePath + '"'
} elseif ((Test-Path -LiteralPath $venvPython) -and (Test-Path -LiteralPath $mainPy)) {
    $command = '"' + $venvPython + '" "' + $mainPy + '"'
} elseif (Test-Path -LiteralPath $mainPy) {
    $command = 'python "' + $mainPy + '"'
} else {
    throw "Startup target not found."
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
New-Item -Path $runKey -Force | Out-Null
Set-ItemProperty -Path $runKey -Name $appName -Value $command
