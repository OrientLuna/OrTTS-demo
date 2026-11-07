# OrTTS 多模型语音运行时调研与实施建议

核对日期：2026-11-07。范围：只读工程核实、官方项目源码和发布资料；未构建新执行器、未运行新模型、未下载权重、未访问用户凭据或修改 OrTavern。性能结论除标注历史实测外均为待验证假设。

## 一页决策结论

**推荐：A 作为近期架构，B 作为有验收门槛的依赖收敛路径，C 仅用于明确收益的局部执行器。** 对多个 App 输出一个 SDK，但初期 SDK 内有 audio.cpp/ggml 和 Sherpa/ORT 两套执行器。这是统一合同和管理层，不是统一底层。只有同一发行包确实去掉某个数值运行时、重复库或重复常驻模型，才记作底层合并。

1. **“Sherpa 能力在 ggml 生态没有对应实现”不成立。** 当前锁定 audio.cpp 中已有 Kokoro、Piper/VITS、SenseVoice、Silero 和特定 Kroko Zipformer2 的原生实现。另有 whisper.cpp、SenseVoice.cpp。它们足以支持按模型收敛的实验，不足以证明能替代 Sherpa 的全部模型、语言、流式解码和平台产物。[S1–S7]
2. **OrTTS 当前不能直接使用这些能力。** 本仓库 CMake 强制只选 `qwen3_tts`；C ABI 绑定 P3/P5 和自研资产合同、24kHz mono，ASR 无入口。不能将上游具备某模型等同于 OrTTS 已接入。
3. **Kokoro 值得做小规模迁移实验，不值得马上替换现有默认。** audio.cpp 已有完整 GGUF pipeline，独立 kokoro.cpp 也有执行器；优先测试现有 audio.cpp，而非另引一份 ggml。但 OrTavern 用到的 v1.1-zh/103 音色与已核实 audio.cpp v1.0/54 音色不是等价包；G2P、字典和模型版本不一致时，迁移会改变产品能力。[S1,S8–S13]
4. **不要将中文流式 ASR 替换为“Whisper 实时窗口”或 Kroko 英文模型。** Whisper 窗口重解码、SenseVoice 缓冲分段、Zipformer 有状态流式是三种合同。Kroko 移植覆盖特定免费单语 Zipformer2，不代表支持宿主当前 zh-en 2023 Zipformer 包。[S3–S6]
5. **最先应查真正的重复依赖。** 宿主同时锁定 `sherpa-onnx 1.13.8` 和 `ort 2.0.0-rc.12`；Sherpa sys 构建列表包含 ORT、eSpeak、SentencePiece、fbank、FFT/FST。是否真的重复进包仍需最终链接图和运行库清单确认。比重写 Kokoro 更低风险的节省，可能来自按模型裁剪、去掉第二份 ORT/eSpeak 和限制线程/模型缓存。
6. **不推荐本轮全量迁移 ggml、全面转 ORT/MNN/ncnn 或默认引入 MLX/Core ML。** 前两者是流水线重实现，后者分裂平台、增加额外运行时；目前没有本工程端到端收益证据。

下一步仅批准两个独立 CLI 探针：**Piper en_US-lessac-medium 同模型 ORT vs audio.cpp**，以及 **SenseVoice-Small 同检查点 ORT vs audio.cpp**。先 macOS CPU，后 iOS、Android；通过质量、生命周期和实际体积门槛才扩展。Kokoro 的 v1.0 探针是随后可选项，不阻塞既有 v1.1-zh 服务。保留现有 ABI；不搬宿主 provider、prompt、角色、分句策略或对话编排。

## 1. 工程事实与修正

| 核实项 | 事实与源码 |
|---|---|
| 版本基线 | OrTTS HEAD `e56899ce32dabaf751af07a23d0bdfdffa4c31ad`；OrTavern HEAD `c644ac2756965a60fa745f8f813ae2376ee84b02b`，本地工作树另计。宿主旧分析是参考，不是验收证据。 |
| 上游身份 | `vendor/runtime.lock.json` 固定 audio.cpp base `e9303b76983993cc59576bf6d16d8a0635ae4d85` 与补丁；直接 `git show BASE:docs/models/kokoro_tts.md` 已确认其包含 Kokoro。联网发布页另列 v0.9.4（2026-11-05，`f7ac446`），不能自动换源或将 main 文档功能倒推到锁定版本。[S7] |
| 自研路径 | `CMakeLists.txt` 的 `AUDIOCPP_MODELS=qwen3_tts`，CPU 配置；LiquidCodec 可选 unified ggml source 有独立 receipt。新模型必须核对该 ggml pin 的算子兼容，不能照搬最新上游宏。 |
| ABI | `runtime/include/ortts_engine.h` 的 `struct_size`、ABI 1、P3/P5、1..8线程和 max_tokens<=513；`runtime/src/ortts_engine.cpp` 检查输出 24000Hz/1ch，全库 `execution_gate`，环境变量临时设/恢复。流取消在 PCM 边界，离线取消不能打断矩阵计算。 |
| Android 与 Apple | Android JNI 仍走 audiocpp API，Apple Demo 走 ortts_engine；Android JNI 的显式取消与有界音频队列不能视为已经具备。 |
| 宿主 TTS | `native/rust-core/src/tts/providers/sherpa_onnx.rs` 建 Kokoro/VITS 配置；`generate_with_config(..., None)` 未传 PCM callback；能力不等于 Sherpa 上游上限。 |
| 宿主 ASR | `asr/sherpa_local.rs` 为 SenseVoice 离线；`asr/streaming_model.rs` 指向 `sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16`，流模型由客户端壳消费。 |
| iOS 误区 | `native/rust-ffi/Cargo.toml` 在非 iOS 才启用 `local-tts`；这是宿主接线选择。已缓存 `sherpa-onnx-sys 1.13.8/build.rs` 实际有 iOS XCFramework 和移动 shared linking 分支，上游也有 iOS 构建脚本。[S14] |
| 多份 ORT | `native/Cargo.lock` 同时有 sherpa 与 Rust ort；这证明依赖入口并存，不证明最终同一 APK/IPA 装了两份。须检查启用 features、静态 archive/link map、DT_NEEDED、LC_LOAD_DYLIB 和实际部署文件。 |

