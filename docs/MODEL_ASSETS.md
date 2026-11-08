# 模型资产

Android内置两个ModelScope清单：

- [0.6B v0.3.1-preview](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B/resolve/v0.3.1-preview/DOWNLOAD_MANIFEST.json)
- [1.7B v0.3.1-preview](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-1.7B/resolve/v0.3.1-preview/DOWNLOAD_MANIFEST.json)

下载器根据P3/P5选择文件，校验清单和文件SHA；同版本共用权重只保留一份，已安装模型可在尺寸之间切换。四个音色来自各模型自身的说话人向量：0.6B为1024维，1.7B为2048维，不混用。

P3需要`P3/predictor/predictor.gguf`及自身配置，P5使用基座内的原生预测器。新版声学端由清单自动选择LiquidCodec；旧LFM包继续支持。详细格式见[模型包合同](model-pack-runtime.md)。

ZIP导入使用`model.json`清单，包含其中登记的全部文件；不需要另外复制一份Python浮点预测器。模型权重不放入GitHub源码仓库。

## iOS 与 macOS

iOS 自研 Demo 默认固定 v0.3.1-preview LiquidCodec，另有 v0.2.0-preview LFM 兼容入口，分别存放 `models-liquid/` 与 `models/`。两者校验各自内置清单 SHA256，再逐文件校验大小、SHA256。原生模型文件夹导入必须包含匹配的固定清单，逐文件校验后复制，已有相同文件复用，内容冲突明确报错；不支持 Android ZIP 或自定义下载源。LiquidCodec 使用清单绑定的 dequant 身份，不能传旧 bridge SHA。

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

新模型包可声明声学解码器，由运行时自动选择；格式与兼容构建见 [解码器支持](DECODERS.md)。当前发布 APK 的能力以其发行说明为准。
