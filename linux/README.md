# OrTTS Linux 桌面 Demo

与 macOS 共用三标签页界面与统一主题，在 Linux 上提供本地语音合成与识别，自研 OrTTS 支持通过 ALSA 边合成边播放。安装包不含模型权重。

## 环境准备

需要 Python 3.10+、Tk、ALSA 播放工具与中文字体（使用语音识别加载非 16kHz 单声道 WAV 音频时还需 `ffmpeg`，使用 Kokoro / Piper / Kitten 时需系统 eSpeak NG）。Debian / Ubuntu 可执行：

```sh
sudo apt install python3-tk alsa-utils fonts-noto-cjk ffmpeg espeak-ng libespeak-ng1
```

## 启动

文件夹包内直接运行：

```sh
./ortts
```

或从仓库根目录以源码方式启动：

```sh
python3 -m linux.app --library /path/to/libortts.so
```

## 使用提示

1. 默认选择 **0.6B Q4 / P3**，可在线下载或导入本地完整模型目录；下载中断后选择同一目录可断点续传。
2. 顶部可切换 **OrTTS 合成**、**其他语音合成** 与 **语音识别**（按随包 `libortts.so` 能力自动展示）。
3. 音频设备异常时，可通过 `--audio-device DEVICE` 指定 ALSA 设备（`--audio-device null` 可用于无声环境验证）。
4. 用户设置与输出音频默认保存在 `~/.local/share/ortts-desktop/`，也可用 `--state-dir PATH` 自定义。

构建与自动化测试说明见 [开发与代理说明](AGENT_README.md)。
