# 模型文件

模型仓库：[OrTTS-Qwen3-LFM-0.6B](https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B)。

Android 应用支持三种准备方式：

- 从模型清单地址下载文件并校验。
- 通过系统文件选择器导入本地权重 ZIP。
- 调试版本携带 `model.zip`，首次运行解包。

下载清单包含文件相对路径、长度、SHA256 和文件源地址。默认使用 ModelScope，可改为其他 HTTP／HTTPS 文件源。新模型校验完成后才启用。

本地 ZIP 使用相同清单，命名为 `model.json`，并包含清单列出的文件。模型与运行时代码分开分发。

P3/P5 共用主干与音频解码器，P3 额外加载三层预测器。`voices/female.f32` 和 `voices/male.f32` 为预设音色。原生调用示例见根目录的 `assets-*.native.json`。
