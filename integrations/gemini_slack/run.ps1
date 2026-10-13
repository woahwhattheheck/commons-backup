$ErrorActionPreference = "Stop"

if (-not $env:SLACK_BOT_TOKEN -or -not $env:SLACK_APP_TOKEN) {
    throw "Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in this process before starting the bridge."
}

$python = (Get-Command python -ErrorAction Stop).Source
& $python "$PSScriptRoot\bridge.py" serve @args
exit $LASTEXITCODE
