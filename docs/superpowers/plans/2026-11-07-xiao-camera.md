# XIAO ESP32-S3 Camera Verification

Goal: Confirm the attached Sense camera can initialize and produce usable JPEG images, keeping the existing Wi-Fi hotspot and BLE service available.

Use the installed official esp32-camera driver and its XIAO ESP32-S3 pin map. Capture VGA JPEG frames with OPI PSRAM, record sensor PID/model and errors, and expose a single-photo HTTP endpoint. Keep factory and wireless-only firmware backups. Do not add continuous streaming or cloud uploads.

- [x] Confirm COM3 and back up wireless-only firmware and source.
- [x] Run `verify_camera.py` against the current firmware; expect camera-not-initialized failure.
- [x] Extend `WirelessCheck.ino` with camera initialization, status, serial JPEG capture and `/capture.jpg`.
- [x] Compile and upload, then decode three actual captured JPEGs and inspect one image.
- [x] Recheck BLE and HTTP camera transfer; restore the computer's original Wi-Fi network.
- [x] Update README with actual sensor, test coverage and photo access instructions.

Actual sensor: OV5640, PID 0x5640. Initial and adjusted three-frame VGA JPEG decoding passed; adjusted image visually contains a recognizable scene. Autofocus initialization was absent; add the Seeed-recommended OV5640 Auto Focus for ESP32 Camera 0.1.1 library, initialize at SXGA, then restore VGA for capture. Test the final firmware again before completion.

Final result: OV5640 AF initialized and focused (status 0x10); three 640x480 JPEGs decoded; HTTP camera image decoded; BLE two rounds passed; computer Wi-Fi restored. No continuous-video or long-duration qualification was performed.
