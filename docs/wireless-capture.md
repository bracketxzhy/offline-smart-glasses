# XIAO wireless image/audio capture

The sensing board is the project's verified XIAO ESP32-S3 Sense with OV5640, not STM32. The wireless firmware creates the local development AP **XIAO-S3-1984** and needs no computer USB/serial monitor to boot. Set the AP passphrase for your build using the [firmware instructions](../hardware/xiao-esp32s3/README.md).

Device status: `http://192.168.4.1/api/status`. SGA1 JPEG/PCM stream: TCP `192.168.4.1:3333`. Current capture settings are VGA JPEG at a target 3 FPS and mono 16-kHz signed 16-bit PCM. A single TCP client owns the stream. Complete packets are serialized; an incomplete TCP write closes the session. Camera/microphone controls are independent. The CPU models and audio output stay on the host.

## Normal use

Both November 8 phases passed: while computer USB supplied power, 25.156 seconds produced 75 VGA frames and 401,600 PCM samples; after the independent-supply handoff, with the computer USB device absent, 25.156 seconds produced 75 VGA frames and 403,200 PCM samples. Both had zero rejected packets and a successful app object query through `xiao_wifi`. SCUNET was restored after each test. This verifies short-duration independent sensing-unit operation, not battery endurance or Pi operation.

1. Power the sensing board through its USB-C port. A computer data connection is unnecessary for wireless capture.
2. Connect the computing host to `XIAO-S3-1984`. This AP provides local communication, not Internet service.
3. Set `sensor_source` to `xiao_wifi` and `xiao_wifi.expected_mac` to the board MAC in `config.app.json`. Run `Start-Glasses.ps1` and open `http://127.0.0.1:8765`.
4. Start capture, then use text queries or voice controls. Stop capture before disconnecting the host from the AP. Wi-Fi errors remain visible; the application does not silently select computer sensors or USB input.

The computer currently has one WLAN adapter, so joining the board AP temporarily replaces SCUNET. The offline assistant remains local. Codex online communication can resume after reconnecting SCUNET.

## Reversible validation

Set `XIAO_AP_PASSWORD` in the current PowerShell session to the board hotspot passphrase. From the normal WLAN connection, while the board is still USB-powered:

```powershell
.\scripts\Test-WirelessCapture.ps1 -PowerPhase usb_connected -Seconds 25 -AppCheck
```

After the user removes the computer USB connection and switches to independent power:

```powershell
.\scripts\Test-WirelessCapture.ps1 -PowerPhase external -Seconds 25 -AppCheck
```

The script temporarily associates with the AP, validates identity/readiness, receives JPEG and PCM, checks independent stream shutdown, optionally performs an actual app object query, and restores the original WLAN. An independent hidden watchdog also restores it if the test process is interrupted. Numeric evidence goes to `logs/validation/wifi-stream-<phase>.json`; no images or audio recordings are retained. External phase explicitly rejects a board still enumerated through the computer's USB port. It records that the user reported independent power; it does not measure battery runtime, power draw, speech correctness, acoustic onset, or Pi performance.

## Firmware and rollback

Wireless sketch: `hardware/xiao-esp32s3/SmartGlassesWiFi/`. Original USB acquisition sketch remains in `SmartGlassesCapture/`. Before flashing, two complete 8,388,608-byte copies of the previous Flash were compared and matched; the hash and backup paths are in `hardware/xiao-esp32s3/backups/pre-wireless-stream-20261108.json`. Backups remain local and are excluded from release packages.

Rollback is explicit: stop capture and use esptool to restore `backups/pre-wireless-stream-20261108.bin` at address 0, then select `sensor_source="xiao_usb"`. No eFuse or boot-security settings are changed. The previous report's USB measurements remain historical; they must not be relabelled as wireless results.
