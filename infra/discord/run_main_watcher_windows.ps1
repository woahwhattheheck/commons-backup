[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$git = (Get-Command git.exe -ErrorAction Stop).Source
$env:GIT_TERMINAL_PROMPT = "0"

$dirty = & $git -C $repoRoot status --porcelain --untracked-files=no 2>$null
if ($LASTEXITCODE -ne 0 -or $dirty) {
    exit 0
}

& $git -C $repoRoot pull --ff-only --quiet origin main *> $null
exit $LASTEXITCODE
