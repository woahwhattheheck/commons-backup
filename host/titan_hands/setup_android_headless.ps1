[CmdletBinding()]
param(
    [string]$SdkRoot = (Join-Path $env:LOCALAPPDATA 'TitanHands\AndroidSdk'),
    [string]$AndroidUserHome = (Join-Path $env:LOCALAPPDATA 'TitanHands\AndroidHome'),
    [string]$AvdName = 'TitanHands_AOSP_API34',
    [switch]$AcceptSdkLicenses
)

$ErrorActionPreference = 'Stop'
$toolsUrl = 'https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip'
$toolsSha256 = '90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a'
$image = 'system-images;android-34;default;x86_64'
$java = Get-Command java.exe -ErrorAction Stop
$curl = Get-Command curl.exe -ErrorAction Stop
$tar = Get-Command tar.exe -ErrorAction Stop

if (-not $AcceptSdkLicenses) {
    throw 'Android SDK packages require license acceptance. Re-run with -AcceptSdkLicenses after accepting the Android SDK License Agreement.'
}

$resolvedSdkRoot = [System.IO.Path]::GetFullPath($SdkRoot)
$resolvedAndroidHome = [System.IO.Path]::GetFullPath($AndroidUserHome)
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("titan-hands-android-" + [guid]::NewGuid().ToString('N'))
$archive = Join-Path $tempRoot 'commandline-tools.zip'
$expanded = Join-Path $tempRoot 'expanded'
$latest = Join-Path $resolvedSdkRoot 'cmdline-tools\latest'

New-Item -ItemType Directory -Path $tempRoot,$expanded,$resolvedSdkRoot,$resolvedAndroidHome -Force | Out-Null
try {
    if (-not (Test-Path -LiteralPath (Join-Path $latest 'bin\sdkmanager.bat'))) {
        & $curl.Source --fail --location --silent --show-error --output $archive $toolsUrl
        if ($LASTEXITCODE -ne 0) { throw "Android command-line tools download failed with exit code $LASTEXITCODE" }
        $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
        if ($actualHash -ne $toolsSha256) {
            throw "Android command-line tools checksum mismatch: $actualHash"
        }
        & $tar.Source -xf $archive -C $expanded
        if ($LASTEXITCODE -ne 0) { throw "Android command-line tools extraction failed with exit code $LASTEXITCODE" }
        New-Item -ItemType Directory -Path (Split-Path -Parent $latest) -Force | Out-Null
        if (Test-Path -LiteralPath $latest) {
            Remove-Item -LiteralPath $latest -Recurse -Force
        }
        Move-Item -LiteralPath (Join-Path $expanded 'cmdline-tools') -Destination $latest
    }

    $env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $java.Source)
    $env:ANDROID_HOME = $resolvedSdkRoot
    $env:ANDROID_USER_HOME = $resolvedAndroidHome
    $sdkManager = Join-Path $latest 'bin\sdkmanager.bat'
    $avdManager = Join-Path $latest 'bin\avdmanager.bat'

    $yesFile = Join-Path $tempRoot 'accept-sdk-licenses.txt'
    1..200 | ForEach-Object { 'y' } | Set-Content -LiteralPath $yesFile -Encoding Ascii
    $licenseCommand = '"' + $sdkManager + '" --sdk_root="' + $resolvedSdkRoot + '" --licenses < "' + $yesFile + '"'
    & $env:ComSpec /d /c $licenseCommand | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Android SDK license acceptance failed with exit code $LASTEXITCODE" }
    & $sdkManager --sdk_root=$resolvedSdkRoot 'platform-tools' 'emulator' 'platforms;android-34' $image | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "sdkmanager package install failed with exit code $LASTEXITCODE" }
    $imageDirectory = Join-Path $resolvedSdkRoot 'system-images\android-34\default\x86_64'
    if (-not (Test-Path -LiteralPath $imageDirectory)) { throw "Android system image was not installed: $imageDirectory" }

    $avdDirectory = Join-Path $resolvedAndroidHome ("avd\" + $AvdName + '.avd')
    if (-not (Test-Path -LiteralPath $avdDirectory)) {
        'no' | & $avdManager create avd --force --name $AvdName --package $image --device 'pixel_2' | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "avdmanager failed with exit code $LASTEXITCODE" }
    }

    [Environment]::SetEnvironmentVariable('ANDROID_HOME', $resolvedSdkRoot, 'User')
    [Environment]::SetEnvironmentVariable('ANDROID_USER_HOME', $resolvedAndroidHome, 'User')
    [Environment]::SetEnvironmentVariable('ANDROID_AVD_HOME', (Join-Path $resolvedAndroidHome 'avd'), 'User')
    [Environment]::SetEnvironmentVariable('TITAN_HANDS_ADB', (Join-Path $resolvedSdkRoot 'platform-tools\adb.exe'), 'User')
    [Environment]::SetEnvironmentVariable('TITAN_HANDS_ANDROID_EMULATOR', (Join-Path $resolvedSdkRoot 'emulator\emulator.exe'), 'User')
    [Environment]::SetEnvironmentVariable('TITAN_HANDS_ANDROID_AVD', $AvdName, 'User')

    [pscustomobject]@{
        ok = $true
        sdk_root = $resolvedSdkRoot
        android_user_home = $resolvedAndroidHome
        android_avd_home = Join-Path $resolvedAndroidHome 'avd'
        avd = $AvdName
        adb = Join-Path $resolvedSdkRoot 'platform-tools\adb.exe'
        emulator = Join-Path $resolvedSdkRoot 'emulator\emulator.exe'
    } | ConvertTo-Json -Compress
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
