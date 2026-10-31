# OrTTS-demo

OrTTS 的端侧语音合成应用与可嵌入 CPU 运行时，支持 P3（速度优先）、P5（标准版）及男女音色。模型在设备本地运行。

## 平台支持

| 平台 | 当前提供 | 使用入口 |
|---|---|---|
| Android ARM64 | 可安装 APK、模型下载 / ZIP 导入、流式播放 | [快速开始](#android) |
| iOS ARM64 | UIKit Demo 源码、模型下载 / 文件夹导入、流式播放、停止、重播；已在 iPhone 17 验证 | [iOS 使用](apple/README.md#ios-使用) |
| macOS | 命令行 Demo、离线合成与保存音频；Apple Silicon 已实测 | [macOS 使用](apple/README.md#macos-使用) |
| Linux x64 / ARM64 | CPU 命令行构建入口、C ABI、Rust 绑定 | [运行时集成](runtime/README.md) |

iOS 需要自行构建和开发签名，尚无公开 IPA / TestFlight；macOS 当前为 CLI，无图形安装包。优化档位须匹配设备能力，baseline 是保守起点。当前使用 CPU，尚未接入 Metal、Core ML 或 QNN。

## Android

1. [下载 Android ARM64 APK](https://github.com/OrientLuna/OrTTS-demo/raw/refs/heads/main/releases/OrTTS-0.2.3-preview-arm64.apk)并安装。
2. 选择 P3 或 P5，下载模型；也可导入本地权重 ZIP。
3. 输入文字、选择音色，点击“合成语音”。

P3 速度优先，P5 为标准版。P5 下载约 2.0 GB，P3 约 2.2 GB；共享文件只保存一份，切换模型时补齐缺失组件。下载地址可修改，支持 ModelScope 或其他 HTTP／HTTPS 文件源。

首次下载请保持应用在前台。首次合成需要加载模型；运行较慢时，播放前会增加缓冲。首块生成时间不等于实际开始播放时间。正常卸载会清理应用内的模型、缓存和生成音频；手动保存的外部 ZIP／APK 不受影响。

当前 APK 需要 Android 9 或更高版本，以及支持 DotProd、I8MM、FP16 的 ARM64 CPU。本版 APK 已在荣耀90 Pro 验证；不支持必要指令的设备会收到提示。

模型与权重：[OrientLuna/OrTTS-Qwen3-LFM-0.6B](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B)

## iOS 与 macOS

iOS Demo 可选择模型和音色，下载并校验模型后边生成边播放，支持停止、重播及本地模型文件夹导入。功能和安装边界见 [Apple Demo](apple/README.md)。

macOS 使用 `ortts-apple MODEL_ROOT P3|P5 TRUSTED_BRIDGE_SHA TEXT` 离线合成，输出 `~/Documents/ortts-output.caf`；完整命令见 [构建说明](docs/BUILD.md#apple)。

## 文档导航

- [构建与开发环境](docs/BUILD.md)：源码准备及各平台构建命令。
- [模型准备](docs/MODEL_ASSETS.md)：下载、导入、原生目录与清单校验。
- [CPU 优化参数](docs/CPU_PROFILES.md)：平台档位、指令集和兼容条件。
- [实测与限制](docs/BENCHMARKS.md)：Android / iPhone 数据及测试口径。
- [C ABI / Rust 集成](runtime/README.md)：PCM、取消及并发约束。
- [完整文档索引](docs/README.md)。

## 许可

运行时代码与依赖见 [NOTICE.md](NOTICE.md)。模型权重遵循模型仓库中的组件许可。
