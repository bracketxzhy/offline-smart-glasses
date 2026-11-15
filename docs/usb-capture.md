# XIAO 原生USB图像与音频

设备：ESP32-S3 rev0.2，8MiB Flash/PSRAM，USB 303a:1001，OV5640摄像头。

源码：`hardware/xiao-esp32s3/SmartGlassesCapture/`。Arduino ESP32核心3.3.12，FQBN为 `esp32:esp32:XIAO_ESP32S3:USBMode=hwcdc,CDCOnBoot=default,PSRAM=opi`，依赖OV5640 Auto Focus for ESP32 Camera 0.1.1。

摄像头先以SXGA初始化自动对焦，再切至640×480 JPEG，目标3FPS。PDM CLK GPIO42、DATA GPIO41；音频16kHz mono s16le，每100ms一包。原生USB承载两路采集，计算端执行AI和声音输出。关闭输入停止传输，不表示硬件物理断电。

## SGA1 v1

小端24字节头，Python格式 `<4sBBHIIII`：magic SGA1、version1、kind、头长24、sequence、deviceMillis、payloadBytes、payload CRC32。

kind1 JPEG、kind2 PCM、kind3 UTF-8 JSON状态。CRC32为zlib标准多项式。接收器限制512KiB，拒绝损坏包并重同步。握手必须匹配MAC、协议和音频格式。

控制命令为换行结束的ASCII：START、STOP、CAM_ON、CAM_OFF、MIC_ON、MIC_OFF、STATUS。没有活跃采集时关闭串口。断线停止语音循环并报错，重新接入后显式重新开启，不切换传感器。

## 备份与固件

烧录前两次完整读取8MiB，摘要一致：`5abff0909e2170764a719a09b0d6f961146f08d0f10077eb0b3de4f4b2bccfb9`。

备份在 `hardware/xiao-esp32s3/backups/pre-smart-glasses-20261107-full.bin` 与verify副本。新采集程序通过编译、上传及写入哈希校验；原WirelessCheck源码、出厂和无线固件备份保留。Flash备份不进入发布包。

需回滚时，先关闭采集并释放COM3，再用.xiao-env中的esptool将pre-smart-glasses完整备份写回地址0；回滚是显式操作。程序不会自动刷写或修改eFuse。

## 稳定性测试

运行 `scripts/verify_xiao_stream.py --seconds 1800`。测试独占串口，图像和音频临时处理后丢弃，仅保存速率、CRC和状态等数字指标。开始前关闭控制台采集。

官方引脚与麦克风依据：[Seeed引脚说明](https://wiki.seeedstudio.com/xiao_esp32s3_pin_multiplexing/)、[Seeed麦克风说明](https://wiki.seeedstudio.com/xiao_esp32s3_sense_mic/)。