以上路径以各工程根目录为基准。旧分析位于 OrTavern `docs/development/research/ortts-runtime-compatibility-2026-11-07.md`；新增结论是“上游已实现的模型可用于真实底层收敛实验”。

## 2. 能力与等效关系

| 能力 | Sherpa 常用路线 | ggml 生态已存在 | 等价边界 |
|---|---|---|---|
| 传统 TTS | Kokoro、VITS/Piper 等模型专用前后处理 + ORT | audio.cpp `kokoro_tts`、`piper_tts`；独立 kokoro.cpp | 同检查点能有不同后端执行，但先核对模型/voice/G2P版本。Piper port 有实际 VITS runtime；不是任意VITS ONNX导入器。自研Qwen/LiquidCodec是另一模型能力，不能替代同音色。 |
| 离线 ASR | SenseVoice、Whisper、各类 CTC/transducer | audio.cpp `sense_asr`，SenseVoice.cpp，whisper.cpp | SenseVoice 同族移植与 Whisper 替换模型是两回事；特征提取、ITN、标点、标签和量化会影响输出。 |
| 流式 ASR | OnlineRecognizer + Zipformer encoder缓存/decoder/joiner + endpoint | audio.cpp `kroko_asr` 是特定 Zipformer2 的有状态实现；Whisper 示例为窗口重解码；SenseVoice为缓冲窗口 | Kroko可作为真正流式算法参考，不能加载任意Sherpa Zipformer。窗口上传/分段输出不等于原生在线模型。中文产品仍保留现有Sherpa链。 |
| VAD | Silero 等 + 语段状态机 | audio.cpp 自带 Silero runtime；whisper.cpp 有 Silero模型转换、加载及分段 | 同一Silero版本可比较后端概率；v5/v6不能混为同权重。必须保持采样率、frame长度、LSTM状态、阈值、迟滞、尾静音和reset语义。能检测语音不代表替代endpoint。 |

证据：audio.cpp 锁定源码 `src/models/kokoro_tts/{frontend,predictor,decoder,session}.cpp`、`src/community_models/piper_tts/vits_runtime.cpp`、`src/community_models/sense_asr/`、`src/community_models/kroko_asr/`、`src/models/silero_vad/`；源树具体布局以固定提交为准，当前 public main 的 community 文件与 docs/models 链接曾调整。[S1–S6,S15]

### 分级规则

- **同模型不同后端**：相同checkpoint、配置、音色、token表、G2P输入，先 FP32/BF16/F16校验再量化。GGUF/ONNX只是序列化与图合同的一部分。
- **相近能力不同模型**：Whisper换SenseVoice、英语Kroko换中文Zipformer、Qwen TTS换Piper。可做产品选型，不可称兼容迁移或同模型性能对照。
- **已有可用实现**：存在 loader、算子图、前后处理、运行入口和验证记录；仍需目标机验收。
- **实验/转换**：只有导出脚本、能加载tensor或单算子测试，尚不足以执行pipeline。MNN/ncnn导入某ONNX也必须过此关。

Kroko 上游验证报告提供 Windows/Ryzen/RTX、Sherpa 1.13.4 CPU参考和具体包/探针；这是可信的作者复现记录，**不是本机或移动端验收**。[S4] whisper.cpp 的 `examples/stream` 自称简单实时示例，不能作为原生Zipformer同等延迟证明。[S5]

## 3. Kokoro 专项

### 3.1 模型版本不能合并成一个名称

- **Hexgrad Kokoro-82M v1.0**：官方2025-01-27发布，82M，官方模型卡标8种语言、54音色；美英两种英语口音常在运行时表中展开成9个locale。权重Apache-2.0，原生参考为PyTorch + KPipeline/Misaki，24kHz。[S8,S9]
- **v1.1-zh**：独立权重与tokenization，主要100中文+3英文音色；官方说明其并非保留全部旧音色的严格升级。Sherpa `kokoro-multi-lang-v1_1` 包有103音色。[S10,S11]
- **Sherpa v1_0包**：文档明确53音色、中英支持；不能把底层多语权重理解为该包前端已支持全部语言。宿主的中英包指向v1_1，英语条目还保留v0_19；资产清单必须保留这些身份。[S10]

