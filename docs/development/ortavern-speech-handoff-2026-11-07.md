# OrTavern 音频后端迭代交接

## 增量 ASR 更新（2026-11-07）

新增独立 `ortts_asr_stream_*` ABI1 和 Rust `speech::streaming`，不改变下文旧 `ortts_asr_*` final-only 合同。Moonshine英语可修订partial/final、flush/reset、能量/限长endpoint、跨线程取消与stats已接线，仍共享一份ggml。Rust `Cancellation` 可交UI线程，句柄Drop后自动失效，不保活权重。能力检查用 `ortts_asr_stream_abi_version` / catalog的 `incremental_asr`；旧字段 `partial=false` 仅描述旧接口。

它采用F16展开编码权重、有界重叠编码和重算假设解码，**不是逐层KV完全复用**；中文仍用SenseVoice离线，宿主已有Sherpa真流式中文和全双工路径继续保留。本次不集成Sherpa submodule，不复制宿主编排或修改OrTavern主线。

新增验收见 [SDK状态与内存](../../benchmarks/asr-stream-sdk-20261107.json)、[音色/长句](../../benchmarks/asr-stream-quality-20261107.json)、[平台检查](../../benchmarks/asr-stream-platforms-20261107.json)。默认15秒segment上限下，独立进程加速回放约303秒语音，预热后RSS约228–230MiB，未随输入增长；不是手机或麦克风热验收。原TTS/离线ASR回归见 [回归记录](../../benchmarks/speech-stream-regression-20261107.json)。

