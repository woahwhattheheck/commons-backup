[CmdletBinding()]
param(
    [string]$SdkRoot = (Join-Path $env:LOCALAPPDATA 'TitanHands\AndroidSdk'),
    [string]$Gradle = 'C:\Gradle\gradle-8.9\bin\gradle.bat',
    [string]$Serial = 'emulator-5554',
    [switch]$AllowPhysicalDevice,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$adb = Join-Path $SdkRoot 'platform-tools\adb.exe'
$ldaRoot = Join-Path $repoRoot 'lda'
$apk = Join-Path $ldaRoot 'app\build\outputs\apk\debug\app-debug.apk'
$debugKey = Join-Path $ldaRoot 'app\debug.keystore'
$packageName = 'com.local.deviceagent'
$service = "$packageName/com.local.deviceagent.ActionAccessibilityService"

if (-not (Test-Path -LiteralPath $adb)) { throw "adb not found: $adb" }
if (-not (Test-Path -LiteralPath $Gradle)) { throw "Gradle not found: $Gradle" }
if (-not $Serial.StartsWith('emulator-') -and -not $AllowPhysicalDevice) {
    throw 'Refusing a physical handset without -AllowPhysicalDevice and an explicit -Serial.'
}

$java = (Get-Command java.exe -ErrorAction Stop).Source
$env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $java)
$env:ANDROID_HOME = $SdkRoot
$env:ANDROID_SDK_ROOT = $SdkRoot

# The source build references a stable per-host debug key. Some Commons exports intentionally omit
# binary keystores, so create the standard Android debug identity locally when it is absent.
if (-not (Test-Path -LiteralPath $debugKey)) {
    $keytool = Join-Path $env:JAVA_HOME 'bin\keytool.exe'
    & $keytool -genkeypair -v -keystore $debugKey -storepass android -alias androiddebugkey `
        -keypass android -dname 'CN=Android Debug,O=Android,C=US' -keyalg RSA -keysize 2048 `
        -validity 10000 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Android debug keystore' }
}

if ($SkipBuild) {
    if (-not (Test-Path -LiteralPath $apk)) { throw "Cannot skip build; APK not found: $apk" }
} else {
    Push-Location $ldaRoot
    try {
        # The in-process compiler and bounded worker count keep the large imported LDA tree reliable
        # on the same laptop that hosts the headless emulator.
        & $Gradle ':app:assembleDebug' '--no-daemon' '--max-workers=2' `
            '-Pkotlin.compiler.execution.strategy=in-process' '-PtitanHandsAbi=x86_64'
        if ($LASTEXITCODE -ne 0) { throw "LDA Gradle build failed with exit code $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
}

& $adb -s $Serial install -r $apk | Out-Host
if ($LASTEXITCODE -ne 0) { throw "LDA APK install failed with exit code $LASTEXITCODE" }

# This application deliberately contains the owner's full Kotlin agent implementation. On a constrained
# emulator, first-run bytecode verification can exceed Android's fixed service-attach deadline even though
# the package is healthy. Compile the installed package once before asking AccessibilityManager to bind it.
$compileResult = @(& $adb -s $Serial shell cmd package compile -m speed -f $packageName)
if ($LASTEXITCODE -ne 0 -or ($compileResult -join ' ') -notmatch '(?i)\bSuccess\b') {
    throw "LDA package precompile failed: $($compileResult -join ' ')"
}

$enabled = (& $adb -s $Serial shell settings get secure enabled_accessibility_services).Trim()
$parts = @($enabled.Split(':') | Where-Object { $_ -and $_ -ne 'null' })
# A package update stops the app but can leave the service name in secure settings. Writing the
# identical list does not make Android rebind it, so cycle only this service while preserving every
# other accessibility service on the target.
if ($service -in $parts) {
    $others = @($parts | Where-Object { $_ -ne $service })
    if ($others.Count -gt 0) {
        & $adb -s $Serial shell settings put secure enabled_accessibility_services ($others -join ':')
    } else {
        & $adb -s $Serial shell settings delete secure enabled_accessibility_services | Out-Null
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not cycle the existing LDA accessibility service' }
    Start-Sleep -Milliseconds 500
    $parts = $others
}
$parts += $service
& $adb -s $Serial shell settings put secure enabled_accessibility_services ($parts -join ':')
if ($LASTEXITCODE -ne 0) { throw 'Could not enable the LDA accessibility service' }
& $adb -s $Serial shell settings put secure accessibility_enabled 1
if ($LASTEXITCODE -ne 0) { throw 'Could not enable Android accessibility' }

function Get-TitanCapabilities {
    $raw = & $adb -s $Serial shell am broadcast -W -a com.local.deviceagent.TITAN_HANDS `
        -n com.local.deviceagent/.TitanHandsReceiver --es op capabilities
    if ($LASTEXITCODE -ne 0) { return $null }
    $match = [regex]::Match(($raw -join "`n"), 'data="?([A-Za-z0-9+/=]+)"?')
    if (-not $match.Success) { return $null }
    try {
        $json = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($match.Groups[1].Value))
        return $json | ConvertFrom-Json
    } catch {
        return $null
    }
}

# Android may acknowledge the secure-settings write before binding the accessibility service. A
# receiver process alone is not a live proof: wait until the Kotlin service instance itself exists.
$capabilities = $null
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    $capabilities = Get-TitanCapabilities
    if ($capabilities.ok -and $capabilities.accessibility_ready) { break }
    Start-Sleep -Milliseconds 500
}
if (-not $capabilities -or -not $capabilities.ok -or -not $capabilities.accessibility_ready) {
    throw 'LDA installed, but its accessibility service did not become ready for TITAN Hands'
}
$capabilities | ConvertTo-Json -Depth 8 | Out-Host

[ordered]@{
    ok = $true
    serial = $Serial
    apk = $apk
    accessibility_service = $service
    implementation = 'lda-kotlin'
} | ConvertTo-Json
