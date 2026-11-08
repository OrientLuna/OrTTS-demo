# TTS 缓存修复与同机验证（2026-11-08）

结论：手机 Demo 逐句 create/free 导致 Kokoro 反复支付首次构图开销，是此前 iOS RTF 接近 3 的一个实测原因。两端已改成单个、可逐出的 worker 所有引擎，Rust SDK 增加同样语义的 `TtsCache`；C ABI 不变。它减少重复构图，没有解决 Kokoro 底层所有内存和算子成本。

## iPhone 17 热 RTF

设备为用户的 iPhone 17 标准版 8GB/256GB；CPU arm64-baseline、4 线程。每格新进程/新引擎，先合成一次排除，然后同引擎连测三次，表中为热 RTF 中位数。接口耗时除以实际输出时长，模型 SHA 校验、下载、创建句柄和文件导出不计入 API 耗时；首次 API 内构图计入首次。关闭扬声器播放，回调仍走配置的流式路径，音频导出后检查。未控制散热、供电或随机化顺序，不代表峰值性能或功耗排名。

| 模型 / 本次音色 | 英文短句 | 英文长句 | 中文短句 | 中文长句 |
|---|---:|---:|---:|---:|
| Kokoro 82M Q8 / af_heart、zf_xiaobei | 0.853 | 0.929 | 0.937 | 1.068 |
| PocketTTS English Q8 / alba | 0.326 | 0.380 | | |
| Kitten mini 0.8 / Bella | 0.859 | 0.652 | | |
| Piper Lessac medium / 默认 | 0.119 | 0.152 | | |

空白表示这些固定英语包不支持中文，未强行输入后填速度。ZipVoice 的参考音频/转写尚未接入手机菜单，**未测试**，不能把它记成不支持中文。不同模型输出长度不同：英文短句约 3.2–5.62s，英文长句约 12.32–18.67s；Kokoro 中文短/长约 5.58/19.15s。逐次范围、实际文本、模型 ID 和原始耗时见[结构化结果](../../benchmarks/tts-warm-iphone-20261108.json)。

Kokoro 英文短句本次首次 API RTF 2.373，三次复用 0.834/0.853/0.864；另一次开启正常播放的真机测试为首次 2.180、热 0.777/0.808。两次环境不同，不能用差值估计播放开销。空闲超过 30 秒会逐出，下一次重新付首次成本；界面现在明确标注首次构图/复用引擎。

十份最终音频均通过 mono F32、有限值、非空、原生 24kHz（Piper 为22.05kHz）检查。SenseVoice 回读只作诊断：大部分主体内容吻合；Pocket 长句出现 `comma>`、`<iod` 等疑似标点读出，需人工试听，**不标成质量通过**。前处理源码有短句规范化、SentencePiece 解码再分句重编码，尚未证实问题来源，不能直接归因于缓存。Kokoro 英文长句回读也有个别词偏差。自动回读不等于人工听感认证。

可试听产物在本机 `outputs/tts-warm-iphone-audio/`，逐格 CAF 在 `outputs/tts-warm-matrix-iphone/`，不提交音频或模型权重。

## 当前默认 LiquidCodec 包

Apple 自研页已补齐固定 v0.3.1-preview LiquidCodec 下载/导入、独立目录及dequant SHA接线，支持四个固定音色，保留旧LFM兼容入口。两者底层能力与实际加载的资产分开记录。此次 P3/P5 真机矩阵为4线程baseline、女声、一次预热加三次连续热请求，温度全部serious：

| 新 LC 包 | 英文短 | 英文长 | 中文短 | 中文长 |
|---|---:|---:|---:|---:|
| P3 | 0.765 | 0.820 | 0.731 | 0.815 |
| P5 | 1.034 | 1.068 | 1.008 | 1.086 |

八份音频格式/有限性通过，长句回读覆盖主体全文；P5中文长句18.32s，未复现旧样本40.96s。正常按钮路径、男声英语播放及CoreAudio排空在真机通过；模拟器同版通过，Mac Rust流式回调与最终PCM逐样本一致。[逐次证据](../../benchmarks/own-tts-warm-liquid-iphone-20261108.json)

**高温矩阵不等于codec退化。** 冷却、历史同文本复测，新版baseline女声热RTF约0.492；相同男声I8MM下旧/新分别约0.492/0.495。新旧female向量不同，权重存储也变了。固定codes的Mac隔离未发现LC导致大幅变慢，LC真机阶段耗时约占API一成。完整归因、波动和保留旧包的判断见[P3性能评估](p3-codec-performance-2026-11-08.md)，不要跨表计算codec加速比。

## 旧 LFM 包补测（与 LiquidCodec 分开）

本次最先补测了手机已有的 v0.2.0-preview，女声、seed20261029、max_tokens513、4线程、关闭播放。它是历史兼容包，不能代表新版 LiquidCodec。每格测试专用入口创建一次原 `ortts_engine`，连续调用四次，排除首次后取三个热请求中位数。自研页正常按钮仍逐次释放原 ABI 句柄；这里的热测试不代表其按钮已经接入 `speech::TtsCache`，后者服务多模型 speech ABI。

