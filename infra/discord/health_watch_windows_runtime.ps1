[CmdletBinding()]
param(
    [int]$TimeoutSec = 10,
    [int]$RetryCount = 3,
    [int]$RetryDelaySec = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$bridgeTask = "Commons Discord Live Bridge v1"
$healthUri = "http://127.0.0.1:18787/health"
$runtimeLog = Join-Path $env:LOCALAPPDATA "Commons\discord-runtime.log"
$schtasks = (Get-Command schtasks.exe -ErrorAction Stop).Source
$curl = (Get-Command curl.exe -ErrorAction Stop).Source

function Write-HealthLog([string]$Message) {
    try {
        $parent = Split-Path $runtimeLog -Parent
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Add-Content -LiteralPath $runtimeLog -Value ("{0} {1}" -f `
            [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds(), $Message)
    } catch {
        # Recovery does not depend on its diagnostic receipt.
    }
}

$healthy = $false
for ($attempt = 1; $attempt -le $RetryCount; $attempt++) {
    try {
        $raw = & $curl --silent --fail --max-time $TimeoutSec $healthUri 2>$null
        $body = $raw | ConvertFrom-Json
        if ($LASTEXITCODE -eq 0 -and $body.ok -and $body.node -eq "discord") {
            $healthy = $true
            break
        }
    } catch {
        # Bounded retry through journal-open and server startup grace.
    }
    if ($attempt -lt $RetryCount) {
        Start-Sleep -Seconds $RetryDelaySec
    }
}

if ($healthy) {
    Write-HealthLog "health-ok"
} else {
    Write-HealthLog "health-restart"
    & $schtasks /End /TN $bridgeTask *> $null
    Start-Sleep -Seconds 2
    & $schtasks /Run /TN $bridgeTask *> $null
}
