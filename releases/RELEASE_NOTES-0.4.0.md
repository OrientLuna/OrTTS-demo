# OrTTS 0.4.0 候选

本候选补齐手机 Demo 的多模型下载和 TTS/ASR 切换。正式稳定标签与签名 APK 尚未发布；不能把未签名产物当作可覆盖安装的正式版本。

- Android 新增多模型语音页面；iOS 新增“合成与识别”标签。
- PocketTTS 英语合成支持 alba、anna、george 选择与增量播放；固定回归 alba、anna。
- SenseVoice 中文/英语离线识别；Moonshine 英语增量 partial/final、结束和取消。
- 固定版本 HTTPS 下载、大小和 SHA256 校验；Android ZIP / iOS 文件夹导入；音频文件识别、录音入口及识别上次合成。
- 与原有自研模型共用 ggml。Android 直接复用 libaudiocpp.so，iOS 复用 OrTTS.framework；不新增 ONNX Runtime 或 sherpa-onnx。
- Android arm64-baseline、保留 16KiB ELF LOAD 对齐；模型权重不打包。
- 修正统一源码准备时 mtmd/探针同级文件的复制与校验，根 CMakeLists 指纹匹配锁定的 pristine llama.cpp v0.8.0 commit。

使用和验证边界见 [手机 Demo](../docs/MOBILE_SPEECH_DEMO.md)。全部模型均有独立许可，目录不代表权重自动获准再分发。Kokoro/Piper/Kitten/ZipVoice 目前仍为 SDK 能力，未列入手机菜单；无通用 ONNX/GGUF 导入。

发行前剩余事项：统一底层真机回归、原有 LiquidCodec 模型包端到端回归、交互录音验收，以及使用原 Android 发布证书签名。iPhone 开发签名产物与描述文件不会公开上传。
