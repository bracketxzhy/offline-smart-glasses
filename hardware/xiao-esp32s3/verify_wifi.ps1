param([string]$InterfaceName = 'WLAN', [switch]$Camera)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrEmpty($env:XIAO_AP_PASSWORD)) {
    throw 'Set XIAO_AP_PASSWORD to the board hotspot passphrase before running this test.'
}
$wifiKey = [System.Security.SecurityElement]::Escape($env:XIAO_AP_PASSWORD)
$deviceName = 'XIAO-S3-1984'
$resultPath = Join-Path $PSScriptRoot 'logs\wifi-after.json'
if ($Camera) { $resultPath = Join-Path $PSScriptRoot 'logs\wifi-camera-after.json' }
$profilePath = Join-Path $PSScriptRoot 'logs\test-wifi-profile.xml'
$null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $profilePath)
$interfaceState = (& netsh wlan show interfaces) -join "`n"
$profileMatch = [regex]::Match($interfaceState, '(?m)^\s*Profile\s*:\s*(.+?)\s*$')
if (-not $profileMatch.Success) {
    throw 'Cannot identify the active Wi-Fi profile; no connection changes were made.'
}
$originalProfile = $profileMatch.Groups[1].Value.Trim()
if ($originalProfile -eq $deviceName) {
    throw 'Already on the test network; connect to the normal network before this test.'
}

$profileXml = @'
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>XIAO-S3-1984</name>
  <SSIDConfig><SSID><name>XIAO-S3-1984</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>manual</connectionMode>
  <MSM><security>
    <authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption>
    <sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>__XIAO_AP_PASSWORD__</keyMaterial></sharedKey>
  </security></MSM>
</WLANProfile>
'@
Set-Content -LiteralPath $profilePath -Value $profileXml.Replace('__XIAO_AP_PASSWORD__', $wifiKey) -Encoding utf8
& netsh wlan add profile "filename=$profilePath" "interface=$InterfaceName" user=current
if ($LASTEXITCODE -ne 0) { throw 'Failed to add the development board Wi-Fi profile.' }

# Independent recovery if this test process is interrupted while Wi-Fi is switched.
$quotedProfile = $originalProfile.Replace("'", "''")
$quotedInterface = $InterfaceName.Replace("'", "''")
$recoveryCode = "Start-Sleep -Seconds 45; & netsh wlan connect 'name=$quotedProfile' 'interface=$quotedInterface' | Out-Null"
$encodedRecovery = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($recoveryCode))
$watchdog = Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -PassThru -ArgumentList @('-NoProfile', '-EncodedCommand', $encodedRecovery)
$result = [ordered]@{ passed = $false; original_profile = $originalProfile; restored = $false }
try {
    & netsh wlan connect "name=$deviceName" "interface=$InterfaceName"
    if ($LASTEXITCODE -ne 0) { throw 'Windows rejected connection to the board hotspot.' }
    $deadline = [DateTime]::UtcNow.AddSeconds(25)
    $response = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri 'http://192.168.4.1/api/status' -NoProxy -TimeoutSec 2
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if ($null -eq $response) { throw 'Board HTTP status was not reachable within 25 seconds.' }
    $status = $response.Content | ConvertFrom-Json
    if ($status.device -ne $deviceName -or -not $status.wifi_ready -or -not $status.ble_ready -or $status.wifi_clients -lt 1) {
        throw 'Unexpected board identity or Wi-Fi/BLE readiness status.'
    }
    $root = Invoke-WebRequest -Uri 'http://192.168.4.1/' -NoProxy -TimeoutSec 3
    if ($root.StatusCode -ne 200 -or $root.Content -notmatch 'XIAO ESP32-S3') { throw 'Board home page check failed.' }
    $result.status = $status
    $result.home_page_status = $root.StatusCode
    if ($Camera) {
        if (-not $status.camera_initialized -or $status.camera_error -ne 0) {
            throw 'Camera initialization check failed.'
        }
        $cameraPath = Join-Path $PSScriptRoot 'logs\camera-http.jpg'
        $photo = Invoke-WebRequest -Uri 'http://192.168.4.1/capture.jpg' -NoProxy -TimeoutSec 6 -OutFile $cameraPath -PassThru
        if ($photo.StatusCode -ne 200 -or $photo.Headers['Content-Type'] -notlike 'image/jpeg*') {
            throw 'Camera endpoint did not return a JPEG image.'
        }
        $pythonPath = Join-Path $PSScriptRoot '..\..\.xiao-env\Scripts\python.exe'
        & $pythonPath -c 'from PIL import Image; import sys; image=Image.open(sys.argv[1]); image.load(); assert image.format=="JPEG" and image.size==(640,480); print("HTTP JPEG decoded: 640x480")' $cameraPath
        if ($LASTEXITCODE -ne 0) { throw 'HTTP camera image failed to decode.' }
        $result.camera_photo = $cameraPath
        $result.camera_photo_bytes = (Get-Item -LiteralPath $cameraPath).Length
        $result.camera_photo_decoded = $true
    }
    $result.passed = $true
} catch {
    $result.error = $_.Exception.Message
} finally {
    & netsh wlan connect "name=$originalProfile" "interface=$InterfaceName"
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while ([DateTime]::UtcNow -lt $deadline) {
        $state = (& netsh wlan show interfaces) -join "`n"
        $match = [regex]::Match($state, '(?m)^\s*Profile\s*:\s*(.+?)\s*$')
        if ($match.Success -and $match.Groups[1].Value.Trim() -eq $originalProfile) {
            $result.restored = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if ($result.restored -and -not $watchdog.HasExited) { Stop-Process -Id $watchdog.Id }
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $resultPath -Encoding utf8
}
$result | ConvertTo-Json -Depth 6
if (-not $result.passed -or -not $result.restored) { exit 1 }
