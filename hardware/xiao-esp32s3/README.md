# XIAO ESP32-S3 摄像头 / Wi-Fi / BLE 验证

实测设备：Seeed XIAO ESP32-S3 Sense，ESP32-S3 revision 0.2，8 MB Flash、8 MB PSRAM。本次串口：`COM3`。

## 验证固件的连接方式

- Wi-Fi 热点：`XIAO-S3-1984`
- Wi-Fi 密码：由本地固件配置提供
- 页面：`http://192.168.4.1/`
- JSON 状态：`http://192.168.4.1/api/status`
- 单张拍照：`http://192.168.4.1/capture.jpg`（刷新重新拍摄）
- BLE 名称：`XIAO-S3-1984`
- BLE Service UUID：`4fafc201-1fb5-459e-8fcc-c5c9c331914b`
- 可读写 Characteristic UUID：`beb5483e-36e1-4688-b7f5-ea07361b26a8`

热点仅供本地测试，不提供互联网。BLE 是低功耗 GATT 通信；可用 nRF Connect 等 BLE 客户端读写。为自己的板卡设置独立的 WPA2 密码。

2026-11-07 已完成烧录及写入哈希校验。实际测试通过：电脑连接热点、主页 HTTP 200、`/api/status` 返回正确设备及一个 Wi-Fi 客户端；BLE 两轮连接、写入、读回和断开后重连。测试后电脑已恢复连接 `SCUNET`。

当前固件已启用摄像头。实测传感器为 **OV5640，PID 0x5640**，已加载自动对焦固件，对焦状态为 `0x10`（已合焦）。启动时以 SXGA 完成对焦初始化，随后切换至 VGA 640×480 JPEG 拍照。

2026-11-07 摄像头最终验证通过：连续三张 USB 传回的 JPEG 完整解码；经热点访问 `/capture.jpg` 返回 HTTP 200 和有效 640×480 JPEG；新增摄像头后 BLE 两轮读写和重连仍通过。Wi-Fi 测试后电脑恢复连接 `SCUNET`。实拍中镜头正对灯光，画面有眩光；本次未验证连续视频、最高分辨率或长期稳定性。

证据：`logs/camera-af-after/verification.json`、同目录三张 JPEG、`logs/wifi-camera-after.json`、`logs/camera-http.jpg`、`logs/ble-camera-af-after.json`。原有出厂程序和无线验证程序均已完整备份，恢复方法见下方。

## 本地工具

- Arduino CLI：`C:\Users\brack\AppData\Local\XIAO-ESP32S3-Tools\cli\arduino-cli.exe`
- Arduino 配置：`C:\Users\brack\AppData\Local\XIAO-ESP32S3-Tools\arduino-cli.yaml`
- Python 工具环境：本项目 `.xiao-env\Scripts\python.exe`，已安装 esptool、Bleak。
- Arduino ESP32 核心已安装版本：`3.3.12`。
- 自动对焦依赖：`OV5640 Auto Focus for ESP32 Camera`，版本 `0.1.1`（Seeed 示例推荐的库）。

编译 `WirelessCheck` 或 `SmartGlassesWiFi` 前，在相应的 sketch 目录新建本地 `ap_secrets.h`：

```cpp
#pragma once
constexpr char AP_PASSWORD[] = "replace-with-your-passphrase";
```

将示例字符串替换为自己的 WPA2 密码（8–63 个字符）。运行 Windows 自动验证脚本前，将同一密码设置为当前 PowerShell 会话的 `XIAO_AP_PASSWORD` 环境变量。

从本目录执行 PowerShell 编译命令：

```powershell
$toolRoot = Join-Path $env:LOCALAPPDATA 'XIAO-ESP32S3-Tools'
& "$toolRoot\cli\arduino-cli.exe" compile --config-file "$toolRoot\arduino-cli.yaml" --fqbn 'esp32:esp32:XIAO_ESP32S3:USBMode=hwcdc,CDCOnBoot=default,PSRAM=opi' --output-dir '.\build-camera' '.\WirelessCheck'
```

上传仅在确认备份完成后执行：

```powershell
& "$toolRoot\cli\arduino-cli.exe" upload --config-file "$toolRoot\arduino-cli.yaml" --fqbn 'esp32:esp32:XIAO_ESP32S3:USBMode=hwcdc,CDCOnBoot=default,PSRAM=opi' --port COM3 --input-dir '.\build-camera' '.\WirelessCheck'
```

在项目根目录运行实际 BLE 读写和重连验证：

```powershell
& '.\.xiao-env\Scripts\python.exe' '.\hardware\xiao-esp32s3\verify_ble.py' '.\hardware\xiao-esp32s3\logs\ble-after.json'
```

在项目根目录验证三张实际照片：

```powershell
& '.\.xiao-env\Scripts\python.exe' '.\hardware\xiao-esp32s3\verify_camera.py' '.\hardware\xiao-esp32s3\logs\camera-test'
```

验证热点传图并自动恢复电脑原 Wi-Fi：

```powershell
& '.\hardware\xiao-esp32s3\verify_wifi.ps1' -Camera
```

## 原固件备份与恢复

- 文件：`backups/original-20261107-<device-mac>.bin`
- 大小：`8388608` 字节（完整 8 MB Flash）
- SHA-256：`9e9d5493e49af973e8cb8025abdd7ad1baa777fda94d297c3f63ca7786fd0579`

备份和测试日志已在 `.gitignore` 排除；不要提交完整 Flash 备份，因为它可能包含原程序保存的配置。

恢复会覆盖验证程序。从项目根目录执行：

```powershell
& '.\.xiao-env\Scripts\python.exe' -m esptool --chip esp32s3 --port COM3 --baud 460800 write-flash 0 '.\hardware\xiao-esp32s3\backups\original-20261107-<device-mac>.bin'
```

仅恢复先前的 Wi-Fi / BLE 测试固件（不启用摄像头）可使用 `backups/wireless-only-20261107.bin`；同为完整 8388608 字节 Flash，SHA-256 为 `fc26861c51c870b213cc19c0d01d0eb5671d9a742fa5f93ddf55e6c25fdd70a7`。

## 官方参考

- [Seeed 快速入门](https://wiki.seeedstudio.com/cn/xiao_esp32s3_getting_started/)
- [Seeed Wi-Fi](https://wiki.seeedstudio.com/cn/xiao_esp32s3_wifi_usage/)
- [Seeed BLE](https://wiki.seeedstudio.com/cn/xiao_esp32s3_bluetooth/)
