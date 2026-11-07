# ggml 增量 ASR SDK、验证与 FunASR 边界

日期：2026-11-07。Sherpa 集成暂停；本轮不增加第二个推理框架、不下载模型、不修改 OrTavern。

## 后续已完成：可用 SDK 接线

此前独立探针已经推进到同一 `libortts` / `OrTTS.framework` 内的独立流式 API：`ortts_asr_stream_*`，Rust 为 `speech::streaming::Stream`。原 `ortts_asr_*` 不改语义。没有增加 Sherpa/ORT，也没有第二份 ggml。完整调用合同与默认值见 [SDK说明](../../runtime/SPEECH.md#moonshine-增量-asr)。

已实现可修订 partial、带segment/revision的final、显式flush、能量静音/硬上限分段、reset、跨线程取消及状态统计。编码器采用有界上下文重叠计算，段内编码结果复用；解码器因新增cross-memory仍重算假设，**不宣称逐层KV缓存完全实现**。F16作为已筛查路径固定用于编码器，权重来自已有Q8包展开，保留其额外内存成本。Native Q8增量未通过筛查，不暴露该模式供宿主误用。

当前验收证据：

- [SDK状态与内存](../../benchmarks/asr-stream-sdk-20261107.json)：任意分块（包括单sample）、partial在finish前产生、flush幂等、NaN/空/超大输入事务性拒绝、低能量非零静音不推理、取消保持到reset、回调及跨线程取消、reset后结果复用、两会话交错。Rust回调panic被捕获，不跨FFI展开；跨线程取消token在句柄释放后安全失效，不保活模型。
- 两个独立进程分别加速回放302.744秒语音：4秒段长上限产生75次限长final，默认15秒上限产生20次；均通过状态上限与预热后RSS平台检查。默认15秒的RSS约228–230MiB（波动约2MiB），已缓存编码峰值750帧；两种设置原始PCM峰值均43840帧。4秒设置整段回放约13.6s（RTF约0.045），15秒约32.5s（RTF约0.107），体现重复解码成本。**这不是五分钟真实麦克风、真人录音或热稳定性认证。**
- [固定音色与自然长句](../../benchmarks/asr-stream-quality-20261107.json)：Kokoro heart/adam、Pocket anna及13.04秒Pocket alba自然三句话，归一化WER均为0；三个final逐字同匹配精度的offline，anna只有标点区别。当前阈值、数值及事件时间线均保存在JSON，不将这些合成样本等同真人语料准确率。
- macOS实际执行；iOS ARM64/Android ARM64完成交叉构建与接口检查，Swift导入通过。新的流式模型未在手机运行，Linux/Windows未做本轮执行认证。

本机产物位于 `build/speech-incremental-macos/install/lib/libortts.dylib`、`build/speech-incremental-ios/install/OrTTS.framework` 和 `build/speech-incremental-android/install/lib/libortts.so`，不随Git提交。Android安装库strip，保留16KiB LOAD对齐；平台检查见 `benchmarks/asr-stream-platforms-20261107.json`。

同机独立进程的加速回放成本如下。CPU秒为user+system累计，不等同功耗或电量；所有数值是一次采样，输入为重复合成语音。

| 段长上限 | 输入时长 | 回放计算耗时 | 计算RTF | CPU秒 | 预热后RSS |
|---|---:|---:|---:|---:|---:|
| 4s | 302.744s | 13.57s | 0.045 | 42.86 | 222–232MiB |
| 15s（默认） | 302.744s | 32.46s | 0.107 | 108.96 | 228–230MiB |

60.4MB（57.6MiB）的GGUF并不等于总RSS：本轮还持有F16展开的编码权重、原生解码权重、tokenizer、段内编码输出和推理工作区。进程内多个流式句柄会各自加载这些对象；没有将五个句柄压力测试的总RSS冒充单引擎内存。更小的段长能降低重复解码成本，但硬限长可能切断词，宿主应优先在有效语音结束处flush。

复现（仅使用已有资产，不下载）：

```sh
python3 tools/test_asr_stream.py --build build/speech-incremental-macos \
  --model local/compat/assets/Moonshine-Streaming-GGUF/moonshine-streaming-tiny-q8_0.gguf \
  --input outputs/unified-2026-11-07/shared-whisper-input.f32 \
  --out outputs/asr-stream-2026-11-07/acceptance
python3 tools/compatibility/check_asr_stream_quality.py \
  --library build/speech-incremental-macos/install/lib/libortts.dylib \
  --model local/compat/assets/Moonshine-Streaming-GGUF/moonshine-streaming-tiny-q8_0.gguf
python3 tools/check_asr_stream_platforms.py
```

自然长句WAV由已有Pocket alba权重、CPU4、seed42生成；文本在质量脚本的 `LONG` 常量中。脚本依赖ffmpeg进行显式16kHz mono转换，已有固定音色WAV不随Git提交。缺失资产时应明确失败，不隐式下载。原有 `test_speech.py` 校验模型包使用Python3.11+（本机用Python3.12），Apple系统Python3.9不支持其 `hashlib.file_digest`。

后续优化与未覆盖范围：逐层KV/卷积缓存、decoder图与cross-memory增量投影、真人/噪声语料和手机热/功耗验收；这些是进一步优化，当前交付采用明确的有界重算策略。中文仍用SenseVoice离线路径；Paraformer-streaming移植尚未实施。不能删除宿主已有真流式中文或全双工路线，全库仍是BUSY互斥调度。

## 初始探针与数值筛查记录


ggml 可以承载增量 ASR，但需要模型流水线实现跨块状态。现有 Moonshine streaming 权重并不等于已有在线执行器：锁定源码的 `process_audio_chunk()` 只追加 PCM，`finalize()` 才创建整句编码图。原 `ortts_asr_*` C/Rust ABI 仍是 buffered-final；后续新增的独立增量API见上节。

本轮增加可复现的 **Moonshine bounded-overlap 编码器实验**。只重新计算局部上下文窗口，保留已提交的编码结果，接收新音频时产生可修订文本；解码器仍在每次更新时从头解码。它证明“无需增加 ONNX 执行器也可以在讲话中途出字”，尚不构成完整的缓存流式 SDK。

工具：`tools/compatibility/build_moonshine_incremental.py`、`moonshine_incremental_probe.cpp`、`check_moonshine_incremental.py`。这些工具生成独立数值探针；后续vendor增量执行器复用已验证的绝对位置偏移，SDK接线见上节。构建器核验 runtime.cpp SHA，复用现有静态库并记录其 SHA、编译器和二进制 SHA。`nm` 验证只有一份已定义的 `ggml_init`。

## 实验方法

设备为本机 M5 MacBook Air 24GB，macOS ARM64，CPU4，使用现有 ggml/Accelerate 构建。权重为已下载 Moonshine streaming tiny Q8；编码器分别保留 Native Q8 或在加载时展开成 F16/F32，解码器保持原配置。**F16/F32 展开都会增加权重内存，不恢复量化前的信息；它们是验证候选，尚不是移动端推荐配置。**

两个 stride=2 的因果卷积将 80-sample 帧下采样到每帧 320 samples。局部注意力各层的过去/未来感受野累加，加上卷积历史，确定窗口与提交延迟；窗口起点按 320 samples 对齐，解码器位置嵌入使用绝对编码帧偏移。已提交区域不再编码。此方法仍有固定重叠计算，尚未复用逐层 KV 和卷积缓存。

对照是同一进程、同一权重配置的整句编码与同一 greedy decoder；不是上游 PyTorch 对齐。逐帧比较编码向量并比较最终文本。探索后设定 relative L2 < 5e-4 的筛查阈值，再验证不同分块和长样例；这不是 bitwise parity，更不是语料级准确率认证。

## 本机结果

原始记录：[Moonshine 实验 JSON](../../benchmarks/moonshine-incremental-20261107.json)。下表耗时以原始 JSON 为准，RTF 仅含增量编码与重复解码；不含加载、输入读取或实际等待麦克风，单次采样不能作为设备功耗结论。

| 输入 / 分块 | 编码存储 | 编码 relative L2 | 最终文本同离线 | 筛查 |
|---|---|---:|---|---|
| 英文 3.692s / 100ms | F32 | 0.00010612 | 是 | 通过 |
| 同上 / 400ms | F32 | 0.00010558 | 是 | 通过 |
| 同上 / 1000ms | F32 | 0.00008350 | 是 | 通过 |
| 重复语音加静音 27.998s / 7777 samples | F32 | 0.00012055 | 是 | 通过 |
| 英文 3.692s / 400ms | F16 | 0.00011001 | 是 | 通过 |
| 重复语音 27.998s / 7777 samples | F16 | 0.00011951 | 是 | 通过 |
| 英文 3.692s / 400ms | Native Q8 | 0.00061839 | 是 | **未通过** |

长样例来自同一短句重复并加静音，末尾刻意不对齐；它是长度/边界压力测试，不是自然长句准确率测试。原始音频 ring 最大 45529 samples（约 2.85s、178KiB），受感受野和输入块大小约束，不随录音长度线性增长。

**不能将 ring 有界等同整个引擎内存有界。** 当前探针仍保留完整对照音频、对照编码结果、累计增量编码结果，每次解码还会重新建立 cross-attention/decoder 图。进程峰值 RSS 包含全部这些对象，不能当作流式会话独立内存。输入硬限制 30s；生产 SDK 原有离线输入上限不变，新增增量接口按segment上限约束。100ms 更新重复工作明显更多，长样例解码时间远高于编码时间，下一步应优先优化解码状态。

负例检查：NaN、过短输入和非 F32 对齐字节均拒绝。初始探针未验证自动endpoint、取消/重置、两会话交错和长时间内存；后续SDK状态/内存验收见上节。稳定前缀与手机执行仍未认证。首个 400ms 更新曾输出错误的 `Okay`；此处只是有 partial，不是有效首字延迟指标。

### 复现

已有模型、源码与 `build/speech-macos-final` 的前提下，在仓库根运行，无隐式下载：

```sh
python3 tools/compatibility/build_moonshine_incremental.py
python3 tools/compatibility/check_moonshine_incremental.py
```

后者会覆盖对应实验 JSON。退出 0 表示 F16/F32 筛查和 ring/负例检查通过；Q8 失败仍如实保存在报告中，不表示全模式通过。当前工具针对 macOS ARM64 已验证，不是跨平台构建入口。

## FunASR 能不能用

**能用，而且中文值得优先研究；必须选择具体模型和执行路径。** FunASR 是工具集，不能整体等同某个 ASR 模型或 ggml 执行器。

本次锁定官方提交 `efe5504e388613e5298e1f93d5ca9f861700b489`，提交时间 2026-11-07T04:45:43Z；记录见 [源码审查 JSON](../../benchmarks/funasr-source-audit-20261107.json)。以下都是源码/文档证据，**没有在本机下载或运行新的 FunASR 模型**。

| 路线 | 已有能力与证据 | 对当前 OrTTS 的意义 |
|---|---|---|
| SenseVoice Small | 已接入本项目 ggml 的离线识别 | 保留中文基线；不是在线缓存模型 |
| Paraformer-streaming | [官方实现](https://github.com/modelscope/FunASR/blob/efe5504e388613e5298e1f93d5ca9f861700b489/funasr/models/paraformer_streaming/model.py)含 `encode_chunk`、encoder/decoder/predictor cache 与 final chunk 处理 | 可作为中文真流式参考基线；尚未移植到本项目 ggml |
| Paraformer 原生 ggml | [官方 C++](https://github.com/modelscope/FunASR/blob/efe5504e388613e5298e1f93d5ca9f861700b489/runtime/llama.cpp/paraformer/funasr-paraformer/funasr-paraformer.cpp)已有 SAN-M、CIF、decoder 执行 | 具备可复用代码；当前入口读取文件，再对整段/VAD 分段调用完整流水线，不是在线 streaming cache |
| Fun-ASR-Nano 原生 | [官方原生说明](https://github.com/modelscope/FunASR/blob/efe5504e388613e5298e1f93d5ca9f861700b489/runtime/llama.cpp/README.md)采用 ggml 声学编码器和 llama Qwen 解码器 | 可扩展候选，但会增加 llama 层及更多权重；不是优先解决低延迟手机 ASR 的小切片 |

原生 Paraformer 的具体接入问题：

- 官方入口是 CLI，不是可直接替换的会话库。每段重建图/backend，线程数写死为 8；需改为共享权重、宿主线程配置和会话生命周期。
- `compute_fbank()` 对极短输入的帧数/`feat[0]` 路径需要边界保护；不能把麦克风小块直接送入这个离线函数。
- CIF `integrate/frame` 是每段局部变量，缺少跨调用的残余质量与声学向量；移植流式时不能每块清零。
- 卷积、SAN-M/FSMN、位置编码、fbank/LFR 的尾部与上下文状态都要与在线检查点对齐；仅增加 `cache` 容器不够。
- 官方 [CMake](https://github.com/modelscope/FunASR/blob/efe5504e388613e5298e1f93d5ca9f861700b489/runtime/llama.cpp/CMakeLists.txt)会获取另一份固定 llama.cpp/ggml。若共用 OrTTS 底层，需要验证算子/API 与数值后再只链接现有 ggml；直接加子目录不算依赖合并。源码中的 1/2GiB ggml context 参数也不能直接当作设备实际 RSS。

许可方面，该提交的 [工具集 LICENSE 是 MIT](https://github.com/modelscope/FunASR/blob/efe5504e388613e5298e1f93d5ca9f861700b489/LICENSE)。模型权重按各自模型卡与其引用的协议审查；部分采用 FunASR Model Open Source License，不能从代码 MIT 推出全部权重 MIT。完整开源发行也不会取消权重条款。这不是“FunASR 不能用”的理由，而是应固定检查点与许可证据。

## 后续实施顺序

1. **已完成可用路径：** F16编码器策略、独立流式API、自然长句/不同音色对照、状态与有界内存测试。Q8增量未通过，不通过放宽阈值直接放行。
2. **缓存：** 将实验中的局部重叠编码替换为逐层 KV/卷积状态；解码需处理新增 cross-memory 与可能修订的 token，不能盲目复用旧 self-KV。先做有界 utterance，再以 endpoint 切段。
3. **已完成 ASR 独立事件 API：** 版本检查、可修订partial、final、endpoint reason、flush/reset、取消及段长上限。稳定token、神经VAD等未实现能力不宣称支持；原buffered-final ABI语义保留。
4. **中文真流式：** 以固定版本 Paraformer-streaming 为基线，先核许可/资产，再验证前端、SAN-M、CIF 残余状态、decoder cache 的逐块对齐；复用官方原生算子但不宣称离线实现等同在线模型。
5. **真实设备门槛：** macOS 连续输入/静音/取消复用/多会话验证后，才做 iOS 与 Android 设备上的延迟、峰值内存、发热测试。没有这轮新模型的手机性能证据。
