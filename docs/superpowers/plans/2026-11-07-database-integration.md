# 人员数据库接入与完整电脑端验证

用户授权按完整项目持续执行，不逐项暂停；有真正影响身份/数据含义的问题及时询问。

## 目标与已核实事实
- 主数据库 `database/smart_glasses.db`；头像 `database/images`。新头像和相应 Users 资料加入后应自动可识别，不要求修改代码或重启。
- 实际 schema：Users(user_id,name,age,gender,introduction,experience)，Face_Embeddings，Profile_Facts(category,field,value,source_title,source_url,source_type,checked_on,note)。
- Users 中有两组重复记录。实际部署时通过本地配置将姓名绑定到既有头像使用的 ID，保留原始记录。
- 原始特征由 buffalo_l 提取，512 维；现有 SFace 128 维。用户已授权选择效果合适的一种。使用固定模型统一从头像重算，禁止混用不同模型的向量。
- 本机端完整软件、动态登记、资料问答、中文语音与基准/模拟器、可迁移发布包纳入本次；真实 Pi 的 perf/功耗/热表现及物理眼镜装配依赖后续硬件，不能伪造。

## 实施与验收
- [ ] 1. 比较 SFace / ArcFace mobile / ArcFace R50 的本机成本与头像一致性，记录公开评测和本地测试边界，固定唯一运行模型。
- [ ] 2. 只读 PeopleDatabase 适配真实 schema，带来源的确定性资料检索；未记录字段不猜测。支持显式姓名查询和摄像头指代查询。
- [ ] 3. 自动头像同步：启动同步、后台约2秒增量扫描、手动同步；支持文件名为唯一姓名或 user_id，以及 user_id 子目录多头像。完整校验后原子更新自有特征缓存，错误图片和重名歧义明确报告；删除资料/头像不继续保留过期识别。
- [ ] 4. 集成接口和控制台，预缓存新增用户常见短答，资料修改即时生效，重启和新用户无须改代码。
- [ ] 5. 单元/集成/真实模型测试：既有两人、变换图片、未知拒识、临时新增第三用户、修改/移除/损坏头像、只读主库摘要不变、语音到资料回答链路。
- [ ] 6. 补全本机 A/B/C 数据采集与顺序管线模拟器；区分不支持的私人身份基线，禁将 VLM 猜身份算作正确。
- [ ] 7. Windows 与 ARM64 独立环境构建、相对路径、离线发布包与自检；更新使用文档和本次结果报告，最终服务可用且设备关闭。

## 决策与进度
- 不运行队友 `database/database.py` 主入口：它会调用 cleanup_old_data；仅只读 SQL 接入，保留资料库和原 embedding 文件。
- profiles.json 有 53 项，但它不是 SQLite 当前登记集；不自动把未登记 JSON 人员导入数据库。自动识别以 Users 与 images 的明确对应为准。
- 模型已选 ArcFace MobileFaceNet（512维，约13MiB，本机2线程embedding中位数6.1ms），R50约125ms/166MiB；公开评测承认重模型的准确率优势，但Pi与一秒预算优先轻量路径。所有新头像统一重提，不复用现有R50向量。
- 用户异步确认“本次一并接通XIAO”。新增原生USB采集，SGA1 v1，24字节头+CRC32，JPEG3FPS、16kHz mono s16le PCM；保留原WirelessCheck源文件，使用独立SmartGlassesCapture草图。
- COM3实测ESP32-S3 rev0.2、USB 303a:1001、序列<device-mac>，OV5640 AF沿用已有验证实现。已两次完整读回8MiB Flash，一致SHA256 5abff0909e2170764a719a09b0d6f961146f08d0f10077eb0b3de4f4b2bccfb9，备份在hardware/xiao-esp32s3/backups/pre-smart-glasses-20261107-{full,verify}.bin。
- 当前源数据库初始SHA256 555c340a09eaa5eb3f97a734659a85baf25e1bb8f66630d243bf836dcbd7a24a，后续最终核验不变。
- 人员接入/动态新增删除损坏、真实模型等34项测试已完整通过；后续USB解析器3项通过。完整架构基准210个trial（含显式unsupported）已保存logs/architecture-benchmark.json；管线模拟器已保存logs/pipeline-simulation.json。基准仅预解码图像到首块音频准备好，不是完整语音起音/真人准确率/Pi测量。
- Pi cp313/aarch64离线wheelhouse已下载runtime/pi-wheelhouse；官方b12110 ARM64包已SHA校验并展开runtime/pi-llama（未执行）。尚待构建完整发布包、设备实测、最终审查修复与报告。
