# Kokoro 内存定位与语音框架兼容性增补

> 后续集成更正：首次PL-BERT候选在取消后复用时暴露固定位置/类型输入被graph allocator复用的问题。当前补丁已将这两组持久输入标记为输出保护，并增加同配置eager A/B、取消/复用与真实C/Rust验收。历史统计保留为当时结果；交付状态以[多模型SDK](../../runtime/SPEECH.md)及`vendor/speech/`锁文件为准。

2026-11-07，M5 MacBook Air 24GB、CPU四线程。延续第一轮 `multi-model-local-validation-2026-11-07.md`。本轮使用独立源副本 `_work/compat-profile-runtime`，未修改原已准备源树或OrTavern。证据：`benchmarks/kokoro-memory-and-extra-models-20261107.json`；所有改法仅认证本机CPU，不认证Metal/CUDA/iOS/Android。

## 1. 定位结果

此前Kokoro英语约1618MB、中文混合文本约2094MB的峰值，不是190MB模型文件的简单放大，也不是已证明的泄漏。分配探针实际记录：

| 分配点 | 申请字节 | 解释 |
|---|---:|---|
| 权重backend buffer | 约281.6MiB | Q8包内并非所有算子都以Q8执行，卷积等保留相应类型；模型文件还包含音色/资源 |
| PL-BERT context tensors | 243,835,680 | `ggml_backend_alloc_ctx_tensors` 为上下文中间张量分配，未利用完整图的生命周期复用 |
| predictor duration | 80,047,904 | 同类上下文张量分配 |
| predictor text | 28,799,424 | 同类上下文张量分配 |
| shared LSTM两方向 | 各4,785,408 | 状态和块内中间张量 |
| predictor tail | 248,245,248 | 含F0、噪声和decoder features的联合图 |
| generator graph allocator | 259,435,968 | 已使用gallocr，但图本身仍有巨大中间张量 |
| 最大generator节点 | 185,185,792 | CUSTOM，shape=1408×32881，结合 `decoder.cpp` 卷积展开路径定位为重点检查对象 |
| CPU临时工作区 | 最大观测11,608,320 | 相比上述图张量小，不是主要来源 |

这些分配有生命周期重叠，也有释放/缓存，不可全部机械相加当作峰值。`ggml_init`元数据arena容量、模型映射、物理footprint、RSS是不同指标。此前只调小predictor图metadata arena的实验没有降低峰值，不能据此排除真正的激活缓冲。

## 2. 试验与接受边界

### 已拒绝的全面复用方案

对PL-BERT及所有predictor阶段改用按图存活期复用，峰值约950MB，但固定seed波形变化：最大绝对差约0.484、相关性约0.126。即使音频长度相同也不能接受。可能涉及后续阶段的自定义算子、视图别名或跨调用状态生存期；本轮未证明具体破坏点。该方案不作为迁移补丁。

### 保留的最小候选

仅把PL-BERT的中间张量分配改为gallocr，并显式标记输出、同步修改异常路径和析构释放。可审查补丁：`tools/compatibility/kokoro-plbert-liveness.patch`。它不改模型、精度、采样或文本前端。

英语相同文本的ABBA单进程对照，每项重新启动、seed42、CPU4线程：

| 顺序 | 版本 | 峰值physical footprint（CLI MB） | API ms | WAV |
|---|---|---:|---:|---|
| A | 原版 | 1617 | 3095.27 | 同一哈希 |
| B | 仅PL-BERT复用 | 1386 | 3238.63 | 同一哈希 |
| B | 仅PL-BERT复用 | 1386 | 3373.02 | 同一哈希 |
| A | 原版 | 1617 | 3562.98 | 同一哈希 |

此组内存降低约14.3%，没有证明提速。其他单次候选观察到1279–1406MB，说明分配器/物理页状态会影响具体数字，不选最低一次宣传。

中文混合文本从之前2094MB到本轮1646MB，WAV哈希完全一致，约21.4%降低；不是ABBA重复组，只算单次补充证据。英语男声、中文三块流式也与原版WAV逐字节一致。同一session按“短句→长句→短句”的3请求批处理，每项与原版批处理哈希一致，覆盖不同输入形状和缓存重建。

