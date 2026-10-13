# Run from the existing Commons checkout/runtime. No clone, model launch, or secret export.
[CmdletBinding()]
param([string]$Python = "python", [int]$Minutes = 15)
$ErrorActionPreference = "Stop"
if ($Minutes -lt 5) { throw "Use at least five minutes." }
$Root = Split-Path -Parent $PSScriptRoot
$PythonPath = (Get-Command $Python -ErrorAction Stop).Source
$Worker = Join-Path $PSScriptRoot "inbox_slack_relay.py"
$Config = Join-Path $PSScriptRoot "inbox_visibility.json"
$State = Join-Path $env:LOCALAPPDATA "Commons\InboxVisibility\state.sqlite3"
# A finite foreground run returns a live/degraded receipt before installation.
$RawReceipt = & $PythonPath $Worker --config $Config --state $State
$Receipt = $RawReceipt | ConvertFrom-Json
$RawReceipt | Write-Output
if ($Receipt.status -notin @("LIVE", "DEGRADED")) { throw "Initial Slack transport is blocked; no task installed. Resolve the displayed fixed-code blocker." }
# DEGRADED installs the health/working-source job without claiming all sources work.
# Unclassified/private counts also remain visible instead of preventing useful delivery.
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$Worker`" --config `"$Config`" --state `"$State`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes($Minutes) -RepetitionInterval (New-TimeSpan -Minutes $Minutes)
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 12) -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "Commons Inbox Visibility" -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Read-only work inboxes to Slack; no model calls or source read/done mutation." -Force | Select-Object TaskName,State
# Uses the current user's existing keyrings. It runs only while that user is logged on.
