# Wireless Capture Implementation Plan

**Goal:** Prepare and verify wireless image/audio before the user's independent-power handoff.
**Architecture:** Separate AP/TCP firmware, explicit Python Wi-Fi transport using SGA1, shared acquisition adapters, and reversible WLAN verification.
**Tech stack:** Installed Arduino ESP32 3.3.12, XIAO ESP32-S3/OV5640, Python sockets, OpenCV.
**Spec:** ../specs/2026-11-08-xiao-wireless-stream-design.md

- [x] Read current firmware and transport; confirm ESP32-S3 hardware and AP selection.
- [x] Compare two complete Flash backups and retain their SHA-256.
- [x] Write and run failing TCP transport tests (fragmentation, identity, format, EOF, lifecycle).
- [x] Implement transport/adapters; integrate explicit xiao_wifi configuration and pass tests.
- [x] Build separate wireless firmware, serialize writes, enforce single ownership, expose status; flash with verification.
- [x] Associate with AP and test actual wireless media with numeric evidence; automatically restore SCUNET.
- [x] Prepare user-facing connection instructions and notify readiness while USB remains connected.
- [x] After user switches supply, repeat actual wireless test; record this separately.

No USB fallback, automatic network change outside the explicit WLAN test, recorded personal media, eFuse changes, or wireless performance claims before measurement. The current checkout is the user's active project; changes are local and no remote commit/push is requested.

Verification: two 8 MB backups match SHA-256 99d2f66dd9f6cb0b4a5e03096dba17b492a69bc35fe824c38d44a2f00e988876. Firmware compile/upload/hash verification passed. All 47 tests passed with real models enabled. Actual AP capture while USB supplied power: 25.156 s, 75 frames, 401,600 PCM samples, zero bad packets and zero firmware-reported drops. The app explicitly used xiao_wifi for an object query; text ready in 23.18 ms. Independent input shutdown and socket release passed; SCUNET restored. Evidence: logs/validation/wifi-stream-usb_connected.json and wifi-network-usb_connected.json. Independent power remains pending the user's handoff.

External phase completed after the user's supply handoff: matching computer USB device absent; 25.156 s, 75 VGA frames, 403,200 PCM samples, zero bad packets, zero reported firmware drops, app xiao_wifi object query text ready in 16.45 ms. Input shutdown and socket release passed; SCUNET restored. Evidence: logs/validation/wifi-stream-external.json and wifi-network-external.json. No battery-duration, power-meter, live-ASR or acoustic-onset claim follows.
