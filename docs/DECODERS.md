# 解码器与模型清单

P3/P5 选择生成端，声学解码器由模型包决定，两者相互独立。0.3.1 Android候选使用LiquidCodec；旧版Qwen–LFM包保留兼容，解码器由各自模型清单自动选择。

## 自动选择

下载或导入包中的 `model.json` 可以增加：

```json
{
  "runtime": {
    "schema": "ortts-runtime-v1",
    "decoder": {
      "kind": "liquidcodec",
      "variant": "base",
      "manifest": "native/liquidcodec/runtime.json"
    }
  }
}
```

这是原有下载清单的附加字段，其余 `schema`、`files`、下载地址、P3/P5 分组等保持不变。`variant` 可为 `base` 或 `expanded`。`runtime.json` 和同目录的权重必须列入 `files`、提供真实长度与 SHA256，并被所选下载分组包含。原清单没有 `runtime` 字段时继续使用 Qwen–LFM；也可显式声明 `decoder.kind` 为 `qwen_lfm`。

Android 自动识别并显示所用解码器，无需再选择一个与模型包可能冲突的开关。未知类型、缺文件、校验失败或构建未包含对应后端时明确报错，不静默改用其他模型。C ABI 不改变结构或版本；创建引擎时从安装目录读取同一份清单，既有调用方无需改参数。也兼容现有 Apple 安装器使用的 `download-manifest.json` 文件名；存在 `model.json` 时优先采用它。

模型目录仍保留已发布包的共用主干、音色、codebook/bridge 及配套绑定文件。新的解码器是额外组件，不将普通 ONNX、训练权重或任意 GGUF 当成可直接加载的运行包。下载清单与解码器 `runtime.json` 分工不同：前者负责分发和文件身份，后者绑定实际解码器文件、精度和帧接口。

LiquidCodec 的本地布局为：

```text
native/liquidcodec/
  runtime.json
  <core_file 指定的 GGUF>
  project_out.weight.f32
  project_out.bias.f32
  from_quantizer.weight.f32
  from_quantizer.bias.f32
  base/ 或 expanded/
    tensors.json
    <由 tensors.json 声明的 F32 文件>
```

`runtime.json` 使用 `ortts-liquidcodec-native-v1`，声明 `core_file`、`core_sha256`、`precision`（`F32`、`MIXED_Q8_0`或`MIXED_Q4_0`），以及 `source_RVQ_groups: 16`、`frame_samples: 1920`、`lookahead_frames: 1`。24 kHz 单声道输出，真实 EOS 后刷新前瞻与 OLA 尾部。不要通过删除尾部、归一化输出或将长度上限当 EOS 来适配格式。

## 构建可选后端

默认继续使用原有运行时和构建路径。需要 LiquidCodec 时，先按 [BUILD](BUILD.md) 准备原有 audio.cpp，再提供已在本地准备好的 [llama.cpp v0.8.0](https://github.com/ggml-org/llama.cpp/tree/v0.8.0)：

```bash
python3 tools/prepare_unified_runtime.py \
  --audio-source /path/to/prepared/audio.cpp \
  --llama-source /path/to/llama.cpp \
  --out _work/unified --release-compat

python3 tools/build_engine.py \
  --target linux-x86_64 --profile x86_64-avx2 \
  --source _work/unified/audio.cpp --out build/unified-engine \
  --liquidcodec
```

`tools/build.py` 和 `tools/build_android.py` 同样接受 `--liquidcodec`，对应 CMake 的 `ORTTS_ENABLE_LIQUIDCODEC=ON`。所有工具只使用已有源码和工具链，不下载 SDK 或模型。两种源码目录不混用；源码身份与补丁校验不通过时应重新准备。

统一构建只有一份新版 ggml，LiquidCodec 在同进程中执行。默认后端仍关闭，保留现有 Apple/Android 构建选项；启用新后端不代表所有平台都已验证。Linux ARM64 的现行 P3/P5 已完成数值和性能回归；新解码器量化音质、Android/iOS/macOS 新后端性能仍需分别验收。不要将 Linux 的 OpenMP 设置直接套到 Apple 构建或现有 APK。

开发者可运行不加载模型的清单检查：

```bash
python3 tests/check_model_pack.py --source /path/to/prepared/audio.cpp
```
