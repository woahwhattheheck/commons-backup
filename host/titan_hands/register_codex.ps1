[CmdletBinding()]
param(
    [string]$SdkRoot = (Join-Path $env:LOCALAPPDATA 'TitanHands\AndroidSdk'),
    [string]$AndroidUserHome = (Join-Path $env:LOCALAPPDATA 'TitanHands\AndroidHome'),
    [string]$AvdName = 'TitanHands_AOSP_API34'
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = (Get-Command python.exe -ErrorAction Stop).Source
$codex = (Get-Command codex.exe -ErrorAction Stop).Source
$adb = Join-Path $SdkRoot 'platform-tools\adb.exe'
$emulator = Join-Path $SdkRoot 'emulator\emulator.exe'
$avdHome = Join-Path $AndroidUserHome 'avd'
$configPath = Join-Path $env:USERPROFILE '.codex\config.toml'

$existing = & $codex mcp list | Select-String -Pattern '^titan_hands\s'
if ($existing) {
    & $codex mcp remove titan_hands | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "codex mcp remove failed with exit code $LASTEXITCODE" }
}

$arguments = @(
    'mcp','add','titan_hands',
    '--env',("PYTHONPATH=" + $repoRoot),
    '--env','PYTHONUTF8=1',
    '--env','TITAN_HANDS_DEFAULT_TARGET=windows',
    # The laptop is a terminal, not an emulator host. Android remains reachable
    # when an operator explicitly starts or selects a target, but MCP calls may
    # never allocate the 1.5 GB emulator as a side effect.
    '--env','TITAN_HANDS_ANDROID_AUTOSTART=0',
    '--env','TITAN_HANDS_ANDROID_BACKEND=auto',
    '--env',("TITAN_HANDS_ANDROID_AVD=" + $AvdName),
    '--env','TITAN_HANDS_ANDROID_BOOT_TIMEOUT=240',
    '--env',("ANDROID_HOME=" + $SdkRoot),
    '--env',("ANDROID_USER_HOME=" + $AndroidUserHome),
    '--env',("ANDROID_AVD_HOME=" + $avdHome),
    '--env',("TITAN_HANDS_ADB=" + $adb),
    '--env',("TITAN_HANDS_ANDROID_EMULATOR=" + $emulator),
    '--',$python,'-m','host.titan_hands.mcp_one'
)
& $codex @arguments | Out-Host
if ($LASTEXITCODE -ne 0) { throw "codex mcp add failed with exit code $LASTEXITCODE" }

$lines = [System.Collections.Generic.List[string]]::new()
$lines.AddRange([string[]][System.IO.File]::ReadAllLines($configPath))
$header = $lines.IndexOf('[mcp_servers.titan_hands]')
if ($header -lt 0) { throw 'Codex wrote no titan_hands MCP block' }
$envHeader = $lines.IndexOf('[mcp_servers.titan_hands.env]')
if ($envHeader -lt 0 -or $envHeader -le $header) { throw 'Codex wrote no titan_hands MCP environment block' }

$settings = [ordered]@{
    'default_tools_approval_mode' = 'default_tools_approval_mode = "approve"'
    'startup_timeout_sec' = 'startup_timeout_sec = 20'
    'tool_timeout_sec' = 'tool_timeout_sec = 120'
}
foreach ($name in $settings.Keys) {
    $found = $false
    for ($index = $header + 1; $index -lt $envHeader; $index++) {
        if ($lines[$index] -match ('^' + [regex]::Escape($name) + '\s*=')) {
            $lines[$index] = $settings[$name]
            $found = $true
            break
        }
    }
    if (-not $found) {
        $lines.Insert($envHeader, $settings[$name])
        $envHeader++
    }
}

$temporaryConfig = $configPath + '.titan-hands.tmp'
[System.IO.File]::WriteAllLines($temporaryConfig, $lines, [System.Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temporaryConfig -Destination $configPath -Force

& $codex mcp get titan_hands --json
if ($LASTEXITCODE -ne 0) { throw "Codex could not read the registered MCP server" }
