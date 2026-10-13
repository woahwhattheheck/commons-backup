$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonCommand = Get-Command python -ErrorAction Stop
$pythonExe = $pythonCommand.Source
$pythonWindowless = Join-Path (Split-Path -Parent $pythonExe) "pythonw.exe"
$runner = $pythonExe
if (Test-Path -LiteralPath $pythonWindowless) {
    $runner = $pythonWindowless
}

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskName = "Commons Cloud PC Bridge"
$action = New-ScheduledTaskAction `
    -Execute $runner `
    -Argument "-B -m host.cloud_pc_bridge --poll-seconds 30" `
    -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal `
    -UserId $identity `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::FromSeconds(0))

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "Installed and started '$taskName' for $identity."
Write-Output "It uses the existing Commons checkout at $repoRoot."
