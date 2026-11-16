# OrTTS Apple Demo（iOS & macOS CLI）

iOS 提供原生 UIKit 三标签页 App，支持本地语音合成、流式边生成边播放、打断停止以及多模型 TTS / ASR。macOS 图形界面请看[桌面版说明](../desktop/README.md)，本目录同时提供 macOS 命令行入口。

## iOS 使用

1. **OrTTS 合成**：默认 **0.6B Q4 / P3**（Q8 与旧版兼容包可选 P3 / P5）。点击“下载 / 检查所选模型”或“导入本地模型文件夹”（需包含 `native/`、`voices/` 与对应 `P3/` 目录），输入文字即可边生成边播放，支持随时点击“停止”打断或“重播”。
2. **其他语音合成**：支持 Kokoro、Kitten、Piper、PocketTTS。
3. **语音识别**：支持 SenseVoice、Moonshine，以及启用 Sherpa 时的 Paraformer 实验档；支持麦克风录音、导入音频文件及直接识别上次合成结果。

下载支持自动、Hugging Face、HF Mirror 与 ModelScope 通道，通道设置在各标签页间共享。更多操作见[多模型 Demo 指南](../docs/MOBILE_SPEECH_DEMO.md)。

## 构建与安装

- 需要 Mac 与 Xcode，iOS 最低部署版本为 **iOS 16.3**（真机安装需配置自己的开发签名）。
- 构建命令见[构建说明 / Apple](../docs/BUILD.md#apple)。

## macOS 命令行使用

```sh
build/apple-mac/ortts-apple /path/to/models P3 TRUSTED_BRIDGE_SHA '你好。'
afplay ~/Documents/ortts-output.caf
```

开发参数与 QA 验收入口见 [AGENT_README](AGENT_README.md)。
