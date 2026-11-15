# 本地 AI 部署验证记录

日期：2026-11-07（Asia/Shanghai）。部署位置：`D:\Desktop\Computer organization\project`。

## 已部署

- 隔离 Python 3.12 环境 `.ai-env`，CPU 推理，不依赖本机 Intel GPU。
- YOLO11n 320px ONNX、OpenCV YuNet/SFace、Qwen3.5-0.8B Q4_K_M 与 F16 vision projector。
- sherpa-onnx 中文流式 Zipformer int8（2025-06-30）、VITS zh-ll；85 条常用短答离线音频缓存。
- 中文提问路由、物体短答、人脸显式登记与未知拒识、多人歧义提示、中文 VLM 问答、语音播报、中文唤醒短语门控。
- 本地控制台 http://127.0.0.1:8765 ，模型端口 8081，均只监听 loopback。后台没有开机自启动。
- SQLite 只读适配接口与字段契约；队友资料库尚未提供，当前明确显示未配置，没有伪造个人资料。

当前默认唤醒短语为 **你好助手**。初选 14M ASR 的合成命令漏字较多，实际验证后替换为更完整的中文 int8 模型。“你好眼镜”的转写容易成为同音字，因此不使用它作为默认唤醒短语，也未添加隐藏的同音别名。

## 验证证据

- 最终完整测试：`GLASSES_MODEL_TESTS=1`，**21 项全部通过，无跳过**，包括 4 项真实模型测试。
- 真实物体模型：公开公交车测试图中识别到公交车与人，框坐标落在图像范围内。
- 真实 VLM：根据同一图片用中文回答主要交通工具，识别为公交/巴士类。
- 真实人脸模型：测试图片在空临时库中判为未知；显式登记后原图和缩放图匹配到测试编号。没有将该图片写入真实人脸库。此项不是人脸准确率数据集评估。
- 合成中文音频经 ASR 转写、唤醒短语门控后，正确路由至物体识别。这不能替代用户口音/噪声条件的真实语音准确率测量。
- 电脑摄像头输出 640×480 三通道画面；麦克风可采样，无 overflow；扬声器可打开，设备报告低延迟输出约 91ms。
- 浏览器实际完成启动摄像头、中文识物与播报、开启监听和关闭设备。实时画面识别到“人”，中文短答“前面是人。”已提交给音频设备播放。
- 独立审查发现并修复：混合关键词导致资料误走 VLM、停止慢语音请求不能及时释放麦克风、下载缓存完整性未复核；同时补测电话颜色/机器工作原理等视觉问句的路由。
- 14 个下载资产已按 manifest 复核大小和 SHA-256；导出 ONNX 另有来源与摘要记录。
- 最终重启后：VLM 就绪，摄像头关闭，语音 stopped，无设备错误。服务后台保持可用。

## 本机测量与边界

硬件：Intel Core Ultra 7 155H，约 32GB RAM，Windows；所有 AI 路径使用 CPU。

| 测量 | 结果 | 含义 |
|---|---:|---|
| 10 次物体查询到缓存音频准备好 | 中位数 20.4ms，最大 53.6ms | 预热后的重复图片，不含 ASR、声卡启动和声学起音 |
| 一次实时摄像头识物的文字就绪 | 48.5ms | 实际页面请求 |
| 同次请求到音频提交 | 411.5ms | 含第一次音频模块导入/启动等开销 |
| 同次请求估计起音 | 502.5ms | 音频提交 + 设备报告延迟，非外部录音实测 |
| 最终空闲 Python 工作进程树 RSS | 537.8MiB | 采样值，不是峰值 |
| 最终 VLM 进程树 RSS | 1100.9MiB | 采样值，不是峰值 |

重复图片的 VLM 测量可能复用 image/prompt 缓存，且只有 3 次，不作为独立冷启动或正式架构性能结论。首次单图 VLM smoke test 的首 token 约 1.88s、完整文字约 2.33s，说明复杂视觉路径的延迟应与简单路径分开。

**尚未证明树莓派的完整语音链路能始终在一秒内开始有效回答。** 语音终点的尾静音目标是 320ms，模型块大小、识别计算、调度和声卡也增加等待。应在真实 Pi 上测量说完至声学起音的最大值、P95、超时率，以及准确率。电脑测量不能推导 Pi 达标。

## 后续依赖

1. 登记真实参与者的人脸，使用与队友资料库一致的 person_id；实际人脸阈值需要测试集校准。
2. 队友提供 SQLite 文件和表/列信息后，填写 `config.app.json` 中的只读查询并联调。
3. 迁移真实 Pi 5 8GB，验证 ARM64 软件、设备、内存峰值、温度/降频、perf 和功耗。已核对所选核心 Python 包在 PyPI 有对应 Linux ARM64 wheel，但没有实际在 Pi 安装运行。
4. 本次没有更改 XIAO 的无线验证固件。采集模块支持电脑/UVC 设备和显式 HTTP/MJPEG 图像源；XIAO 摄像头/麦克风传输仍需固件与音频输入适配。当前不声称该链路已接通。
5. proposal 的完整数据集准确率、受控 A/B/C 实验和性能模拟器需要真实 Pi 数据后另行完成；当前控制台只提供三种显式推理模式与阶段日志入口。

## 文件

- 使用：`README-AI.md`、`Start-Glasses.ps1`、`Stop-Glasses.ps1`
- 配置：`config.app.json`
- 接口：`docs/database-interface.md`
- 迁移：`docs/raspberry-pi-migration.md`
- 证据：`logs/validation/full-tests.log`、`logs/validation/final-check.json`、`logs/benchmark-local.json`、`logs/queries.jsonl`
- 模型：`models/manifest.json`、`models/detector/export.json`

## 主要来源

- [Qwen 原始模型](https://huggingface.co/Qwen/Qwen3.5-0.8B)；[Unsloth 固定 GGUF revision](https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/tree/6ab461498e2023f6e3c1baea90a8f0fe38ab64d0)
- [llama.cpp b12110 官方发布](https://github.com/ggml-org/llama.cpp/releases/tag/b12110)
- [中文 Zipformer 固定 revision](https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30/tree/ad658fa0201659a09ea3c176129a191c77ecae8f)；[sherpa 中文 TTS 官方说明](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html)
- [OpenCV Zoo](https://github.com/opencv/opencv_zoo)；[Ultralytics 模型资产](https://github.com/ultralytics/assets/releases/tag/v8.3.0)