### 3.2 后端核查

| 实现 | 实际执行与精度 | 前端 / 语言音色 | 输出流与平台证据 | 判定 |
|---|---|---|---|---|
| Hexgrad PyTorch参考 | 原始v1.0/v1.1-zh权重；参考数值行为 | Misaki、对应语言资源；部分语言eSpeak fallback | pipeline迭代可按文本段返回；不是实时增量文本神经模型；Python环境非移动SDK | 质量/G2P参考，不作为App统一底座 |
| Sherpa/ORT | 明确Kokoro loader，官方发布FP32/int8包 | tokens、voices.bin、lexicon/FST、字典/eSpeak；包决定语言 | `OfflineTts`名称下可按合成batch/sentence callback返回与取消；一次Run中的计算不能因此立即停止。三主平台有框架入口，宿主未全部启用 | 现用基线，保留 |
| kokoro-onnx | 项目导出v1.0/v1.1-zh，发布FP32/FP16/int8资产 | 发布voice版本配对，Python侧phonemizer；不能替代中文字典流程 | 有生成接口，近期release增加continuous/timed相关输出；不据此推断实时低延迟或移动C ABI | 排除Sherpa包装开销的ORT参考候选 |
| audio.cpp/ggml | **真实原生pipeline**；锁定源树含loader、PLBERT、predictor、decoder、iSTFT及G2P；v1.0 GGUF Q8_0/BF16 | 54 voices；共享eSpeak，中文内置G2P表，日语还需MeCab/UniDic；并非任意第三方Kokoro GGUF可加载 | 锁定文档明确按文本chunk真正逐段合成后输出；短句可能仅一块。Windows CPU作者smoke记录；无本工程Kokoro三平台实测 | 值得验证现成实现，不需从零移植；v1.1-zh尚无本轮确认的匹配支持 |
| simonfxr/kokoro.cpp | 完整C/C++ ggml执行器、C ABI，F16/Q8_0与独立voice GGUF | 固定ggml、Highway子模块及系统eSpeak；发布54 voices，不代表全语言G2P验收 | README声明24kHz整句生成，CPU/Metal/Vulkan/CUDA；未找到本轮可引用的iOS/Android同模型实机验收或稳定发行承诺 | 可信原生实现候选，但不优先再引入第二份ggml |
| MLX Python / KokoroSwift | 模型的MLX实现，非GGUF或ORT；Swift package可嵌入Apple | KokoroSwift默认MisakiSwift；其API示例为enUS，不外推完整v1.1-zh支持 | KokoroSwift示例SPM from1.0.0、iOS18/macOS15，作者有iPhone13Pro Release暖机结果；API为整段音频 | Apple定向候选；无Android/Linux/Windows共同底座 |
| FluidAudio/Core ML | 发布模型分阶段执行，不是把原始ONNX直接无损全图跑ANE | v0.17.6 Kokoro ANE v3明确英/日/中，区分v1.0与v1.1-zh资源 | macOS15/iOS18；CPU/ANE、CPU/GPU及Accelerate混合；该版本说明明确physical iOS inference尚未验证 | 有实现与macOS性能记录，不能当已验iPhone加速 |

资料：[S1,S8–S13,S16–S19]。MLX/Core ML的具体导出精度、量化算子覆盖和每个voice的设备验证本轮未逐资产核实；不能把MLX可量化或Core ML支持低精度当成这些包已完成量化验收。kokoro-onnx release文件大小约FP32 326MB、FP16 164MB、int8 114MB，voice另计；这仅为模型文件，不是App二进制或峰值内存。其发布者提供的相关性数字不是听感验收。[S12]

### 3.3 迁移判断

**值得：** 在已有audio.cpp固定源上，对v1.0的英语/中文做同资产探针，评估能否在不引入第二份ggml的条件下卸除某个产品包的Kokoro ORT路径。

**暂不值得：** 为统一扩展名立即换掉OrTavern v1.1-zh/103音色；把独立kokoro.cpp、MLX、Core ML一起装进默认SDK；从头重写Kokoro。若ASR或记忆模型仍要求ORT，迁移Kokoro本身不会消除ORT，只可能减少session与部分前端依赖。

**进入产品默认的必要条件：** 同模型/voice/token/G2P版本可验证；中文数字日期、混合拉丁、长句不退化；三主平台完成实机与包体测试；用户可感知的首声/RTF/内存/功耗收益超过迁移维护成本。v1.0探针成功只能认证v1.0子集。

### 3.4 许可证与资源边界

模型Apache-2.0不等于整条链都Apache。audio.cpp Apache-2.0，ggml MIT，kokoro.cpp/KokoroSwift标MIT，FluidAudio标Apache-2.0；eSpeak-ng为GPL-3.0-or-later，静态链接和动态链接都需要审查具体分发安排，不能声称动态链接天然免除义务。[S13,S17,S18,S20] 原始/导出模型、词典、MeCab/UniDic、Misaki语言依赖和voice包分别登记来源与许可。Piper运行时不同代际许可不同，现维护OHF实现与归档旧代码不能混同；voice卡逐个核对。Kroko商业/加密包明确排除在免费转换器之外。本报告不裁定特定App分发的法律兼容性。

