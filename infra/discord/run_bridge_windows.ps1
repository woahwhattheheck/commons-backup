[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$python = (Get-Command python.exe -ErrorAction Stop).Source
$bridgeScript = Join-Path $PSScriptRoot "commons_discord_bridge.py"

# Compatibility standby only. The scheduled-task action supplies
# -WindowStyle Hidden; verified cloud cutover unregisters this task entirely.
& $python -B $bridgeScript *> $null
exit $LASTEXITCODE
