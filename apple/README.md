# Apple CPU Demo

macOS 提供命令行原型，iOS 提供 UIKit Demo。CPU 编译档位、兼容要求及性能口径见 [平台优化参数](../docs/CPU_PROFILES.md)。

## iOS 使用

底部“中文合成”“多模型合成”“语音识别”分别进入自研 TTS、Kokoro / Kitten / Piper / PocketTTS 和 SenseVoice / Moonshine。识别页面点击模型名称切换模型，选择后下载校验；支持文件夹导入、音频文件/录音输入、识别上次合成、停止和重播。详见 [多模型 Demo](../docs/MOBILE_SPEECH_DEMO.md)。底部原有自研模型页面继续提供以下功能。

默认选择 LiquidCodec v0.3.1-preview，支持 P3/P5 与四个固定音色，P3 首次约1.81GB。可切到“LFM · 旧版兼容”使用 v0.2.0-preview 与原有男女声。两者分别放在 `models-liquid/`、`models/`，保留旧包，不静默替换解码器。下载及导入均检查各自固定清单 SHA256、文件大小和 SHA256；LiquidCodec 将已校验的 dequant 清单身份传给运行时，不沿用旧 bridge SHA。进度按文件计数，已校验文件跳过，未完成的大文件重新下载，请保持前台。

可导入包含 `native/`、`voices/`、可选 `P3/` 的原生模型文件夹，再检查补齐；不支持ZIP，不覆盖已有同名子目录。输入后点击“合成并播放”，先缓冲约480ms音频，再边生成边播放。停止清空播放队列并在生成块边界取消。成功结果保存到应用 `Documents/ortts-output.caf`，可重播及通过文件共享获取。键盘工具栏“完成”、点击外部、滑动页面均可收起键盘。

## 安装与构建

完整命令统一见 [构建说明 / Apple](../docs/BUILD.md#apple)，优化版参数见 [CPU 档位](../docs/CPU_PROFILES.md)。iOS 真机需使用自己的开发证书和覆盖设备、Bundle ID 的描述文件，并签名嵌入框架。当前没有公开 IPA、TestFlight 或 App Store 版本。

## macOS 使用

macOS 为离线 CLI，构建后运行：

```sh
build/apple-mac/ortts-apple /path/to/native-model-pack P3 TRUSTED_BRIDGE_SHA '你好。'
afplay ~/Documents/ortts-output.caf
```

模型需手动准备，目录和可信 SHA 来源见 [模型说明](../docs/MODEL_ASSETS.md)。没有图形界面、签名公证 DMG 或模型自动下载。

## 验证

iOS 真机和模拟器均编译通过。iOS Scene 生命周期、键盘收起功能已接入；模拟器验证了真实P3合成、音频文件、流播放启动/排空、播放中取消、缺失小文件下载补齐及全量校验。iPhone 17 实测见 [基准数据](../benchmarks/iphone17-cpu.json)。未验证全部文件选择器交互、真机音频中断、所有设备、长文EOS或音质。

显式开发启动参数：`--synthesis-smoke`、`--download-smoke`、`--cancel-stream-smoke`；文本与选择可用 `--benchmark-text TEXT`、`--benchmark-p5`、`--benchmark-male`。普通启动不自动下载或合成。性能日志不代表真实声学起播延迟。
