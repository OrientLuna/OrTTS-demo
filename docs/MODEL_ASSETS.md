# 模型文件

模型仓库：[OrTTS-Qwen3-LFM-0.6B](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B)。

Android 应用支持三种准备方式：

- 从模型清单地址下载文件并校验。
- 通过系统文件选择器导入本地权重 ZIP。
- 调试版本携带 `model.zip`，首次运行解包。

下载清单包含文件相对路径、长度、SHA256 和文件源地址。默认使用 ModelScope，可改为其他 HTTP／HTTPS 文件源。新模型校验完成后才启用。

本地 ZIP 使用相同清单，命名为 `model.json`，并包含清单列出的文件。模型与运行时代码分开分发。

P3/P5 共用主干与音频解码器，P3 额外加载三层预测器。`voices/female.f32` 和 `voices/male.f32` 为预设音色。原生配置示例见 [`models/qwen3-lfm-0.6b/`](../models/qwen3-lfm-0.6b/)，下载包包含 `assets-p3.native.json` / `assets-p5.native.json`。

## iOS 与 macOS

iOS Demo 固定下载 v0.2.0-preview 清单并校验内置清单SHA256，再逐文件校验大小、SHA256；支持原生模型文件夹导入，不支持 Android ZIP 或自定义下载源。导入后需点“下载 / 检查所选模型”补齐、校验，已有同名子目录不覆盖。

macOS CLI / C ABI 不负责下载；需在调用前准备并验证原生模型目录：

```text
MODEL_ROOT/
  native/
    model.gguf
    bridge/MANIFEST.json
    bridge/…
    tokenizer-b260k-MIXED_Q4_0.gguf
    tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf
    vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf
  voices/female.f32
  voices/male.f32
  P3/predictor/…
```

完整文件列表以可信下载清单为准，不能只下载上述几个 GGUF。P3 需要额外 predictor 文件。传给引擎的 `bridge_manifest_sha256` 应来自已验证模型清单，不能把任意本地文件计算出的SHA当成信任来源。当前 v0.2.0-preview 值为 `a4202fc2d5ba0352cd847b02e83fd7382b0a2ba54e3e3aefdc4c82c7aa068228`，其他版本应重新核对。