## 4. 模型 × 后端 × 平台证据矩阵

标记：**S**=有模型专用源码/构建入口；**P**=官方发布库/工具或模型资产（不代表此模型实机通过）；**U**=作者公布该路径的运行/验证；**L**=本工程历史实机或运行记录；**?**=未核实该模型该平台。组合如S/P只到该证据等级。平台简称M=macOS Apple Silicon，I=iOS ARM64，A=Android ARM64，Lx=Linux，W=Windows。

| 模型/精确子集 | 执行器、版本锚点 | M | I | A | Lx / W | 模型证据与不能外推之处 |
|---|---|---|---|---|---|---|
| OrTTS P3/P5自研包 | 本仓库固定audio.cpp + unified可选LiquidCodec | L（历史） | L（历史） | L（历史） | S / ? | 历史链路/包版本各异；本轮未重跑，旧FAILED receipt不被现存dylib覆盖 |
| Kokoro v0.19/v1_0/v1_1 | Sherpa锁1.13.8；公开release页另列2.0.1 | S/P | S/P | S/P | S/P / S/P | 各平台发布体系[S14,S21]；Kokoro具体包[S10]；本轮无三平台模型级验收，宿主iOS feature关闭 |
| Kokoro v1.0 54音色 | audio.cpp固定e930…；上游v0.9.4作参考 | S | ? | ? | S / U | 固定源内实现、Windows CPU12项G2P/18项非静音smoke；不证明听感等价，也不证明v1.1-zh |
| Kokoro v1.0 | simonfxr/kokoro.cpp master，未锁发行 | S | ? | ? | S / S | C ABI+F16/Q8模型发布[S13]；无本项目移动验证，不与audio.cpp GGUF互换 |
| Kokoro | KokoroSwift示例from1.0.0 | S | U（作者） | — | — / — | iPhone13Pro作者结果；语言/模型资产按包，不能继承我们的iPhone17证据[S17] |
| Kokoro v1.0/v1.1-zh分支 | FluidAudio0.17.6 v3 | U（作者） | S，明确未实机验 | — | — / — | Apple新系统版本及混合设备执行[S18,S19] |
| Piper en_US-lessac-medium | Sherpa VITS/ORT vs audio.cpp `piper_tts` orig GGUF | S/P vs S | S/P vs ? | S/P vs ? | S/P vs S（Lx）、作者路径（W） | 同模型移植候选；22.05kHz，与Kokoro24k不可硬套；不覆盖宿主全部Melo/VITS[S2] |
| SenseVoice-Small | Sherpa ORT vs audio.cpp `sense_asr` Q8 / SenseVoice.cpp | S/P vs S | S/P vs ? | S/P vs ? | S/P vs S | GGML已有模型图；audio.cpp用Silero分段、buffered streaming，不等于原生在线模型[S3,S6] |
| Whisper | whisper.cpp专用模型图/官方发行 | S/P | S（官方示例） | S（官方示例） | S/P / S/P | 同Whisper有ORT实现可比较；与SenseVoice仅能力替代，窗口stream不等价Zipformer[S5,S22] |
| zh-en Zipformer small 2023-02-16 | Sherpa OnlineRecognizer | S/P | S/P | S/P（宿主客户端路径） | S/P / S/P | 宿主实际资产已定位；ggml可直接加载的等价实现本轮未找到 |
| Kroko免费64-L/128-L Zipformer2 | audio.cpp `kroko_asr` | S待验 | ? | ? | S / U（作者） | 有状态缓存、partial、endpoint；特定10单语包，不含现用zh-en，需独立许可[S4] |
| Silero指定版本 | Sherpa ORT / audio.cpp / whisper.cpp ggml | S/P | S/P（Sherpa）其余? | S/P（Sherpa）其余? | S/P | 各自模型布局与版本不同；audio.cpp模型是内部VAD，不因库中存在就已接OrTTS ABI[S15] |

**平台证据范围：** Sherpa 的 P 来自通用库/XCFramework/Android分发体系，Kokoro模型包 P 是独立资产；两者组合仍需目标平台执行才能升级为模型级 U/L。本轮未获取新产物，未验证下载链接中的每个库slice。

**矩阵不是兼容白名单。** 发布版本、库产物、模型资产、设备运行、质量和性能应在manifest/测试报告中分别打勾；不能仅凭`__APPLE__`、`ANDROID`或发布页有XCFramework声明可交付。对没有模型级移动证据的audio.cpp端口，优先保留问号。

## 5. A/B/C 路线比较

