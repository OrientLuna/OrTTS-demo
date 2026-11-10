# OrTTS-demo

OrTTS 的端侧语音合成应用与可嵌入 CPU 运行时，支持 **0.6B／1.7B**、P3／P5、男女各两个音色，以及边生成边播放。

## 可选多模型语音 SDK

除现有自研模型 Demo 外，后端提供可选的 [多模型 TTS / ASR C ABI 与 Rust 接口](runtime/SPEECH.md)：MOSS-TTS-Nano、Kokoro、PocketTTS、Piper、Kitten、ZipVoice，以及 SenseVoice / Moonshine。Moonshine 另提供英语增量识别接口（partial/final、分段、取消）。这些流水线与原接口共用一份 ggml；不表示能执行任意 ONNX/GGUF。新版手机 Demo 已接入 MOSS-TTS-Nano、Kokoro、Kitten、Piper、PocketTTS、SenseVoice 和 Moonshine，支持固定版本下载、SHA256 校验及 TTS/ASR 切换；ZipVoice 当前仍为 SDK 能力。详见 [多模型 Demo](docs/MOBILE_SPEECH_DEMO.md)。

## 平台支持

| 平台 | 当前提供 | 使用入口 |
|---|---|---|
| Android ARM64 | 可安装 APK、模型下载 / ZIP 导入、流式播放 | [快速开始](#android) |
| iOS ARM64 | UIKit Demo 源码、模型下载 / 文件夹导入、流式播放、停止、重播；已在 iPhone 17 验证 | [iOS 使用](apple/README.md#ios-使用) |
| macOS | 命令行 Demo、离线合成与保存音频；Apple Silicon 已实测 | [macOS 使用](apple/README.md#macos-使用) |
| Linux x64 / ARM64 | CPU 命令行构建入口、C ABI、Rust 绑定 | [运行时集成](runtime/README.md) |

iOS 需要自行构建和开发签名，尚无公开 IPA / TestFlight；macOS 当前为 CLI，无图形安装包。优化档位须匹配设备能力，baseline 是保守起点。当前使用 CPU，尚未接入 Metal、Core ML 或 QNN。

## Android

1. [下载 Android ARM64 APK](https://github.com/OrientLuna/OrTTS-demo/releases/download/v0.3.1-preview/OrTTS-0.3.1-preview-arm64-v8a.apk)并安装。
2. 选择0.6B或1.7B、P3或P5，下载所需权重；也可导入本地模型ZIP。
3. 输入文字、选择音色，点击“合成语音”。默认开启“边生成边播放”。

| 模型 | P5下载 | 包含P3后的总量 |
|---|---:|---:|
| 0.6B · 混合Q8 | 1.66 GB | 1.81 GB |
| 1.7B · 混合Q8 | 3.07 GB | 3.28 GB |

共享文件只保存一份，切换P3时补齐预测器。默认使用0.6B P3；也可选择P5原生预测器和`female`、`female_2`、`male`、`male_2`四个音色。模型清单固定为ModelScope的`v0.3.1-preview`版本，下载地址仍可手工修改。

首次下载请保持应用在前台。首次合成需要加载模型，较慢设备会在播放前增加缓冲。正常卸载会清理应用内模型、缓存及生成音频；手动保存到外部的文件不受影响。

上面的 0.3.1-preview APK 需要 Android 9 或更高版本，以及支持 DotProd、I8MM 和 FP16 的 ARM64 CPU。新版多模型 Demo 使用 arm64-baseline，安装包不含模型权重。手机参考数据见[性能说明](docs/BENCHMARKS.md)。

模型仓库：[0.6B](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B) · [1.7B](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-1.7B)

## iOS 与 macOS

iOS Demo 可选择模型和音色，下载并校验模型后边生成边播放，支持停止、重播及本地模型文件夹导入。功能和安装边界见 [Apple Demo](apple/README.md)。

macOS 使用 `ortts-apple MODEL_ROOT P3|P5 TRUSTED_BRIDGE_SHA TEXT` 离线合成，输出 `~/Documents/ortts-output.caf`；完整命令见 [构建说明](docs/BUILD.md#apple)。

## 文档导航

- [多模型 Demo 下载与 TTS/ASR 切换](docs/MOBILE_SPEECH_DEMO.md)
- [构建与开发环境](docs/BUILD.md)
- [模型准备](docs/MODEL_ASSETS.md)
- [解码器兼容](docs/DECODERS.md)
- [CPU参数](docs/CPU_PROFILES.md)与[手机性能](docs/BENCHMARKS.md)
- [C ABI／Rust集成](runtime/README.md)
- [iPhone 多模型热 RTF 与缓存修复](docs/development/tts-warm-cache-2026-11-08.md)
- [P3 新旧 codec 性能归因](docs/development/p3-codec-performance-2026-11-08.md)
- [Kokoro Mac 后端实测对照](experiments/kokoro-ab/README.md)
- [完整文档索引](docs/README.md)

## 致谢与许可

扩展手机 Demo 随附 eSpeak NG G2P，组合二进制发行需满足 GPL 对应源码义务；源码、构建补丁和模型权重许可分别处理，详见 [手机 G2P 与发行](docs/MOBILE_G2P.md)。

运行时基于[audio.cpp](https://github.com/0xShug0/audio.cpp)与[ggml](https://github.com/ggml-org/ggml)，感谢Qwen3-TTS、Liquid AI、speech.cpp和Vocos等开源项目。组件归属与许可见[NOTICE.md](NOTICE.md)；模型权重适用各模型仓库的许可。
