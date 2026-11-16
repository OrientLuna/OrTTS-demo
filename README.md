<p align="center"><img src="assets/brand/ortts-icon.png" width="128" alt="OrTTS 三色语音积木" /></p>

# OrTTS-demo

**OrTTS 的端侧语音合成与识别 Demo 及可嵌入运行时，所有模型均在设备本地离线运行。**

除自研 **OrTTS** 语音合成模型外，项目还集成了 Kokoro、PocketTTS、Piper、Kitten、SenseVoice、Moonshine 与 Paraformer（实验）等开源 TTS / ASR 模型，支持在同一个应用中切换体验，并支持不同任务/句柄并发推理与任务级取消。

## 下载与快速开始

**[下载最新发布版本（Latest Release）](https://github.com/OrientLuna/OrTTS-demo/releases/latest)** · [全部版本与预览包](https://github.com/OrientLuna/OrTTS-demo/releases)

| 平台 | 当前支持 | 使用说明 |
|---|---|---|
| Android ARM64 | 3 标签页 APK（OrTTS 合成 / 其他语音合成 / 语音识别）、模型下载与 ZIP 导入、流式播放 | [Android 快速开始](#android-快速开始) |
| iOS ARM64 | UIKit 3 标签页 Demo（流式播放、录音与文件识别、模型下载与导入）；需自行构建签名 | [iOS 使用](apple/README.md) |
| macOS Apple Silicon | 3 标签页桌面 GUI（统一 iOS 风格主题）、模型下载与导入、`.app` / DMG 打包 | [桌面版说明](desktop/README.md) |
| Linux | 3 标签页桌面 GUI（与 macOS 共用主题）、ALSA 边合成边播放、文件夹包构建 | [Linux 桌面版](linux/README.md) |
| Windows | 原生运行库与桌面客户端规划中 | [开发计划](#开发计划) |

### Android 快速开始

1. 从 [Latest Release](https://github.com/OrientLuna/OrTTS-demo/releases/latest) 下载 APK 并安装。
2. 在应用内选择模型，通过在线下载或导入本地文件夹 / ZIP 获取权重。
3. 输入文本或导入/录制音频，即可离线合成或识别（自研模型支持边生成边播放与随时停止）。

### macOS / Linux 快速开始

- **macOS**：自行构建或打开 `OrTTS.app`（DMG 拖入“应用程序”即可）。应用采用 **OrTTS 合成 / 其他语音合成 / 语音识别** 三标签页设计，默认 **0.6B Q4 / P3**，支持断点续传下载与本地模型目录导入。
- **Linux**：按 [Linux 桌面版说明](linux/README.md) 组装文件夹包并运行 `./ortts`，或通过 `python3 -m linux.app` 启动，支持 ALSA 边合成边播放。

## 模型与后端支持

### OrTTS 自研模型

| 模型包 | 推理版本 | 说明 |
|---|---|---|
| 0.6B · Q4（精简） | P3 | 默认推荐组合，内存占用更低 |
| 0.6B · Q8（均衡） | P3 / P5 | 标准精度模型包 |
| 1.7B · Q8（增强） | P3 / P5 | 移动端可选 |

音色随模型包提供（女声 1 / 女声 2 / 男声 1 / 男声 2）。模型仓库：[0.6B](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B) · [1.7B](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-1.7B)，资源准备见[模型资产](docs/MODEL_ASSETS.md)与[模型目录](docs/OWN_MODEL_CATALOG.md)。

### 其他 TTS / ASR 后端

| 用途 | 后端 | 接入平台 |
|---|---|---|
| 语音合成 | Kokoro、PocketTTS、Piper、Kitten | Android / iOS / 桌面端（macOS、Linux） |
| 语音合成 | MOSS-TTS-Nano | Android |
| 语音合成 | ZipVoice | C / Rust SDK |
| 语音识别 | SenseVoice（中/英离线） | Android / iOS / 桌面端 |
| 语音识别 | Moonshine（英语流式增量） | Android / iOS / 桌面端 |
| 语音识别 | Paraformer（中/英流式实验档，Sherpa） | Android / iOS / 桌面端 |

## 开发计划

- [x] Android / iOS 本地语音 Demo、模型下载与导入、多模型 TTS / ASR 接入。
- [x] macOS / Linux 共享三标签页桌面端（统一 iOS 风格主题）、断点续传下载与本地模型复用。
- [x] 任务级协作式取消，以及 ggml 域内 / Sherpa 跨域并发推理。
- [ ] macOS Developer ID 正式签名与公证 DMG 发布。
- [ ] Windows 原生运行库与桌面客户端；Linux 发行版通用打包（AppImage / `.deb`）。
- [ ] Apple Core ML / Metal、高通 QNN 等硬件加速路线。

## 文档导航

- [构建与开发环境](docs/BUILD.md)
- [桌面端说明（macOS / Linux）](desktop/README.md) · [Linux 专属说明](linux/README.md)
- [Apple（iOS / macOS CLI）说明](apple/README.md) · [多模型 Demo 使用指南](docs/MOBILE_SPEECH_DEMO.md)
- [C ABI 集成](runtime/README.md) · [Rust SDK](runtime/rust/README.md) · [多模型语音 SDK](runtime/SPEECH.md)
- [模型准备](docs/MODEL_ASSETS.md) · [CPU 构建档位](docs/CPU_PROFILES.md) · [完整文档索引](docs/README.md)

## 致谢与许可

扩展 Demo 随附 eSpeak NG G2P，组件归属与开源许可详见 [NOTICE.md](NOTICE.md) 与 [手机 G2P 与发行](docs/MOBILE_G2P.md)。
运行时基于 [audio.cpp](https://github.com/0xShug0/audio.cpp)、[ggml](https://github.com/ggml-org/ggml) 与 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)，感谢 Qwen3-TTS、Liquid AI、speech.cpp 与 Vocos 等开源项目。
