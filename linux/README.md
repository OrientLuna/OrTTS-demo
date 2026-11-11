# OrTTS Linux 桌面 Demo

本地语音合成，支持模型下载、导入、边合成边播放，以及保存 WAV。安装包不含模型。

## 启动

文件夹包中运行：

```sh
./ortts
```

需要 Python 3.10+、Tk、ALSA 播放工具和中文字体。Debian/Ubuntu 通常安装
`python3-tk alsa-utils fonts-noto-cjk`，原生库也需匹配你的发行版与 CPU。
当前文件夹包不是通用 AppImage 或 `.deb`；构建机产物不保证能直接运行于旧版 Ubuntu。

源码启动（仓库根目录）：

```sh
python3 -m linux.app --library /path/to/libortts.so
```

## 使用

1. 默认选择 **0.6B Q4 / P3**，下载模型或导入完整模型文件夹。
2. 校验完成后选择音色、输入文字，点击“合成语音”，默认边生成边播放。
3. 可停止、重播或保存 WAV；“释放模型”可回收占用，下次合成会重新加载。

下载中断后选择同一位置继续。若 Hugging Face 拒绝访问，可改用 ModelScope。
更多共用操作见[桌面使用说明](../desktop/README.md)。

声音设备有问题时，可用 `--audio-device DEVICE` 指定 ALSA 设备；即使无法播放，仍可保存音频。
`--audio-device null` 是无声测试，不会从扬声器发声。

设置和音频默认保存在 `~/.local/share/ortts-desktop/`（遵循 XDG 配置），
也可用 `--state-dir /path/to/settings` 指定位置。

文件夹包构建、依赖审计和自动化测试见 [开发与代理说明](AGENT_README.md)。