| 维度 | A 保留ggml+Sherpa，统一管理 | B ggml为主，逐模型收敛 | C ORT或平台执行器等其他底座 |
|---|---|---|---|
| 真正统一的层 | API/包/生命周期/资源预算；底层仍两个 | 已迁移模型可共用同pin ggml、部分前端；未迁移保留ORT | ORT统一图执行但仍多pipeline；CoreML/MLX是按平台不同底层 |
| 依赖体积 | 初期最高风险是多份ORT/eSpeak；裁剪模型模块与统一链接可立刻调查 | 移除一个TTS port不一定移除ORT；若该产品全部ASR/TTS都过ggml才可能消除ORT | 已有ORT可裁剪算子/EP；全迁自研Qwen/codec需要导出和算子重做；Apple SDK加CoreML不等于零模型资产 |
| 维护成本 | 较低迁移风险，需维护两adapter与版本矩阵 | 中高：同pin算子、模型转换、G2P、量化、上游fork持续回归 | ORT中等/高；新MNN/ncnn全栈高；多平台执行器的模型/前端分叉高 |
| 性能 | 让每模型用已有成熟实现；无法仅靠接口提速 | 可专用优化，但非自动快于ORT；CNN、LSTM、动态shape未必是ggml强项 | CoreML/MLX可能利于Apple；EP分图、拷贝和fallback可抵消加速，必须端到端测[S23] |
| 内存 | 两线程池/arena/cache需预算；按需装载降低常驻 | 可统一backend分配但不能默认跨模型共用KV/arena；GGUF mmap不等于低峰值 | ORT arena/EP编译缓存各自占用；CoreML首次编译与多stage驻留另计 |
| 覆盖 | 最稳，Sherpa补ASR/传统TTS | 精选模型可行，长尾和特定中文流ASR保留兼容 | ORT广图覆盖但不涵盖现自研pipeline；CoreML/MLX局限Apple，MNN/ncnn需逐图导出/验证[S24] |
| 流式/取消 | adapter真实披露每模型能力 | 专用模型状态机可控，但长段图仍不能立刻取消 | 通用Run/terminate语义不替代模型级reset；EP硬件任务不保证抢占 |
| 推荐 | 近期实施，明确多底层 | 通过下面两个实验后逐步采用 | 有可量化设备收益再做单个适配器，不做全面替换 |

**拒绝的推理：** 同为GGUF→可以共享loader；同为ONNX→可以直接交换session；同为ggml→可以直接链接两个不同版本；模型文件更小→二进制或峰值内存一定更小。

### 哪些依赖真的能减

体积尚无可比实测，不能给出“换ggml节省多少MB”的数字。报告公式应为：单架构已strip原生库总和 + 必需字典/资源 + 该产品选择的模型，分别列磁盘/压缩包；内存另列已加载权重、激活峰值、各后端arena、线程栈和播放队列。Kokoro的图arena配置上限不应直接累加成已分配RSS。

1. **ORT共享（候选，未实现）**：让Sherpa、Rust ort显式依赖同一兼容版本的ORT库和EP配置，验证API/ABI、opset、custom ops及符号可见性；Sherpa内建静态ORT不能通过改名字“复用”Rust OrtSession，session/allocator ownership不可跨库传递。能共用一个`OrtEnv`也不代表当前Sherpa API允许注入它。
2. **ggml共享（候选，已有基础）**：优先把模型编译在audio.cpp同一源与backend版本，而不是分别静态链接kokoro.cpp、whisper.cpp的ggml。当前LiquidCodec unified source是实际收敛的先例；换pin仍要跑原有自研回归。
3. **eSpeak/字典**：audio.cpp已有共享phonemizer并序列化调用。与Sherpa可共用库/字典须语言版本、数据ABI和许可证一致；phoneme映射/normalizer不必相同。不保留多个压缩、解压后的字典副本才有实际磁盘收益。
4. **FST/FFT/fbank/重采样**：能复用的是参数完全一致的实现；Whisper mel、Kaldi fbank/LFR、VAD采样窗不能只因名称相同而统一。需要保持数值基准。重复静态库还要检查隐藏符号/ODR。
5. **不是推理依赖的合并**：公共下载、日志、音频帧、调度是代码与行为复用，不应宣传已合并数值底层。按product feature不装未用adapter，通常比一个“全模型万能包”更省。

## 6. 可复用层与最小合同

| 层 | 可复用范围 | 必须隔离的内容 |
|---|---|---|
| tensor backend | 同ggml pin的CPU/Metal上下文、device预算；同ORT库的基础设施 | tensor布局、量化类型、graph、allocator/stream ownership不能跨框架强传 |
| model pipeline | loader注册、能力发现、请求/错误框架 | Qwen自回归+RVQ、Piper flow/VITS、Kokoro PLBERT/LSTM/iSTFT、ASR fbank/CTC/RNNT分别实现 |
| tokenizer/G2P | 版本化资源缓存、eSpeak受控服务、可独立测试的normalizer | IPA字表、重音标记、中文数字/多音字、日语切词、ASR SentencePiece都模型专属 |
| 声码器/codec | 相同检查点、采样率、frame/hop/codebook及精度合同才共享 | Piper生成器、Kokoro iSTFTNet、LiquidCodec不能互换；共同conv算子不等于共同decoder |
| 音频转换 | 公共PCM metadata、重采样、混音、格式转换、有界队列与时间基准 | 播放器/麦克风/AEC属宿主平台；推理回调不能阻塞AudioTrack或主线程 |
| 模型下载校验 | hash/CAS去重、原子安装、信任manifest、磁盘预算 | 安装、已验证、设备可运行、模型已加载四种状态；版本转换不得覆盖旧资产 |
| 调度与取消 | per-executor worker、request_id/epoch、优先级、线程预算、终态 | 当前全库互斥不能靠多worker解除；非抢占图不能谎报立即取消/释放算力 |
| 内存/缓存 | LRU按checkpoint+adapter+backend+precision+frontend版本键缓存 | 不能跨模型复用decoder状态；共享session须明示不可并发。底层线程池必须纳入全局预算 |

