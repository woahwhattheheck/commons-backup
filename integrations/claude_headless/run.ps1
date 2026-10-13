$ErrorActionPreference = "Stop"

# Start the headless Claude gateway on 127.0.0.1:8879 as a console-free
# background process and print its /health once it answers. Idempotent: if a
# gateway already answers on the port, that one is reported and nothing new
# is started. Extra arguments are passed through to gateway.py.
#
#   integrations\claude_headless\run.ps1
#   integrations\claude_headless\run.ps1 -Port 8879
param(
    [int]$Port = 8879,
    [Parameter(ValueFromRemainingArguments = $true)] [string[]]$GatewayArgs
)

$health = "http://127.0.0.1:$Port/health"
try {
    $existing = Invoke-RestMethod -Uri $health -TimeoutSec 2
    Write-Output (@{ ready = $true; already_running = $true; listen = "http://127.0.0.1:$Port"; health = $existing } | ConvertTo-Json -Compress -Depth 6)
    exit 0
} catch {}

$python = (Get-Command python -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }
$gateway = Join-Path $PSScriptRoot "gateway.py"
$stateDir = Join-Path $HOME ".commons\claude_headless"
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$log = Join-Path $stateDir "gateway.log"

$proc = Start-Process -FilePath $pythonw -ArgumentList (@("`"$gateway`"") + $GatewayArgs) -WindowStyle Hidden -WorkingDirectory $HOME -RedirectStandardOutput $log -RedirectStandardError (Join-Path $stateDir "gateway.err.log") -PassThru
Set-Content -Path (Join-Path $stateDir "gateway.pid") -Value $proc.Id -Encoding ascii

$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    try {
        $h = Invoke-RestMethod -Uri $health -TimeoutSec 2
        Write-Output (@{ ready = $true; listen = "http://127.0.0.1:$Port"; pid = $proc.Id; log = $log; health = $h } | ConvertTo-Json -Compress -Depth 6)
        exit 0
    } catch { Start-Sleep -Milliseconds 250 }
}
Write-Output (@{ ready = $false; pid = $proc.Id; log = $log; note = "gateway did not answer /health within 30 s; read the log" } | ConvertTo-Json -Compress)
exit 1
