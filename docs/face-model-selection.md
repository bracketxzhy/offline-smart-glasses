# 固定512维ArcFace MobileFaceNet

选择依据是识别能力、计算和内存，不是维数本身。不同模型的512维特征也不能混用。

| 候选 | 模型MiB | 本机2线程特征中位数ms | 变换头像最小相似度 |
|---|---:|---:|---:|
| SFace 128D | 36.90 | 10.00 | 0.9407 |
| ArcFace R50 512D | 166.31 | 124.81 | 0.9383 |
| ArcFace MobileFaceNet 512D | 12.99 | 6.11 | 0.9557 |

本地仅两张登记头像的亮度、模糊和降分辨率变换，加一个公开未知头像。这不是独立真人准确率数据集，不能用这些相似度断言一般识别效果更好。

InsightFace官方部分复杂基准中R50更准；本机计算/内存开销也更高。结合Pi5 CPU与简单问题一秒预算，选用轻量MobileFaceNet。实际不同角度/光照的人脸仍需校准，当前cosine0.50、身份间margin0.08不代表人群统计阈值。

模型为官方buffalo_sc中的w600k_mbf.onnx，SHA256：`9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f`。官方包摘要：`57d31b56b6ffa911c8a73cfc1707c73cab76efe7f13b675a05223bf42de47c72`。

按InsightFace非商业研究条款用于课程项目。统一从头像重新计算，不复用database/embeddings的R50特征。原始本机结果见logs/face-model-comparison.json。

来源：[InsightFace官方模型/评测](https://github.com/deepinsight/insightface/blob/master/python-package/docs/model_zoo.md)、[官方模型包](https://github.com/deepinsight/insightface/releases/tag/model-zoo)、[OpenCV SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface)。
