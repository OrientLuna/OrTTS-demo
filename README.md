<p align="center"><img src="assets/brand/ortts-icon.png" width="128" alt="OrTTS 三色语音积木" /></p>

# OrTTS-demo

**OrTTS 的端侧语音合成 Demo 与可嵌入运行时，模型在设备本地运行。**

为了方便对比语音模型的效果，也提供了其他 TTS / ASR 后端集成，具体见[模型与后端支持](#模型与后端支持)。

## 下载与体验

**[下载最新发布版本（Latest Release）](https://github.com/OrientLuna/OrTTS-demo/releases/latest)** · [全部版本与预览包](https://github.com/OrientLuna/OrTTS-demo/releases)

在 Release 的 Assets 中选择对应平台的附件；系统要求、签名状态和本次发布功能以该版本说明为准。下文描述当前源码进展，不代表每个已发布安装包都包含全部功能。

| 平台 | 当前进展 | 使用说明 |
|---|---|---|
| Android ARM64 | APK、模型下载 / ZIP 导入、语音合成与播放、多模型 TTS / ASR | [Android 快速开始](#android-快速开始) |
| iOS ARM64 | UIKit Demo 源码，支持模型下载 / 文件夹导入；需自行构建和签名 | [iOS 使用](apple/README.md#ios-使用) |
| macOS Apple Silicon | 桌面 GUI、模型下载 / 导入、合成后播放、`.app` / DMG 打包；新版已在本机复验 | [桌面版](desktop/README.md) · [CLI](apple/README.md#macos-使用) |
| Linux | 桌面 GUI、模型下载 / 导入、流式播放与文件夹包构建入口；另有 x64 / ARM64 运行时 | [Linux 桌面版](linux/README.md) · [运行时](runtime/README.md) |
| Windows | 原生运行库和桌面客户端待完善 | [开发计划](#开发计划) |

iOS 暂无公开 IPA / TestFlight；macOS 当前产物为本机构建、ad-hoc 签名，尚未发布 Developer ID 签名并公证的正式安装包。没有对应 Release 附件的平台，请按文档自行构建。

### Android 快速开始

1. 从 [Latest Release](https://github.com/OrientLuna/OrTTS-demo/releases/latest) 下载适合设备的 APK 并安装。
2. 在应用内选择模型，下载或导入权重。
3. 输入文字、选择音色，点击“合成语音”；自研模型支持边生成边播放。

安装包不包含模型权重；首次下载请保持应用在前台，首次合成需要加载模型。CPU 兼容要求因构建而异，具体见 Release 说明与 [CPU 构建档位](docs/CPU_PROFILES.md)。

### macOS 快速开始

自行构建后打开 `OrTTS.app`，或通过 DMG 拖入“应用程序”。选择模型版本，导入完整模型目录或下载模型后，即可输入文字、合成、播放或保存 WAV。

当前桌面版默认 **0.6B Q4 / P3**。下载需用户确认，支持取消、断点继续和已校验文件复用，不在启动时自动下载。macOS 仍为合成后播放，暂不提供第三方 TTS / ASR。构建、安装和签名边界见[桌面版说明](desktop/README.md)。

### Linux 快速开始

按 [Linux 桌面版说明](linux/README.md) 组装文件夹包并运行 `./ortts`，或从源码启动。模型导入与下载界面和 macOS 共用，Linux 通过 ALSA 边合成边播放。文件夹包依赖系统 Python / Tk / ALSA，原生库还需匹配目标架构与发行版；当前不是通用 AppImage / `.deb`，无声设备自动化验证也不等于实体声卡试听通过。

## 模型与后端支持

### OrTTS 自研模型

| 模型包 | 推理版本 | 说明 |
|---|---|---|
| 0.6B · Q4（精简） | P3 | 当前默认组合，不支持 P5 |
| 0.6B · Q8（均衡） | P3 / P5 | 标准模型包 |
| 1.7B · Q8（增强） | P3 / P5 | 移动端可选；当前 macOS / Linux 桌面菜单尚未接入 |

音色按模型包实际资源提供，包含女声1 / 女声2 / 男声1 / 男声2；历史包可能只有部分音色。模型与变体不能任意混用。

模型仓库：[0.6B](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B) · [1.7B](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-1.7B)。模型准备与版本选择见[模型资产](docs/MODEL_ASSETS.md)和[模型目录](docs/OWN_MODEL_CATALOG.md)。

### 其他 TTS / ASR 后端

| 用途 | 后端 | 当前应用接入 |
|---|---|---|
| 语音合成 | Kokoro、PocketTTS、Piper、Kitten | Android / iOS 多模型页 |
| 语音合成 | MOSS-TTS-Nano | Android 多模型页；iOS 页面尚未接入 |
| 语音合成 | ZipVoice | SDK 接口，暂未接入手机菜单 |
| 语音识别 | SenseVoice | Android / iOS；中文、英文离线识别 |
| 语音识别 | Moonshine | Android / iOS；英语增量识别 |

“后端已接入”不等于所有平台、语言和音色均已验证，也不支持任意 ONNX / GGUF 文件。应用操作与限制见[多模型 Demo](docs/MOBILE_SPEECH_DEMO.md)，C ABI / Rust 接口见[语音 SDK](runtime/SPEECH.md)。

## 开发计划

- [x] Android / iOS 本地语音 Demo、模型下载与导入、多模型 TTS / ASR 接入。
- [x] macOS 最小桌面 Demo、Q4/P3 本机验证及 app / DMG 打包。
- [x] macOS / Linux 共用模型下载、断点继续与文件复用；Linux 流式桌面及文件夹包构建入口。
- [ ] macOS Developer ID 签名、公证与正式安装包发布。
- [ ] Windows 原生运行库与桌面客户端；Linux 发行版兼容构建、`.deb` 打包与实体声卡验收。
- [ ] 桌面端第三方 TTS / ASR 页面，以及 macOS 流式播放。
- [ ] Apple Core ML / Metal、高通 QNN 等设备加速路线。
- [ ] 更多音色、发音与自然度改善，以及更完整的音质评测。
- [ ] 统一条件下的性能回归与跨设备验证。

以上是开发方向，不代表已经实现或承诺发布时间。当前运行时使用 CPU；性能数据必须结合具体模型、设备、供电、线程和计时边界理解，不将不同条件下的 RTF 当作统一排名。

## 文档导航

- [多模型 Demo 下载与 TTS/ASR 切换](docs/MOBILE_SPEECH_DEMO.md)
- [构建与开发环境](docs/BUILD.md)
- [macOS 桌面 Demo 与 app / DMG 打包](desktop/README.md)
- [Linux 流式桌面 Demo 与文件夹包](linux/README.md)
- [模型准备](docs/MODEL_ASSETS.md)
- [解码器兼容](docs/DECODERS.md)
- [CPU 构建档位](docs/CPU_PROFILES.md)与[性能记录](docs/BENCHMARKS.md)
- [C ABI 集成](runtime/README.md) · [Rust SDK 与任务级取消](runtime/rust/README.md)
- [完整文档索引](docs/README.md)

## 致谢与许可

扩展手机 Demo 随附 eSpeak NG G2P，组合二进制发行需满足 GPL 对应源码义务；源码、构建补丁和模型权重许可分别处理，详见 [手机 G2P 与发行](docs/MOBILE_G2P.md)。

运行时基于[audio.cpp](https://github.com/0xShug0/audio.cpp)与[ggml](https://github.com/ggml-org/ggml)，感谢Qwen3-TTS、Liquid AI、speech.cpp和Vocos等开源项目。组件归属与许可见[NOTICE.md](NOTICE.md)；模型权重适用各模型仓库的许可。