建议新增版本化SDK合同，而非修改ABI1结构解释：

- `EngineCapabilities`：task/family、offline / chunked_output / stateful_input / incremental_text各自独立、cancel granularity、输入输出格式、音色与语言、线程约束、后端。
- `TtsSession`：`submit(text, voice, options, request_id)` → `audio_chunk(metadata, sequence, epoch)` → 单一`completed/cancelled/failed`。语句分片是否模型级或宿主级明确标注；后端不能把一次完成波形拆小假装低延迟。
- **独立 `AsrSession`**：`accept_audio(samples, sample_rate, channels)`、`input_finished`、`decode_ready/decode`（需要时）、`partial`（可修订）、`final`、`is_endpoint`、`reset`、`cancel`。增加segment ID、已消费音频时间与可修订区间；endpoint与final/reset不自动等同。
- `VadSession`：接受固定协议音频、输出概率/区间与状态reset；ASR endpoint可消费VAD但不由其冒充识别状态。
- PCM统一结构允许16k/22.05k/24k/其他，f32为建议内部表示但不伪改采样率；重采样只放明确边界。终态后任何旧epoch chunk都丢弃。

## 7. 跨平台与二进制检查

| 平台 | 需要解决的具体问题 | 不能用来代替证据的说法 |
|---|---|---|
| macOS Apple Silicon | baseline/性能ISA分别测；Metal buffer/command queue与CPU fallback；dyld install_name/rpath与导出符号；ORT dylib与ggml pin；G2P动态库发现 | Mac可跑Python不等于可嵌入Swift/Rust；M5结果不代表M1 |
| iOS ARM64 | 签名内置framework/XCFramework、真机/模拟器slice、min OS、静态字典资源定位、App生命周期、内存压力、中断；不下载执行代码 | Xcode编译成功不等于设备执行；ANE/CoreML只有分图/设备trace证据才标加速 |
| Android ARM64 | baseline/DotProd/I8MM/FP16能力分派、NDK/libc++_shared唯一来源、JNI与C ABI收敛、16KB页、native lib冲突、AudioTrack有界队列；可选Vulkan/QNN/NNAPI逐模型验证 | ARM64不保证I8MM；有EP名称不等于设备实际执行，QNN只针对匹配硬件与资产 |
| Linux | glibc/libstdc++最低版本、RPATH、静态/动态ORT、x64 ISA与ARM工具链 | 本机Apple编译不代表Linux可交付 |
| Windows | MSVC CRT、DLL名字/搜索路径、同名ORT DLL、符号导出、Unicode字典路径 | `_WIN32`导出宏不是Windows构建证据；不能把作者Windows GPU结果当移动端性能 |

使用 `otool -L`/`nm`/link map、Android `readelf -d`/APK清单、Windows `dumpbin /dependents`与映射记录。分别报告strip后单架构原生库总大小、分发压缩大小、模型/字典大小、启动后RSS/PSS、峰值内存、退出后残留。`OrtGetApiBase`/ggml/eSpeak重复定义、两份OpenMP/不同libc++、多个线程池、不同GGUF布局均是实际风险点，不靠隐藏文件名解决。

硬件加速先CPU基线：ORT的CoreML/XNNPACK/QNN等支持是通用EP能力，不证明Sherpa每个构建启用或每层命中；MLX不是ANE，CoreML也不是全图ANE。FluidAudio当前v3文档尤其明确CPU/ANE/CPU-GPU混合与真机iOS未验证。[S18,S19,S23]

## 8. 最小验证实验设计

本节为待批准小切片，**不在本轮执行**。每个只做独立CLI/测试harness，不改OrTavern、不重写SDK。预算先限定macOS CPU，三平台资格分别验收。

### E1 传统TTS：Piper en_US-lessac-medium

**理由：** audio.cpp明确给出同ONNX voice到native的转换与VITS pipeline，模型小、前端可控制；比从现用v1.1-zh直接换到v1.0 Kokoro更容易判定是不是后端问题。[S2]

