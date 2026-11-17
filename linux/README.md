# OrTTS Linux 桌面 Demo

与 macOS 共用三标签页界面与统一主题，在 Linux 上提供本地语音合成与识别，自研 OrTTS 支持通过 ALSA 边合成边播放。安装包不含模型权重。

## 环境准备

需要 Python 3.10+、Tk、ALSA 播放工具与中文字体（使用语音识别加载非 16kHz 单声道 WAV 音频时还需 `ffmpeg`，使用 Kokoro / Piper / Kitten 时需系统 eSpeak NG）。Debian / Ubuntu 可执行：

```sh
sudo apt install python3-tk alsa-utils fonts-noto-cjk ffmpeg espeak-ng libespeak-ng1
```

## 准备与构建运行时

当前 Release 暂不提供 Linux 预编译安装包，使用前需先按[构建说明 / 桌面端](../docs/BUILD.md#桌面端macos--linux)准备运行时源码并编译出 `libortts.so`（例如在仓库根目录执行）：

```sh
python3 tools/build_engine.py --target linux-x86_64 --profile x86_64-baseline \
  --source _work/desktop-runtime --liquidcodec --speech --out build/linux-engine
```

编译完成后，动态库位于 `build/linux-engine/install/lib/libortts.so`（ARM64 Linux 请改用 `--target linux-aarch64 --profile arm64-baseline`）。

## 启动

**方式一：从仓库根目录以源码方式启动**

```sh
python3 -m linux.app --library build/linux-engine/install/lib/libortts.so
```

**方式二：组装可移动文件夹包并运行**

```sh
python3 -m linux.build --library build/linux-engine/install/lib/libortts.so --output /path/to/OrTTS-Linux
cd /path/to/OrTTS-Linux && ./ortts
```

## 使用提示

1. 默认选择 **0.6B Q4 / P3**，可在线下载或导入本地完整模型目录；下载中断后选择同一目录可断点续传。
2. 顶部可切换 **OrTTS 合成**、**其他语音合成** 与 **语音识别**（按随包 `libortts.so` 能力自动展示）。
3. 音频设备异常时，可通过 `--audio-device DEVICE` 指定 ALSA 设备（`--audio-device null` 可用于无声环境验证）。
4. 用户设置与输出音频默认保存在 `~/.local/share/ortts-desktop/`，也可用 `--state-dir PATH` 自定义。

构建与自动化测试说明见 [开发与代理说明](AGENT_README.md)。
