# XIAO ESP32-S3 无线验证

用户已确认选择开发板创建热点，同时验证 Wi-Fi 和 BLE。USB 实测芯片为 ESP32-S3 revision 0.2，8 MB Flash、8 MB PSRAM，COM3。

使用 Arduino ESP32 官方核心及其 WiFi、WebServer、BLE 库。创建 WPA2 热点 `XIAO-S3-1984`，提供 `/api/status` JSON；BLE 使用同名广播及可读写 GATT 特征，验证写入数据可以读回。热点方案不需要家庭/校园网络凭据；连接现有网络方案未选。

先备份整个 8 MB Flash，并记录 SHA-256，再上传验证程序。备份包含原有摄像头程序，本次验证程序不初始化摄像头。原固件可按记录恢复。不得改动 eFuse、刷写安全配置、读取电脑已有 Wi-Fi 密码。

验收：固件编译通过、上传校验通过；串口报告 AP/BLE 就绪；电脑实际 BLE 连接、读写及断开后重连；Wi-Fi 热点发现和 HTTP 状态访问。未执行的验收必须明确标记。
