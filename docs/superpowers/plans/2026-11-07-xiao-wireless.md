# XIAO Wireless Implementation Plan

**Goal:** Configure and verify the user's XIAO ESP32-S3 Wi-Fi hotspot and BLE.

**Architecture:** One Arduino sketch using official WiFi, WebServer and BLE libraries. Preserve a complete pre-flash backup and local verification results.

**Spec:** ../specs/2026-11-07-xiao-wireless-design.md

**Tech Stack:** Arduino CLI 1.5.1, esp32:esp32 3.3.12, esptool 5.6.0, Python 3.12, Bleak.

## Constraints

- Target chip must be confirmed as ESP32-S3 with 8 MB Flash.
- Back up Flash before writes; do not modify eFuse.
- AP and BLE name: XIAO-S3-1984. GATT uses Seeed example service and characteristic UUIDs.
- Verification firmware does not initialize the camera; preserve original camera firmware in backup.

## Steps

- [x] Save 8 MB Flash backup, size and SHA-256.
- [x] Add `hardware/xiao-esp32s3/verify_ble.py`; demonstrate failure before the new BLE firmware exists.
- [x] Implement `hardware/xiao-esp32s3/WirelessCheck/WirelessCheck.ino`: AP, HTTP JSON, BLE read/write, restart advertising after disconnect, serial status.
- [x] Compile for `esp32:esp32:XIAO_ESP32S3`, 8 MB Flash, USB CDC enabled, PSRAM enabled; upload with verification.
- [x] Run BLE read/write and reconnection checks; capture serial and HTTP evidence, verify AP by actual association.
- [x] Document connection details, exact test coverage and restore command in local README.

## Review focus

Keep advertising after BLE disconnect. USB output must not block without a serial monitor. Report initialization errors rather than claim readiness. Preserve original Flash and avoid leaking its content. Restore the computer's Wi-Fi connection after any temporary HTTP test.
