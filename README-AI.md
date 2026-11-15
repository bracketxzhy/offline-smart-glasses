# 离线智能眼镜：电脑测试与树莓派部署

中文链路：XIAO ESP32-S3 Sense → Wi-Fi 图像/音频 → 中文 ASR / 物体检测 / 人脸识别 / 视觉问答 → SQLite 资料 → 中文播报。控制台：http://127.0.0.1:8765 。运行时不调用云服务。无线设置及独立供电验证见 [无线采集](docs/wireless-capture.md)。

## 使用

1. 给已刷无线采集固件的 XIAO 供电，电脑连接热点 `XIAO-S3-1984`；当前无线模式不需要电脑 USB 数据线。
2. 执行 `Start-Glasses.ps1`；服务已运行时直接打开控制台。
3. 启动摄像头，再开启语音，说 **你好助手，前面是什么？**。也可先说唤醒短语，再在8秒内提问。
4. 人物单独面对镜头后可问“这是谁”“他研究什么”“他教什么课”。输入“张三研究什么”等明确姓名时，可直接查库，不需要摄像头。
5. 关闭语音停止音频传输和识别；关闭摄像头停止图像传输。`Stop-Glasses.ps1` 停止后台服务，关闭网页不会停止设备。

XIAO负责采集，电脑扬声器/耳机负责播报；推荐耳机减少反馈。未设置开机自启动。

## 新增登记用户

资料库：`database/smart_glasses.db`；头像：`database/images`。

1. 在 SQLite 的 `Users` 表新增资料，记下 `user_id`。
2. 放入头像，任选一种明确对应方式：唯一姓名 `images/张三.jpg`、编号 `images/9.jpg`、同一人多头像 `images/9/正面.jpg` 和 `images/9/侧面.jpg`。
3. 后台约每2秒扫描，界面显示登记人数和错误，也可点击“立即同步头像”。**无须重启、改代码或手动重提特征。**

单张图片必须恰有一张清晰人脸。照片替换后自动重算；移除照片或数据库人员会移除派生模板；损坏、多脸、资料未创建、重名不明确等情况会显示原因，不沿用失效图片的旧特征。新版控制台使用英文操作标签，保留中文提问与回答；登记细节位于 Enrollment details，立即同步按钮为 Sync portraits。

如有重名，请使用编号文件或目录，或在本地配置中通过 `identity_name_ids` 显式指定绑定。

统一使用 **ArcFace MobileFaceNet 512维**，特征缓存在 `data/identity-cache.sqlite3`。`database/embeddings` 是另一模型的512维向量，不混用；`profiles.json` 的53项也不会自动导入SQLite。

资料字段和来源见 [数据库接口](docs/database-interface.md)。本流程不运行旧 `database/database.py` 的清理主入口。

## 配置与模型

启用 `sensor_source="xiao_wifi"` 后，通过板卡热点的 TCP 3333 端口接收并校验 SGA1 设备身份。原 USB 模式 `xiao_usb` 需要对应 USB 采集固件，不能与无线固件混用。设备不符或断线时明确报错。测试电脑内置摄像头/麦克风时，显式改为 `sensor_source="local"` 并重启；不会自动换采集源。

| 模块 | 模型 |
|---|---|
| 常见物品 | YOLO11n 320px CPU ONNX，80类 |
| 人脸 | YuNet + ArcFace MobileFaceNet，512维 |
| 中文视觉问答 | Qwen3.5-0.8B Q4_K_M + F16 vision projector，llama.cpp b12110 |
| 中文 ASR | sherpa-onnx streaming Zipformer int8，2025-06-30 |
| 中文播报 | VITS zh-ll，常见短答缓存、长答分块 |

人物回答引用登记内容，不让VLM猜年龄、专业、经历或身份。英文采用字母拼读，邮箱读出“艾特/点”等分隔；控制台保留原文和来源。

## 测试与实验

模型测试需要已安装的模型及 `data/fixtures/` 下的测试图像。测试新增用户时，将 `GLASSES_TEST_PORTRAIT` 设置为另一张获授权的单人头像路径。运行架构基准前，参考 `scripts/architecture-cases.example.json` 将本地样本、预期身份和答案填入 `data/fixtures/architecture-cases.json`。

```powershell
$env:GLASSES_MODEL_TESTS='1'
.\.ai-env\Scripts\python.exe -m unittest discover -s tests -v
.\.ai-env\Scripts\python.exe scripts/check_install.py
.\.ai-env\Scripts\python.exe scripts/benchmark_architectures.py --runs 10
.\.ai-env\Scripts\python.exe scripts/simulate_pipeline.py logs/architecture-benchmark.json
```

基准分别报告三种架构的支持范围、测试图片正确数和耗时；不把“不支持”当成零延迟。图像推理到首块音频准备好不含语音终点/声卡/声学起音，不能当作树莓派一秒保证。当前结果见 [集成报告](docs/integration-report-20261107.md)。

## 树莓派

`exports/` 的离线包包含选定模型、当前SQLite/头像、ARM64运行时、Python3.13 wheels；不包含Windows虚拟环境或原始Flash备份。包内含人员资料，按私人项目文件保管。

步骤见 [树莓派迁移](docs/raspberry-pi-migration.md)。真实Pi的性能、功耗、温度与最大响应等待仍需硬件实测。