**仍然偏大。** 1.4–1.6GB不能当移动端问题已解决。进一步方向：generator的卷积展开中间张量、tail阶段状态/别名合同、组件缓存预算、已存在但未在本轮启用的NEON generator。不能直接把不通过数值回归的全图复用补丁带入App。

## 3. 新增本机模型验证

资产固定在维护者仓库 `audio-cpp/audio.cpp-gguf` @57de533382ad47d5527e7562d1f80c41f769553b，尺寸和SHA见 `tools/compatibility/extra-assets.json`。

| 模型 | 资产 | 本机结果 | 边界 |
|---|---|---|---|
| KittenTTS Mini0.8 | orig GGUF，302,167,648B，8英语音色 | Leo音色7.567s音频，API2.934s，footprint1056MB，24kHz mono、finite | 未人工听评；不能用“mini”推断小内存，不代表KittenTTS2或所有音色 |
| Moonshine Streaming Tiny | Q8_0 GGUF，60,409,088B | 离线识别5.817s英语音频，API40.95ms，footprint116MB；分块模式最终文本一致 | 仅一条合成语音，无准确率语料；不能外推中文或模型全族 |

Kitten试听：`outputs/memory-2026-11-07/kitten-en.wav`，文本与第一轮Piper/Kokoro英语相同。Moonshine转录：

> The northern wind crossed the quiet harbor at 9:30. Please check the train ticket and call the station.

**特别修正流式标签：** 固定源的 `src/models/moonshine_asr/session.cpp::process_audio_chunk` 只累积到 `streaming_audio_`，`finalize`才转录，feed事件不包含partial识别。因此本次通过的是“接受分块、最终输出”的buffered模式；既不是有状态在线partial，也没有证明长时间输入内存有界。模型名字中的Streaming不代表这个adapter已经采用模型的增量缓存方案。

## 4. 框架与模型必须分开描述

OrTTS能承接某框架产出的**已实现模型版本**，不等于可以执行框架中任意模型/计算图。下面每一项都需要模型专用前后处理、导出资产和质量验证；不将框架名、GGUF扩展名或平台宏作为支持证据。

| 框架 / 生态 | 当前可以复用或验证的路径 | 支持等级与建议 |
|---|---|---|
| audio.cpp / ggml | Kokoro、Piper、SenseVoice已在同一库运行；本轮另构建Kitten/Moonshine | 继续作为单底层候选，按family裁剪。5个第三方family有本机smoke，不宣称全平台 |
| Sherpa / ONNX Runtime | 现用Kokoro/VITS/SenseVoice/Zipformer及已有C接口 | 保留同模型质量基线和未移植能力；Kokoro103音色及现用中文流Zipformer不能用别的包替代 |
| FunASR / SenseVoice生态 | SenseVoice有原生ggml路径；中文ASR/VAD/标点是多个组件 | 能执行已实现SenseVoice，不是兼容全部FunASR AutoModel或所有在线Paraformer。[1] |
| Whisper / whisper.cpp | 成熟独立ggml执行器，有Apple/Android示例与各平台构建入口 | 可做ASR候选；不能直接把其不同ggml版本再静态链接进现库。窗口转录不等价原生在线识别。[2] |
| NeMo / Parakeet | audio.cpp固定源有Parakeet TDT loader/runtime与文档；官方NeMo是模型训练/推理生态 | 代码存在，未在本轮运行；TDT/RNNT、tokenizer、模型版本、窗口与cache模式要分别验证。[3] |
| WeNet / icefall / Zipformer | Sherpa有相关专用执行路线；audio.cpp有特定Kroko Zipformer2移植 | 不认证任意WeNet U2或宿主zh-en Zipformer包可导入ggml；需具体checkpoint级验证。[4] |
| CosyVoice3 | 固定audio.cpp有 `cosyvoice3` GGUF loader和clone/instruction路径 | 有完整代码入口，未下载/执行其大模型；reference audio、文字、flow及codec是独立合同，不能只换权重。[5] |
| F5-TTS | 固定audio.cpp有原生DiT/flow/Vocos流水线，文档标M4 | 源码与作者验证存在，本机未验；还要检查模型许可，官方代码MIT但预训练权重有NC限制，不能按代码许可直接发布资产。[6] |
| PocketTTS / Supertonic | audio.cpp固定树有模型专用实现/规格，作者原框架也有端侧路线 | 按具体模型与许可评估；未安装新原生框架、未执行大资产，不因上游标支持就加入默认SDK。[7] |
| MLX / Core ML / FluidAudio | Apple平台有Kokoro/ASR具体实现 | 可选设备优化执行器，不是统一跨Android/Linux/Windows的底座；原生运行库和资源增加需实测，不保证ANE整图执行。[8] |
| ncnn / sherpa-ncnn | 独立的在线ASR路径，Sherpa-ncnn作者提供多平台接线 | 是实际可选ASR底层，但不是Sherpa-ONNX模型通用加载器；只有特定需求显著改善才引入第三数值底层。[9] |
| MNN | 通用端侧图/模型运行时及模型部署能力 | 可转换不等于完整TTS/ASR前后处理已支持；本轮没有其模型级或设备级验收，不作为零成本替换承诺。[10] |

