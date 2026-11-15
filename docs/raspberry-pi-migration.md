# Raspberry Pi 5 8GB 离线迁移

目标为64位 Linux ARM64、CPython3.13、主动散热和稳定供电，连接已刷采集固件的XIAO，并配置USB耳机/声卡。当前没有真实Pi测量；Windows结果不可换算为Pi性能。

## 离线包

exports/smart-glasses-pi5-offline-20261107.tar.gz 包含源码、当前SQLite快照/头像、选定模型、短答音频、官方b12110 ARM64 llama.cpp、Linux ARM64 / Python3.13 wheels和XIAO固件。不含Windows虚拟环境或原Flash备份。包内含人员资料，仅在自己的设备间使用。

## 安装

先在Pi准备系统库（安装阶段可联网）：

```bash
sudo apt install python3-venv libportaudio2 libsndfile1 libgl1 libglib2.0-0 libgomp1
```

复制包到自己的目录后：

```bash
tar -xzf smart-glasses-pi5-offline-20261107.tar.gz
cd smart-glasses
bash scripts/install_pi.sh
.ai-env/bin/python scripts/check_install.py --all-files
.ai-env/bin/python scripts/run.py start
```

安装器要求ARM64和Python3.13，从wheelhouse以--no-index安装，不自动切换模型或联网。其他Python版本需要重新准备匹配wheels；不复制Windows的.ai-env。以后修改资料/配置后，--all-files会报告这些变化；普通check_install.py核验模型/运行时/wheels并检查当前数据库。

USB串口权限不足时，请将运行账号加入dialout组并重新登录；不需以root运行整套AI。声卡按sounddevice.query_devices()结果配置audio_output_device。XIAO按实际USB标识、序列号和固件MAC选择，断线明确报错，不改用其他传感器。

控制台绑定Pi本机127.0.0.1:8765，可在Pi浏览器访问。若从电脑访问，可使用SSH本地转发：

```bash
ssh -L 8765:127.0.0.1:8765 <user>@<pi-address>
```

停止服务：

```bash
.ai-env/bin/python scripts/run.py stop
```

## 数据与采集

更新SQLite Users并放入database/images即可后台自动登记。派生512维特征在Pi从头像重建；多张头像按user_id聚合。编号目录避免重名/改名歧义，具体见database-interface.md。

默认sensor_source=xiao_usb，通过单根USB传JPEG和PCM，无需Wi-Fi凭据或互联网。local模式显式使用计算端摄像头/音频。当前SGA1协议和固件见usb-capture.md；不将MJPEG当作音频通道。

## Pi评测

```bash
.ai-env/bin/python scripts/benchmark_architectures.py --runs 10
.ai-env/bin/python scripts/simulate_pipeline.py logs/architecture-benchmark.json
.ai-env/bin/python scripts/pi_telemetry.py --seconds 60 --perf
```

perf需匹配内核并具备权限。采集cycles/instructions/cache references/misses、内存、温度和降频；功耗与每次查询能量需要外部功率计，模拟器不会用CPU TDP制造数据。

严格一秒目标需测用户说完至声学起音，报告最大值、P95、超时率和准确率。软件音频提交/设备延迟只是估计。热稳定、不同角度人物、噪声和穿戴电池续航仍需真实Pi/眼镜验证。
