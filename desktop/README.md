# OrTTS 桌面 Demo（macOS / Linux）

在 macOS 与 Linux 上本地离线合成与识别语音，采用与 iOS 一致的分组卡片界面与三标签页结构：**OrTTS 合成**、**其他语音合成**、**语音识别**。安装包不含模型权重，首次使用可通过应用内下载或导入本地模型目录。

## 启动

- **macOS Apple Silicon**：打开 `OrTTS.app`（使用 DMG 时拖入“应用程序”）。
- **Linux**：运行文件夹包内的 `./ortts`，或从源码启动（环境准备见 [Linux 使用说明](../linux/README.md)）。

## 功能与使用

1. **OrTTS 合成**：默认 **0.6B Q4 / P3**（Q8 / 历史版可选 P3/P5）。点击“下载 / 继续…”获取模型，或点击“导入本地模型…”选择完整模型文件夹；校验完成后选择音色、输入文本即可合成、播放、随时停止或保存 WAV。
2. **其他语音合成**：随包运行时启用语音扩展时，可使用 Kokoro、PocketTTS、Piper、Kitten 等开源模型合成并保存 WAV。
3. **语音识别**：支持 SenseVoice、Moonshine（英语增量）以及 Paraformer（中英流式实验档，需启用 Sherpa 运行时），可导入音频识别并导出文本。

## 常见问题

- **下载中断**：再次选择相同存放位置即可自动断点续传，已校验文件会直接复用。
- **下载通道 401 / 限流**：可在下载下拉框中切换 **ModelScope** 或 **HF Mirror**。
- **停止响应**：支持协作式取消的运行时会在检查点安全停止并保留已加载模型，无需重新加载即可继续下次合成。
- **音频默认保存位置**：macOS 位于 `~/Library/Application Support/OrTTS Desktop/outputs/`，Linux 位于 `~/.local/share/ortts-desktop/outputs/`。

源码运行、打包与自动化验收说明见 [开发与代理说明](AGENT_README.md)。
