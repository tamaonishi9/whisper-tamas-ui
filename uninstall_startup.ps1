$ErrorActionPreference = "Stop"

$appName = "WhisperTamas"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

if (Test-Path -LiteralPath $runKey) {
    Remove-ItemProperty -Path $runKey -Name $appName -ErrorAction SilentlyContinue
}
