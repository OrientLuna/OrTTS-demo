# OrTTS Apple Demo

iOS 提供 UIKit App，支持本地语音合成、流式播放和多模型 TTS / ASR。
本目录的 macOS 入口是命令行；图形界面请看[桌面版](../desktop/README.md)。

## iOS 使用

1. 在“OrTTS语音合成”页选择模型和音色。默认是 **0.6B Q4 / P3**，Q4 不支持 P5。
2. 点击“下载 / 检查所选模型”，或导入已有的模型文件夹。首次下载请保持前台。
3. 输入文字，点击“合成并播放”；支持边生成边播放，点击“停止”可中止。
4. 完成后可重播；音频保存在 `Documents/ortts-output.caf`，可通过文件共享取出。

模型菜单也提供 Q8 和旧 LFM 兼容包；各版本独立保存，已有模型不会被静默替换。
“更新可下载模型”只刷新目录，权重按需下载；技术版本可在“查看版本详情”中查看。
下载支持自动、Hugging Face、HF Mirror 和 ModelScope 通道，设置在模型页面间共享。

导入时选择包含 `native/`、`voices/` 和所需 `P3/` 的模型文件夹，不支持 ZIP，
不覆盖已有同名文件夹。模型选择与资源准备见[模型目录](../docs/OWN_MODEL_CATALOG.md)。

底部另外两个页面提供：

- **第三方语音模型**：Kokoro、Kitten、Piper、PocketTTS。
- **语音识别**：SenseVoice、Moonshine，支持录音、音频文件及识别上次合成结果。

更多操作见[多模型 Demo](../docs/MOBILE_SPEECH_DEMO.md)。

## 安装与构建

需要 Mac 和 Xcode；最低部署版本为 **iOS 16.3**。真机安装需使用自己的开发签名。
当前没有公开 IPA、TestFlight 或 App Store 版本。
构建命令见[构建说明 / Apple](../docs/BUILD.md#apple)。

iPhone 17 / iOS 27.0.1 已验证 Q4 合成、播放和停止；SDK 取消接口也已通过真机和模拟器验收。
这不代表所有旧版 iOS、设备和模型均已实测。

## macOS 使用

准备模型并构建后运行：

```sh
build/apple-mac/ortts-apple /path/to/models P3 TRUSTED_BRIDGE_SHA '你好。'
afplay ~/Documents/ortts-output.caf
```

详细开发参数、模型校验和验收记录见 [AGENT_README](AGENT_README.md)。