- 基线：Sherpa锁1.13.8 CPU，固定原始Piper ONNX、config.json、speaker、eSpeak数据；参考源权重不换voice。实验：固定audio.cpp base+本仓库补丁、`piper_tts`单family，先orig精度（保留源张量类型），再独立量化。仍保留Qwen自研构建回归，不全仓升级到v0.9.4。
- 资产：批准后下载精确voice的ONNX/config与model card/LICENSE，记录revision+SHA；phonemizer数据同版本；转换产物GGUF及转换脚本commit。模型作者的voice许可先登记。
- 步骤：20条英文（数字/时间/缩写/问句/标点/长句），保存标准化文本和音素；相同线程1/2/4，固定随机/噪声参数；各冷启动3次、暖请求10次，顺序AB/BA；chunk与一次整句分开测。保存WAV、duration、F0/音素/听评结果，不以WAV hash要求不同精度完全一致。
- 功能通过：22050Hz mono实际元数据正确；每条完整、非静音/NaN、无丢音素；normalizer/音素相同或差异可解释并人工接受；20条盲听无明显新增故障；duration误差>5%进入人工复核而非直接认证等价。
- 资源通过：加载/释放30轮不持续增长；停止/取消/销毁无死锁，100次重复操作无旧请求chunk泄漏。若仅句间取消，必须报告单个句图的p95最差取消等待，而非伪称立即中断。
- 迁移门槛（设计目标，不是已测收益）：p95端到端延迟或RSS/包体至少一项改善20%，其他指标不退化超过10%，可单独打包去掉ORT且满足同voice质量。否则保留Sherpa，只共享管理层。

### E2 ASR：SenseVoice-Small离线，流输入单独验

- 基线：宿主现有SenseVoice原始检查点对应的Sherpa FP32（若只能获得int8，分别列量化变量）；实验audio.cpp `sense_asr`相同检查点的F16/原精度导出，之后才Q8。不要将不同SenseVoice版本/ITN设置混入后端对照。
- 资产：固定checkpoint、tokens/SentencePiece、config、CMVN与导出元数据；批准后准备不含私人录音的中/英/粤/日/韩短样本，共至少50条、10分钟，含静音/噪声/数字；保存标注。功能先用同16k mono PCM，关闭两端VAD/分段以隔离图差异，再启用同版本Silero测完整链。
- 步骤：比较fbank/LFR/CMVN参数与小tensor探针，再转录；CER用于中文/日文、WER用于英文，ITN与event/emotion tags分开评分；记录冷/暖、p50/p95、CPU占用、峰值RSS及线程。相同标点规范不等于抹掉实质识别错误。
- 精度通过：非量化同模型CER/WER绝对退化≤0.5个百分点；Q8≤1个百分点作为初始门槛，罕见词、语言标签和ITN关键用例不能静默缺失；样本少只准进入下一实验，不能宣称生产精度等价。
- 生命周期通过：accept不同分块尺寸得到一致final；input_finished可排空、reset后不串句；30分钟伪实时输入内存有界；静音不输出幻觉文本。音频文件分窗重跑只认证buffered能力，不认证低延迟在线ASR。
- 流式产品门槛：继续保留现用zh-en Zipformer。后续若试Kroko必须用其支持语言的同包、相同chunk/decoder参考做独立实验；不能拿英语Kroko CER/WER替中文Zipformer。partial延迟、endpoint边界误差、final/reset才是在线验收项。

### 共同测量与终止条件

先生成最小link map/BOM：仅自研、仅Sherpa、两者共存、native TTS+ASR去ORT四种feature构建，测大小差值；若其他App功能仍依赖ORT，明确“该App无法删除ORT”。macOS通过后才分别为iPhone/Android真机编译运行，CPU同档位、散热状态、线程、seed、token limit、首PCM/首声区分。资源缺失、许可证未知、任一关键语言退化、mobile无法打包或引入第二份ggml/ORT，即停止迁移并保留A。

## 9. 分阶段计划与退出标准

| 阶段 | 可以交付的小切片 | 完成标准 / 不做什么 |
|---|---|---|
| 现在：事实与BOM | 锁模型/执行器版本；列所有已启用features和最终库；定义capabilities、音频metadata、TTS/ASR独立合同 | 不改宿主主线，不把接口统一记成底层统一；未知依赖体积保持未知，不填猜测MB |
| 下一实验：E1/E2 | 两个macOS独立CPU探针 + 资产hash与对照报告 | 无大模型默认下载；未过精度/体积门槛不接App、不删Sherpa |
| 验证后：A的最小SDK | registry、包校验、per-executor worker、request epoch与终态；保留ABI1，新增版本化接口 | 同一个App可只链接一个adapter；同进程两个执行器不共享模型句柄；先解决全库环境配置再承诺并行 |
| 有收益才做B | 在同一audio.cpp pin选入已验Piper/SenseVoice；随后Kokoro v1.0子集 | 每迁移一个记录实际删除库/资源；现用103音色无匹配路径就保留Sherpa |
| 移动资格 | iOS/Android各一台真机，FFI/签名/取消/音频中断、内存压力、热负载 | 源码/构建/设备执行/性能/听感五项分开记；Android JNI迁到统一合同是独立小任务 |
| 可选C | Apple单个CoreML或MLX执行器、某Android模型的QNN执行器 | 只有跨平台CPU已稳且设备实测收益明显才加入；不默认把全部后端塞到SDK |
| 暂不值得 | 全Sherpa→ggml、通用ONNX→GGUF执行器、重写所有G2P、复制宿主provider/编排 | 没有可接受的收益与覆盖证据 |

