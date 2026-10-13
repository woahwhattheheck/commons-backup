param(
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"
# Default is a detached, hidden desktop activation. Use -Foreground only for
# an explicit diagnostic session where a console and exit code are wanted.
$python = (Get-Command python -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path -LiteralPath $pythonw)) {
    $candidate = Get-Command pythonw -ErrorAction SilentlyContinue
    $pythonw = if ($candidate) { $candidate.Source } else { $python }
}
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$handoff = Join-Path $here "handoff.py"

if ($Foreground) {
    & $python $handoff serve --open-browser @args
    exit $LASTEXITCODE
}

$childArgs = @("`"$handoff`"", "serve", "--open-browser") + $args
$process = Start-Process -FilePath $pythonw -ArgumentList $childArgs -WindowStyle Hidden -PassThru
if ($null -eq $process) {
    throw "Grok Slack handoff did not start"
}
exit 0