本轮实际执行都在macOS ARM64 CPU；iOS/Android这五个第三方family的部署、听感、内存压力与取消尚未验收。Linux/Windows也不继承本机成绩。此前自研P3/P5的真机成绩只覆盖相应自研资产链。

## 5. 下一步优先级

1. 先让人工试听确认Piper/Kokoro/Kitten的实际发音质量；保留模型/音色版本，不用ASR回读代替听感。
2. CPU候选只保留通过哈希回归的PL-BERT补丁；在更多长度、音色、循环请求和移动端验证前，不并入默认发布源。
3. 继续定位generator展开与tail状态问题，同时给模型缓存、队列及并发设置预算，不用“统一底层”掩盖模型自己的峰值。
4. SenseVoice的NoSpeech/WholeInput/Segments歧义仍是独立阻塞；Moonshine adapter的全量累积也需要显式能力标注，不当作在线partial接口。
5. 优先为已验5个family建立候选能力表，而不是扩大到全部模型。大型CosyVoice/F5/Parakeet需要下一次明确资产选择与预算，避免一次拉取全部权重。

## 官方来源

以下访问日期2026-11-07；移动main/master路径不替代模型资产pin，源码存在与本机验证在上表分开标注。

1. [FunASR](https://github.com/modelscope/FunASR)。
2. [whisper.cpp](https://github.com/ggml-org/whisper.cpp)。
3. [NeMo Speech](https://github.com/NVIDIA-NeMo/Speech)；固定源 `docs/models/parakeet_tdt.md`。
4. [WeNet](https://github.com/wenet-e2e/wenet)；前轮报告中的Sherpa/Kroko固定资产边界。
5. [CosyVoice](https://github.com/QwenAudio/CosyVoice)；[audio.cpp CosyVoice3实现说明](https://github.com/0xShug0/audio.cpp/blob/main/docs/models/cosyvoice3.md)。
6. [F5-TTS及许可](https://github.com/SWivid/F5-TTS#license)；[audio.cpp F5移植](https://github.com/0xShug0/audio.cpp/blob/main/docs/models/f5_tts.md)。
7. [PocketTTS](https://github.com/kyutai-labs/pocket-tts)、[Supertonic归档仓库](https://github.com/supertone-oss-archive/supertonic)。归档项目状态不外推到后续模型版本。
8. [FluidAudio](https://github.com/FluidInference/FluidAudio)、[KokoroSwift](https://github.com/mlalma/kokoro-ios)。
9. [Sherpa-ncnn](https://github.com/k2-fsa/sherpa-ncnn)、[ncnn](https://github.com/Tencent/ncnn)。
10. [MNN](https://github.com/alibaba/MNN)。
11. [KittenTTS原作者](https://github.com/KittenML/KittenTTS)、[audio.cpp Kitten模型说明](https://github.com/0xShug0/audio.cpp/blob/main/docs/models/kitten_tts.md)。
12. [Moonshine原作者](https://github.com/moonshine-ai/moonshine)、[audio.cpp Moonshine adapter](https://github.com/0xShug0/audio.cpp/blob/main/src/models/moonshine_asr/session.cpp)。流式实现结论来自本机固定base的上述函数，不泛化为原作者模型没有流式能力。
