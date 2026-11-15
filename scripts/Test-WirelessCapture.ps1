param(
    [ValidateSet('usb_connected','external')][string]$PowerPhase = 'usb_connected',
    [int]$Seconds = 25,
    [switch]$AppCheck
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrEmpty($env:XIAO_AP_PASSWORD)) {
    throw 'Set XIAO_AP_PASSWORD to the board hotspot passphrase before running this test.'
}
$wifiKey = [System.Security.SecurityElement]::Escape($env:XIAO_AP_PASSWORD)
if ($Seconds -lt 5 -or $Seconds -gt 60) { throw 'This reversible Wi-Fi test supports 5--60 seconds.' }
$root = Split-Path -Parent $PSScriptRoot
$network = 'XIAO-S3-1984'
$interface = 'WLAN'
$state = (& netsh wlan show interfaces) -join "`n"
$match = [regex]::Match($state, '(?m)^\s*Profile\s*:\s*(.+?)\s*$')
if (-not $match.Success) { throw 'Cannot identify original Wi-Fi profile; no network change made.' }
$original = $match.Groups[1].Value.Trim()
if ($original -eq $network) { throw 'Start the reversible test from SCUNET or the normal network.' }
$profile = Join-Path $root 'logs\validation\wireless-stream-profile.xml'
$null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $profile)
@'
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
<name>XIAO-S3-1984</name><SSIDConfig><SSID><name>XIAO-S3-1984</name></SSID></SSIDConfig>
<connectionType>ESS</connectionType><connectionMode>manual</connectionMode><MSM><security>
<authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption>
<sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>__XIAO_AP_PASSWORD__</keyMaterial></sharedKey>
</security></MSM></WLANProfile>
'@.Replace('__XIAO_AP_PASSWORD__', $wifiKey) | Set-Content -LiteralPath $profile -Encoding utf8
& netsh wlan add profile "filename=$profile" "interface=$interface" user=current | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot install board AP profile.' }
$delay = $Seconds + 65
$recovery = "Start-Sleep -Seconds $delay; & netsh wlan connect 'name=$($original.Replace("'","''"))' 'interface=$interface' | Out-Null"
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($recovery))
$watchdog = Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @('-NoProfile','-EncodedCommand',$encoded)
$result = [ordered]@{ original_profile=$original; restored=$false; passed=$false; power_phase=$PowerPhase }
try {
    & netsh wlan connect "name=$network" "interface=$interface" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Windows rejected the AP connection.' }
    $deadline = [DateTime]::UtcNow.AddSeconds(25)
    $board = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        try { $board=Invoke-RestMethod 'http://192.168.4.1/api/status' -NoProxy -TimeoutSec 2; break }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if ($null -eq $board -or $board.transport -ne 'wifi_tcp') { throw 'Wireless streaming firmware is not reachable.' }
    $output = Join-Path $root "logs\validation\wifi-stream-$PowerPhase.json"
    $arguments = @((Join-Path $PSScriptRoot 'verify_wifi_capture.py'),'--seconds',"$Seconds",'--power-phase',$PowerPhase,'--output',$output)
    if ($AppCheck) { $arguments += '--app-check' }
    & (Join-Path $root '.ai-env\Scripts\python.exe') @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Wireless media verification failed; see numeric evidence.' }
    $result.passed=$true
} catch { $result.error=$_.Exception.Message }
finally {
    & netsh wlan connect "name=$original" "interface=$interface" | Out-Null
    $deadline=[DateTime]::UtcNow.AddSeconds(20)
    while ([DateTime]::UtcNow -lt $deadline) {
        $current=(& netsh wlan show interfaces) -join "`n"
        $active=[regex]::Match($current,'(?m)^\s*Profile\s*:\s*(.+?)\s*$')
        if ($active.Success -and $active.Groups[1].Value.Trim() -eq $original) { $result.restored=$true; break }
        Start-Sleep -Milliseconds 500
    }
    if ($result.restored -and -not $watchdog.HasExited) { Stop-Process -Id $watchdog.Id }
    $result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root "logs\validation\wifi-network-$PowerPhase.json")
}
$result | ConvertTo-Json
if (-not $result.passed -or -not $result.restored) { exit 1 }
