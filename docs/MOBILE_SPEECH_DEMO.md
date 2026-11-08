# 多模型手机 Demo（0.4.0 候选）

本版统一的是流水线使用的 ggml 与应用生命周期调度，并提供独立 TTS/ASR 接口。不是通用 ONNX 执行器，也没有引入 sherpa-onnx。手机使用 CPU arm64-baseline，尚未接入 Metal、Core ML 或 QNN。

## 使用

Android 在主页进入多模型语音页，选择 TTS 或 ASR；iOS 底部直接选择“中文合成”“多模型合成”或“语音识别”，任务各自保留页面状态。点击模型名称切换，选择后下载或导入。原有 P3/P5 模型保留独立页面和清单。

| 菜单模型 | 输入/输出 | 下载量（十进制，约） | 音色/识别模式 |
|---|---|---:|---|
| PocketTTS Q8 | 英语文字 → 24kHz 音频 | 148.1MB | alba、anna、george；边合成边播放 |
| Kokoro 82M Q8 | 中文/英语文字 → 24kHz 音频 | 189.6MB | 按中英文音色选择语言；文本分块播放 |
| Kitten mini 0.8 | 英语文字 → 24kHz 音频 | 302.2MB | Bella、Leo；离线合成后播放 |
| Piper Lessac medium | 英语文字 → 22.05kHz 音频 | 62.7MB | 固定音色；离线合成；具体权重有使用限制 |
| SenseVoice Small Q8 | 音频 → 中文/英语文字 | 254.2MB | 完整输入结束后识别 |
| Moonshine Tiny Q8 | 音频 → 英语文字 | 60.4MB | 增量 partial/final；分段重新解码 |

音色资产必须匹配模型包。手机回归固定 alba、anna，未逐一试听全部音色。Moonshine 的文件是 Q8，但增量 encoder 使用展开 F16 权重，内存不等于磁盘文件大小；目前不是逐层 KV 缓存的完整流式架构。

ASR 支持麦克风权限、录音停止、取消和音频文件输入；Android 支持 PCM16/F32 WAV，iOS 使用系统可解码音频格式。输入转换为 16kHz 单声道，最长 60 秒，Moonshine 按段处理。“识别上次合成”可验证合成到识别的数据路径；请按音频语言选择模型。

## 下载和本地导入

下载清单来自 [共享模型目录](../runtime/models/catalog.example.json)。该文件保留 example 文件名，手机实际内置它的副本；每个资产包括 HTTPS 地址、固定 revision、大小和 SHA256，不跟踪远端 main。Android 原有模型入口仍使用固定 ModelScope 0.3.1-preview 清单；Apple 自研入口默认固定 0.3.1-preview LiquidCodec，并保留独立 0.2.0-preview LFM 兼容入口及旧模型目录。

下载到临时文件，校验后替换；已通过校验的文件直接复用，取消时不会把未完成文件当作可用模型。未完成的大文件重新下载，不保证 HTTP 断点续传。保持应用在前台。Android 多模型支持 ZIP 导入（保留清单相对路径），iOS 导入包含同样相对路径的模型文件夹；导入也必须匹配大小和 SHA256，不接受任意 GGUF。

没有将权重嵌入 APK/应用，也没有把目录的 `distribution_cleared` 自动改成 true。模型/音色许可提示与权重限制分别保留；Piper Lessac 的研究语料使用限制不能当作通用商用许可。ZipVoice 仍需参考音频/转写接线，未列入手机菜单。

Kokoro、Kitten、Piper 共用随应用分发的 eSpeak NG 1.52.0 库和字典。组合应用发行需要履行 GPL-3.0-or-later 的源码及许可义务；不能只按仓库 Apache-2.0 声称整个二进制是 Apache。构建脚本生成对应 eSpeak 源码归档，公开发行时应与 OrTTS 对应源码/构建说明一起提供。eSpeak 是 G2P，不是第二份神经网络推理框架。

## 引擎缓存与性能

两端多模型合成页保留单个 TTS 引擎，界面区分首次构图与复用引擎；音色切换复用，模型/任务切换、取消/错误、后台及 30 秒空闲后释放。iOS 同时复用播放器图，采样率变化时重新连接，避免连续播放反复创建 AVAudioEngine。首次完整校验模型，未改变的文件不逐句重复扫描全部权重。详见[缓存修复与 iPhone 热 RTF](development/tts-warm-cache-2026-11-08.md)和 [Mac Kokoro 后端对照](../experiments/kokoro-ab/README.md)。

## 验证范围

自动化入口：`tools/test_mobile_speech_demo.py --help`。它只使用已有测试模型，默认不下载，不录制用户音频；可选 seed 将已有资产放入应用容器。覆盖两音色合成、取消、英语和中文文件识别、合成后识别，以及缓存文件完整校验。物理设备和模拟器结果分开记录，模拟器速度不能作为手机性能。

交互麦克风授权/连续录音、所有文件选择器、弱网完整大模型下载、后台中断及长时间运行仍需独立人工验收。中文固定样本在 SenseVoice 输出中存在多余尾字，保留原始结果，功能通过不代表字错率为零或听感通过。

iOS 模拟器还验证了从网络重新下载 alba 音色文件（约 6.2MB），其余大模型为本地已有缓存；这不能替代完整大包弱网验收。Android 实际导入测试覆盖正常音色 ZIP、坏哈希和路径越界拒绝。

原始摘要见 [手机与组合后端记录](../benchmarks/mobile-speech-demo-20261107.json)。macOS 组合库的五 TTS / 两 ASR、Rust 和旧 P3 短句通过。默认15秒增量内存测试首次触发门限，随后独立诊断及完整隔离回归通过，未放宽门限；首次原因未确立，保留失败记录。当前 LiquidCodec 大包尚未重新做端到端验收。

## 构建与发行

[构建说明](BUILD.md)给出 LiquidCodec 与 speech 共用一份 ggml 的构建步骤。Android 将两个 ABI 链接到现有 libaudiocpp.so，不再额外打包另一份 libortts.so；iOS 链接同一 OrTTS.framework。旧 JNI 与新 C ABI 是不同入口，应用工作队列统一串行执行，不承诺并行推理。

Android 正式 APK 必须使用既有发布证书签名才能覆盖安装旧版本；debug 和 unsigned release 不能充当正式稳定安装包。iOS 需要自己的开发签名，目前没有公开通用 IPA。个人开发签名、描述文件和权重不上传到发布附件。