本机新产物：`build/speech-incremental-macos/install/lib/libortts.dylib`、`build/speech-incremental-ios/install/OrTTS.framework`、`build/speech-incremental-android/install/lib/libortts.so`。移动端目前只完成构建/符号/Swift接口检查，模型设备运行未验收。接线与事件生命周期以 [SPEECH](../../runtime/SPEECH.md#moonshine-增量-asr) 为准，下面旧交接保留作历史范围。

## 初始交付记录

2026-11-07，交付仓库OrTTS-demo。本轮仅修改运行时仓库，未改OrTavern主线、provider、prompt或对话编排。用户授权后端集成本地提交，然后通知“OrTavern主开发”组织宿主迭代；不是授权直接发布App或替换手机默认后端。

## 已完成的后端

- 可选`--speech`将Kokoro、Pocket、Piper、Kitten、ZipVoice TTS，以及SenseVoice/Moonshine ASR，接入同一`libortts`/`OrTTS.framework`，共用一份ggml。原P3/P5 C ABI1保留；新增独立speech ABI1。不是通用ONNX运行时。
- C ABI：[ortts_speech.h](../../runtime/include/ortts_speech.h)；Rust：`ortts_engine::speech::{Config,Request,Tts,Asr}`；完整合同/构建/依赖见[SDK说明](../../runtime/SPEECH.md)。
- 原生音频rate/channels/frames，不强制24kHz；Piper实际22.05kHz。播放和ASR输入转换由宿主明确执行。
- Kokoro处理同步事件，Pocket/ZipVoice处理pull命名音频块；回调帧数核对、取消与句柄复用已测。Piper/Kitten仅离线，拒绝流式配置，不能在UI假装有首包播放。
- ASR独立run/accept/finish/reset，16kHz mono输入，默认60秒、最多120秒缓冲。final-only，**没有partial或自动endpoint**。旧Sherpa实时路线不能因此删除。
- 模型目录/资产例子：`runtime/models/catalog.example.json`；只读SHA验证：`tools/verify_speech_pack.py`。宿主继续负责下载、验证、模型包版本、UI选择与小型引擎缓存。
- 新旧接口仍共用进程级BUSY门，原因是旧路径依赖进程环境；不宣称并行推理已实现。不得同时加载另一份独立OrTTS/ggml副本来绕过。

## 实际验收

结构化记录：[speech-integration-20261107.json](../../benchmarks/speech-integration-20261107.json)。

| 目标 | 证据 | 没有完成的证据 |
|---|---|---|
| macOS M5 | 五个TTS真实合成；Kokoro/Pocket/ZipVoice取消后复用；两个ASR离线/缓冲一致、中文与英文、静音/非有限值/上限/reset；C和Rust闭环 | 非所有模型、语言、音色或长音频的质量认证 |
| 原P3 ABI | 与已有Oct31动态库同一短句/seed输出44160个F32逐字节相同；模型包验证同时覆盖LiquidCodec编译开/关 | 本轮未重新benchmark所有P5/1.7B/codec组合 |
| Kokoro修正 | 同一配置只开关PL-BERT图分配，离线WAV逐字节相同；取消/复用回归通过 | 未全面认证所有shape/GPU/设备 |
| iOS ARM64 baseline | framework构建、两份公共头/模块、Swift导入typecheck | 新增模型未安装到手机运行/试听；未构建本轮模拟器slice |
| Android ARM64 baseline | NDK27链接，34个公开ABI，隐藏ggml/audio.cpp，LOAD对齐0x4000，检查动态依赖 | 新增模型未在手机真实运行；旧Demo JNI没有自动改线 |

macOS安装库约8.5MiB，iOS设备framework二进制约8.4MiB，Android stripped安装库约6.28MiB。它们的编译配置不同，不能用差额推断平台成本。Android未strip构建约116MiB主要含调试信息，发布安装步骤已剥离，原文件留作调试。数字不含模型、eSpeak库/约25MiB字典、Android libc++_shared或宿主原有Sherpa/ORT。

本机产物（不入Git）：

- `build/speech-macos-final/install/lib/libortts.dylib`
- `build/speech-ios/install/OrTTS.framework`
- `build/speech-android/install/lib/libortts.so`
- 各build下`ENGINE_BUILD_RECEIPT.json`记录目标/profile/源指纹/产物SHA；设备运行结果以验收JSON为准，不能把BUILT状态当设备通过。
- `outputs/speech-acceptance-2026-11-07/`含C/Rust日志、音频；试听音色索引在`outputs/voices-2026-11-07/LISTEN.md`。

## 优先级与已停止路线

1. 用户明确允许单语言，不再要求所有模型中英同句混读。英语Pocket优先可选；Kokoro纯中文四个音色通过自动内容检查，但手机内存仍需实测。既有改良后端继续作为手机基线。
2. ZipVoice仅可选；用户报告手机效果不好。Mac通过或RTF不能覆盖该反馈。
3. F5在独立CrispASR端口英文RTF约70，中文参考短句约117；不集成。其他ggml项目的F5 GGUF不能直接当audio.cpp包，不能只改名字。
4. Whisper只是独立whisper.cpp基线，未合并。VITS AISHELL3只是Sherpa对照，8kHz与内容错误不适合据此推荐默认。CosyVoice/MeloTTS/官方Qwen3另有中文路线，但本轮没有将它们新模型导入SDK。
5. **不要恢复“全predictor生命周期复用”**：此前虽降内存但波形明显改变，已拒绝。首版只改PL-BERT也在取消后复用时暴露输入缓存问题；交付补丁保护持久position/type输入，用`vendor/speech/`锁定版本，不能回填旧画像树。
6. SenseVoice VAD未检测到语音时，旧路径错误回退整段转写，已修正并用非零低幅信号验证。默认无内部VAD，只保护精确数字静音；配置显式Silero路径后才做离线VAD，不是实时endpoint。
7. 修复旧`ortts-download-manifest-v1`中runtime描述字符串与新decoder对象的冲突，保留对未知schema和越界路径的拒绝。

## 请主开发组织的宿主工作

- 先阅读SDK和验收记录，再按宿主现有架构分工；不复制OrTTS CLI/画像进程作为产品provider，不改prompt/对话调度来掩盖后端错误。
- 将原自研ABI与新TTS/ASR接到执行器注册层，保留Sherpa兼容路线。界面按模型包语言、音色和离线/增量能力展示，不因名字是streaming就开放partial。未支持的语言/音色明确失败，不静默降级。
- 接入可信模型清单、资产校验和平台G2P依赖；iOS正确嵌入签名eSpeak，Android匹配NDK/STL。不要带Homebrew路径到手机，不直接照搬研究模型许可证结论。
- 通过既有音频转换层处理原生rate/channels，回调快速入有界播放队列，停止时处理CANCELLED/BUSY和旧队列清理。使用小型、可逐出的模型缓存，不按每个音色重复加载权重。
- ASR使用独立录音/输入流和宿主VAD/endpoint；缓冲final与原有真流式partial路线分别验收，保留打断和全双工行为。当前全库互斥不能当作多模型并行服务。
- 先做一个桌面端到端切片：模型下载校验→选择英语Pocket或中文Kokoro→流式播放→停止/切换→SenseVoice final。随后按真实Android/iPhone测试内存、首包、RTF、长句、后台/前台、取消与听感；失败时保留原改良后端。

主开发收到消息/开始组织工作不代表宿主迭代已经完成；需要它自行给出变更、测试、设备证据和验收结果。此仓库本轮只做本地提交，不推送远端。