三个热请求中位数：

| 旧包 | 英文短 | 英文长 | 中文短 | 中文长 |
|---|---:|---:|---:|---:|
| P3 | 0.697 | 0.768 | 0.520 | 0.737 |
| P5 | 1.007 | 1.049 | 0.927 | 1.198* |

*P5 中文长句输出40.96s，疑似达到token上限，回读只得到第一句，不能算全文质量通过。P3长句和P5英文长句回读检查另保留原始文本。测试温度由 fair 升到 serious，P5 全部在 serious 状态，不能作为控制温度的架构比较。[逐次记录](../../benchmarks/own-tts-warm-legacy-iphone-20261108.json)。旧包保留在 `models/`；新版 LiquidCodec 使用独立 `models-liquid/`，界面明确区分。

## 为什么不能只看 82M / 82MB

82M 是参数数目，不是常驻内存上限。当前固定 GGUF 约189.6MB，还包含前处理、声码器及音色数据；量化并非每个 tensor 都是一个字节。执行时还需解量化/转换权重、激活、graph arena、临时 workspace 和输出。长序列会扩大工作区，allocator 峰值也不等于可回收的空闲对象。

同一 M5 Mac 的独立对照中，当前 ggml Kokoro 进程峰值约1044–1935MiB；Sherpa FP32 约679–744MiB，INT8 约512–514MiB。说明实现和内存规划确实影响很大，不能只归因模型大小。本轮没有新的 iPhone RSS 采样，不声称单句峰值已经降低。缓存只留一个模型并空闲释放，避免按音色堆积；它会有意让模型在连续对话期间常驻。

Mac 热 RTF：ggml 英文短/中文短/英文长为0.472/0.482/0.526；Sherpa FP32 为0.272/0.318/0.296，动态 INT8 为0.711/0.916/0.752。**Sherpa 并非所有量化都更快**。三种量化、G2P 和输出时长不同，不是严格算子消融；不能推断手机的 Sherpa 数字。详见[独立实验](../../experiments/kokoro-ab/README.md)，未把 Sherpa 链接到运行时。

## 生命周期与播放修复

- 一条串行 worker，一个 TTS。配置/模型/资产身份变动先释放旧引擎；音色属于请求，复用同一权重。切 ASR、取消、错误、后台、Apple 内存警告以及30秒空闲时清理。
- Rust `speech::cache::TtsCache` 要求显式已验证资产身份，保留 !Send/!Sync；宿主需在所属 worker 的 idle timer 上调用 `evict_expired()`。只更新 submodule、继续逐次 create/free 无法获得热启动收益。使用见 [SDK](../../runtime/SPEECH.md)。
- 资产首次完整 SHA 校验；后续按预期 SHA、inode、大小、纳秒修改时间失效。Android 同时复用已成功准备的 G2P 数据路径，避免每次遍历字典。
- Android 修复晚到的菜单回调在合成时重置音色。iOS 连续测试发现第三次 AVAudioEngine 初始化返回1852797029；改为复用图、停止时使旧回调失效，采样率变化时重连。
- iOS 模拟器和 Android ARM64 模拟器均通过：同音色复用、换音色仍复用、换模型不复用、取消后重新加载、31秒后过期，以及 Kokoro24k→Piper22.05k→Kokoro24k 播放切换。iOS 四次连续正常播放也通过；最终I8MM真机版再通过Kokoro三次复用、24k→22.05k→24k切换，以及LiquidCodec正常按钮合成和播放排空。两端13项 TTS/ASR 既有回归通过，Rust 实际 Pocket 权重例程通过配置/身份变更和取消逐出。[记录](../../benchmarks/tts-cache-lifecycle-20261108.json)

Android 是模拟器验证，不是 Android 真机性能；后台、内存压力及全部路由中断仍需产品设备验收。缓存不提供多模型并行，也没有引入第二份 ggml。

## 复现

使用已经安装且含已校验模型的设备，不下载、不录音。Python3.11+：

```sh
python3 tools/test_mobile_tts_matrix.py --target iphone --device DEVICE_ID --out outputs/warm-matrix
python3 tools/test_mobile_speech_demo.py --target iphone --device DEVICE_ID \
  --case kokoro-en --repeat 4 --out outputs/warm-playback
python3 tools/test_mobile_speech_demo.py --target simulator --device booted \
  --case kokoro-en --repeat 3 --scenario rate --out outputs/rate-switch
# Android 使用 --target android --device emulator-5554；安装可传 --install APK_OR_APP。
# 取消/切模型/换音色 --scenario cancel/switch/voice --repeat 3；ttl 用 --repeat 2。
python3 tools/test_own_tts_matrix.py --device DEVICE_ID --pack liquid --out outputs/liquid-warm
# 旧包另用 --pack legacy，避免混入当前默认模型结果。
python3 tools/test_apple_own_playback.py --target iphone --device DEVICE_ID \
  --pack liquid --variant P3 --voice male --out outputs/liquid-playback
```

矩阵 QA 模式临时保持屏幕亮，写完报告后恢复；用户手动锁屏仍会中断。报告不含设备 UDID、签名信息或用户凭据。
