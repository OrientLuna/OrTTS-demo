# OrTTS Android Demo 0.2.3-preview

本地语音合成，支持 P3／P5 与 female／male 两个音色。

- 默认边生成边播放，根据生成速度调整初始缓冲。
- 按所选模型下载，共享文件只下载一次；支持本地权重 ZIP。
- 无需额外存储权限，正常卸载会清理应用内模型与音频。

需要 Android 9+、支持 DotProd／I8MM／FP16 的 ARM64 CPU。本版 APK 已在荣耀90 Pro 验证；OPPO Find N5 已完成原生 CPU 性能测试，APK 验证待补。

安装包不包含权重：P5约2.0GB，P3约2.2GB。首次加载较慢；长句的缓冲时间因设备而异。

模型：https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B