最终架构名称建议：**OrTTS多执行器语音SDK**。只有经过迁移验证的特定产品配置才称“ggml单底层构建”；A阶段一律称统一接口/资产/生命周期，不混称统一推理框架。

## 证据索引

链接访问日期均2026-11-07；main/master是移动来源，实施前必须补全commit与资产hash。项目发行版不是模型版本。以下以维护者仓库、源码、模型作者卡和作者验证报告为主，不以社区转载或转换文件存在证明兼容。

- S1 [audio.cpp Kokoro源码与用法](https://github.com/0xShug0/audio.cpp/blob/main/docs/models/kokoro_tts.md)；固定base内 `tests/kokoro_tts/MULTILINGUAL_GGUF.md` 明确任意GGUF不兼容、Windows smoke范围及G2P限制。
- S2 [audio.cpp Piper](https://github.com/0xShug0/audio.cpp/blob/main/docs/models/piper_tts.md)，固定源内转换入口 `tests/piper_tts/convert_piper_onnx.py`、`src/community_models/piper_tts/vits_runtime.cpp`。
- S3 [audio.cpp SenseVoice](https://github.com/0xShug0/audio.cpp/blob/main/docs/models/sense_asr.md)。
- S4 [Kroko专用移植](https://github.com/0xShug0/audio.cpp/blob/main/docs/community_models/kroko_asr.md)、[验证报告](https://github.com/0xShug0/audio.cpp/blob/main/docs/reports/kroko_asr_validation.md)，2026-07-27 Windows作者环境。
- S5 [whisper.cpp实时示例及窗口说明](https://github.com/ggml-org/whisper.cpp/blob/master/examples/stream/README.md)。
- S6 [SenseVoice.cpp](https://github.com/lovemefan/SenseVoice.cpp)、[模型作者部署入口](https://github.com/QwenAudio/SenseVoice/blob/main/README.md)。
- S7 [audio.cpp v0.9.4发行](https://github.com/0xShug0/audio.cpp/releases/tag/v0.9.4)；不得自动取代本仓库e930…固定源。
- S8 [Kokoro v1.0模型卡](https://huggingface.co/hexgrad/Kokoro-82M)。
- S9 [Hexgrad原生PyTorch pipeline](https://github.com/hexgrad/kokoro)。
- S10 [Sherpa Kokoro模型包、语言与音色](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html)。
- S11 [Kokoro v1.1-zh模型卡](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)。
- S12 [kokoro-onnx维护者仓库](https://github.com/thewh1teagle/kokoro-onnx)、[模型发行资产](https://github.com/thewh1teagle/kokoro-onnx/releases)。
- S13 [simonfxr/kokoro.cpp完整C ABI与GGML执行器](https://github.com/simonfxr/kokoro.cpp)、[配套模型卡](https://huggingface.co/simonfxr/kokoro.cpp-GGUF)。
- S14 [Sherpa iOS构建脚本](https://github.com/k2-fsa/sherpa-onnx/blob/master/build-ios.sh)、[Android ARM64构建](https://github.com/k2-fsa/sherpa-onnx/blob/master/build-android-arm64-v8a.sh)。
- S15 [whisper.cpp Silero VAD](https://github.com/ggml-org/whisper.cpp#voice-activity-detection-vad)、[Silero原作者](https://github.com/snakers4/silero-vad)。当前whisper文档示例v6.2.0，不能推断audio.cpp同版本。
- S16 [MLX Audio维护者仓库](https://github.com/Neywa-Labs/mlx-audio)（旧Blaizzy路径重定向）。
- S17 [KokoroSwift需求、G2P与作者iPhone结果](https://github.com/mlalma/kokoro-ios)。
- S18 [FluidAudio Kokoro v3平台与iOS验证限制](https://github.com/FluidInference/FluidAudio#kokoro-ane)。
- S19 [FluidAudio TTS基准方法](https://github.com/FluidInference/FluidAudio/blob/main/Documentation/TTS/Benchmarks.md)，仅相应模型/设备/阶段，不把局部毫秒结果当完整App延迟。
- S20 [eSpeak-ng COPYING](https://github.com/espeak-ng/espeak-ng/blob/master/COPYING)及固定audio.cpp `docs/espeak_phonemizer.md`。
- S21 [Sherpa发行列表](https://github.com/k2-fsa/sherpa-onnx/releases)（可见v2.0.1），宿主锁文件仍1.13.8；[Kokoro批次callback实现](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/csrc/offline-tts-kokoro-impl.h)、[OnlineRecognizer transducer](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/csrc/online-recognizer-transducer-impl.h)。
- S22 [whisper.cpp项目](https://github.com/ggml-org/whisper.cpp)、[iOS示例](https://github.com/ggml-org/whisper.cpp/blob/master/examples/whisper.objc/README.md)、[发行记录](https://github.com/ggml-org/whisper.cpp/releases)。本报告不选择移动master作为可复现二进制基线。
- S23 [ORT Execution Provider构建说明](https://onnxruntime.ai/docs/build/eps.html)。
- S24 [ncnn](https://github.com/Tencent/ncnn)、[MNN](https://github.com/alibaba/MNN)：一般移动推理能力，不构成本研究模型的完整pipeline或目标设备验收。
