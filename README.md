# OrTTS-demo

**OrTTS 的端侧语音合成应用与可嵌入运行时。**

支持 P3／P5、`female`／`male` 两个音色，默认边生成边播放。模型在设备本地运行。

## Android

1. [下载 Android ARM64 APK](https://github.com/OrientLuna/OrTTS-demo/raw/refs/heads/main/releases/OrTTS-0.2.3-preview-arm64.apk)并安装。
2. 选择 P3 或 P5，下载模型；也可导入本地权重 ZIP。
3. 输入文字、选择音色，点击“合成语音”。

P3 速度优先，P5 为标准版。P5 下载约 2.0 GB，P3 约 2.2 GB；共享文件只保存一份，切换模型时补齐缺失组件。下载地址可修改，支持 ModelScope 或其他 HTTP／HTTPS 文件源。

首次下载请保持应用在前台。首次合成需要加载模型；运行较慢时，播放前会增加缓冲。首块生成时间不等于实际开始播放时间。正常卸载会清理应用内的模型、缓存和生成音频；手动保存的外部 ZIP／APK 不受影响。

当前 APK 需要 Android 9 或更高版本，以及支持 DotProd、I8MM、FP16 的 ARM64 CPU。本版 APK 已在荣耀90 Pro 验证；不支持必要指令的设备会收到提示。

模型与权重：[OrientLuna/OrTTS-Qwen3-LFM-0.6B](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B)

## CPU 实测

female 音色，原生 CPU 4线程，短句／长句热 RTF；数值越低越好。每组一次热请求，未锁频。

| 设备 | P3 | P5 | 原版 Qwen |
|---|---:|---:|---:|
| OPPO Find N5 · SM8750 · 16GB | 0.525／0.774 | 0.636／0.887 | 1.619／2.501 |
| 荣耀90 Pro · SM8475 · 16GB | 1.015／1.104 | 1.235／1.356 | 2.233／2.434 |

P3／P5为流式生成，原版为优化 CPU 的离线对照；以上不含播放器等待。平均 RTF 不能单独保证持续播放无停顿。可复现输入与结果见[测试数据](benchmarks/android-cpu.json)。

## 构建与集成

- [构建说明](docs/BUILD.md)
- [各平台 CPU 优化参数与验证范围](docs/CPU_PROFILES.md)
- [模型资产格式](docs/MODEL_ASSETS.md)
- [Android 源码](android/)
- [iOS / macOS CPU 原型](apple/README.md)
- [可嵌入 CPU 引擎与 Rust 接口](runtime/README.md)

原生运行时基于 audio.cpp，当前使用 CPU。iOS CPU Demo 已提供源码和真机原型验证；后续计划包括 Apple Core ML／Metal、高通 QNN、更多音色及音质改善。

## 许可

运行时代码与依赖见 [NOTICE.md](NOTICE.md)。模型权重遵循模型仓库中的组件许可。
