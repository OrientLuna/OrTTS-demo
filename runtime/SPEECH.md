# 多模型语音 SDK（可选 CPU 构建）

这是已接线的 OrTTS 后端，不是调研 CLI 的别名。原 `ortts_engine.h` ABI1/P3/P5 保留；新增 `ortts_speech.h` ABI1 和 Rust `speech` 模块。新旧接口在同一个 `libortts`/`OrTTS.framework` 中，共用一份 audio.cpp/ggml 和执行互斥。未引入 ONNX Runtime、whisper.cpp 或第二份 ggml。

## 能力边界

Moonshine 新增独立的 `ortts_asr_stream_*` / Rust `speech::streaming::Stream`，支持可修订 partial、final、flush/reset、取消与有界分段；旧 `ortts_asr_*` 保持 buffered-final。实现与 FunASR 边界见 [验证记录](../docs/development/ggml-streaming-asr-2026-11-07.md)。

| 路线 | 本轮模型资产 | 输出/输入格式 | 增量与限制 |
|---|---|---|---|
| 原 OrTTS P3/P5 | 现有自研包 | 24kHz mono F32 | 原接口保持；原 LiquidCodec 仍需原有可选构建流程 |
| Kokoro | 82M Q8 | 原生24kHz F32 | 文本分块回调；纯中文/英文音色已测，当前混读前端有缺陷 |
| PocketTTS | English Q8 | 原生24kHz F32 | pull codec块转换为回调；英语包不能用于中文 |
| Piper | Lessac medium | 原生22.05kHz F32 | 当前port仅离线；流式配置明确拒绝 |
| Kitten | mini0.8 | 原生24kHz F32 | 当前port仅离线；流式配置明确拒绝 |
| ZipVoice | Distill Q8 | 原生24kHz F32 | pull文本分块；需要参考PCM和匹配转写；用户报告手机效果不佳，保持可选 |
| SenseVoice | Small Q8 | 输入16kHz mono F32 | 离线/有界缓冲后final；中文、英文；可显式配置Silero |
| Moonshine | streaming tiny Q8，增量接口将编码器展开为F16 | 输入16kHz mono F32 | 独立增量接口支持英语 partial/final；有界重叠编码、重复解码；非逐层KV缓存 |

F5、Whisper、VITS ONNX、CosyVoice、MeloTTS不在这个交付库的新模型目录中。F5独立基线很慢；Whisper独立基线未移植；此前VITS是Sherpa独立比较。Piper是模型专用流水线，不是任意VITS ONNX导入器。

模型语言声明来自实际加载包，显式不支持的language返回INVALID。没有自动替换模型。Kitten不声明language请求选项，适配层只设置转写语言，不向它误传该选项；ASR不注入seed。没有中文能力的包还会拒绝Han文本，包括language省略时；这只是脚本范围检查，不是通用语言检测。宿主应明确选择语言和模型，不能用英语ASR自动兜底中文。合法UTF-8、非空文本、选项数组和有限PCM均在边界验证。

## 准备和构建

模型和SDK/工具链均由调用者准备，构建脚本不下载。Python工具使用3.11+，本轮为3.12。

```sh
# --source 指已经由 prepare_runtime.py 准备并通过锁文件检查的原始树。
python3 tools/prepare_speech_runtime.py --source _work/runtime-apple --out _work/runtime-speech
python3 tools/build_engine.py --target macos-arm64 --profile arm64-i8mm \
  --source _work/runtime-speech --speech --out build/speech-macos
```

`prepare_speech_runtime.py`复制源树后应用锁定修正与增量执行器，不改原树：Kokoro PL-BERT生命周期复用；SenseVoice VAD无语音时不再错误地整段转写；Moonshine绝对位置偏移与独立有界增量会话。准备结果有独立receipt，构建工具拒绝未经准备或被改动的源。要复现低内存开关A/B，可在独立构建目录将CMake的`ORTTS_KOKORO_GRAPH_ALLOC`设为OFF；发布构建默认ON，最终回归应记录实际配置。

```sh
python3 tools/build_engine.py --target ios-arm64 --profile arm64-baseline \
  --source _work/runtime-speech --speech --out build/speech-ios
python3 tools/build_engine.py --target android-arm64 --profile arm64-baseline \
  --source _work/runtime-speech --speech --ndk /path/to/installed/ndk \
  --out build/speech-android
```

macOS arm64本轮真实运行；iOS ARM64与Android ARM64做交叉编译和链接检查，**新增模型未做手机真实运行/听感认证**。模拟器、Linux、Windows本轮未验收。不能用平台宏、编译通过或Mac RTF替代设备证据。原Android Demo的JNI接线未改；Rust/其他宿主直接消费新C ABI。既有LiquidCodec可选源码准备/构建入口保留，但本轮未认证与`--speech`组合的模型执行。

同配置增量重建可加`--rebuild`，只接受目标/profile/configure命令/语音补丁receipt相同且未标记BUILDING的目录；改变配置使用新目录。receipt包含源指纹、实际产物SHA与CMakeCache SHA，不包含模型权重。

## 宿主包与依赖

`models/catalog.example.json`是固定资产的宿主清单示例，含revision/尺寸/SHA和已测音色子集。不是运行时自动下载配置，也不代表所有音色和语言都验收过。宿主负责下载、验证、版本选择、缓存与路径解析，再填C配置。

```sh
python3 tools/verify_speech_pack.py --id pocket-english-q8 --root /installed/assets
```

该命令只读校验，不下载；拒绝重复/越界路径、尺寸/SHA不符和缺少model资产。源码、模型、音色、G2P资源许可证分别适用；不能用推理代码许可证代替模型/语料授权。清单中Piper/ZipVoice仍需按其具体资产审查许可，不视为默认发行包。

Kokoro/Piper/Kitten和ZipVoice英文前端使用的eSpeak-ng不是系统内置能力（Pocket与ASR当前不需要）：宿主需带合适的平台库和数据，配置`espeak_library`/`espeak_data`绝对路径。同进程应使用一致的eSpeak库/字典；底层有缓存，环境变量按操作恢复不意味着支持同时混用不同库版本。iOS需嵌入并签名合法库，Android需匹配ABI，并携带NDK的`libc++_shared.so`。Android安装产物会strip，未剥离调试信息留在构建目录，避免将调试体积误算作发布库体积。不能把Mac的Homebrew路径带到手机。新库隐藏audio.cpp/ggml符号，Android保留16KiB页对齐并链接liblog；不要再在同进程加载另一份独立OrTTS库。

## C ABI与生命周期

1. 检查`ortts_abi_version()==1`，新增功能检查`ortts_speech_abi_version()==1`；未开启speech的新版库返回0。旧版库可能没有这个符号，动态加载方需检查符号存在。
2. 用`ortts_tts_create`或`ortts_asr_create`建立拥有模型/session的句柄。设置`struct_size=sizeof(config)`。配置中的字符串/option在调用中消费，模型文件需持续可读。
3. TTS请求每次选择text/language/voice，固定seed可选；ZipVoice提供`reference_pcm`、每通道frames、采样率、channels及准确转写。Piper/ZipVoice没有命名预置音色，不接受任意voice_id来假装切换声音。
4. TTS返回`ortts_speech_audio`，通过原生rate/channels/frames读取交错F32。frames是每通道长度，float数=frames×channels。宿主负责重采样/声道转换与播放；不再假定所有模型24kHz。输入参考/单次输出限120秒，文本限64KiB，长内容由宿主拆分。
5. 回调在生成线程同步执行，借用PCM只在该次回调有效。快速复制/入队；不得重入、释放或等待播放完成。返回非零取消。适配层分别处理主动回调和pull事件/命名音频，不把最终整段音频冒充首包。
6. 所有音频、转写结果和引擎句柄显式free。Rust包装复制到Vec/String后立即释放C结果，句柄Drop释放session；它们故意不是Send/Sync，放在固定worker。

错误读取同线程的`ortts_last_error()`。INVALID=参数/能力不匹配，RUNTIME_ERROR=推理/资产错误，BUSY=其他OrTTS操作在运行，CANCELLED=取消。不要将INVALID/缺少音色静默映射为默认模型成功。每个结果拥有独立音频/文本；读取结果时不依赖下一次模型请求。

### ASR输入和endpoint

`ortts_asr_run`直接接受有限16kHz mono F32；`accept`复制片段到有界缓冲，`finish(language)`转写后释放输入，`reset`丢弃输入。默认60秒，上限120秒；超限返回INVALID，宿主可finish/reset，不能无限累积。缓冲未结束时run被拒绝，防止串话。

旧 `ortts_asr_*` 没有partial、自动endpoint或中间时间戳API；宿主现有VAD/endpoint决定何时finish。精确数字静音返回空串，这是确定性保护，**不是通用VAD**。SenseVoice若配置session option `sense_asr.vad_model_path`为已验证Silero路径，会在离线转写时做VAD分段；未配置则显式禁用内部VAD，不依赖cwd寻找文件。此VAD不是实时endpoint。

旧接口取消为PCM/事件边界检查，离线ASR/TTS只能在compute返回后丢弃结果，不能中断单个矩阵计算。取消不释放句柄；TTS复用前适配层reset。不得与free并发。输入缓冲要丢弃请显式reset，idle cancel不会充当reset。

### Moonshine 增量 ASR

检查 `ortts_asr_stream_abi_version()==1`。`ortts_asr_stream_create` 使用基础 speech config（`family=moonshine_asr`、`streaming=1`、CPU线程1..8）和独立 typed config，不接受旧离线 `max_input_frames`、eSpeak或session options。C结构必须填写 `struct_size`；传NULL流式配置使用默认值。

- 输入固定为有限16kHz mono F32，每次1..32000帧，任意分块大小；内部按20ms推进，尾部不足一块在finish时处理。
- 默认每400ms尝试更新，积累至少1000ms才发partial。partial是当前segment整条假设，宿主应替换，不应把它追加到最终文本。没有稳定token承诺，也没有词级时间戳；start/end是输入段范围。
- endpoint=0表示partial，1/2/3分别表示显式flush、能量静音、段长上限产生的final。segment_id和revision区分段与修订。finish结束当前段，但句柄继续接收下一段；没有新输入时重复finish不重复final。全静音flush可得到空final。
- 默认段长上限15s，可配置1..30s；达到上限会切段，不保证词边界。默认RMS阈值0.003、静音800ms；这是能量门限，**不是神经网络VAD**，噪声可能误触发，较轻语音可能漏检。`silence_ms=0`关闭自动静音结束，由宿主VAD调用finish；能量门限仍用于无语音保护，可调整阈值。
- 编码器采用有界上下文重叠计算，保留段内已提交编码帧；解码器从新cross-memory重新生成假设。编码器固定将Q8权重展开为F16，解码器保持Native；F16已通过数值筛查，Native Q8增量筛查尚未通过，没有把失败模式开放为配置。它是增量输入/输出执行器，**不是逐层KV完全复用实现**。
- 当前段PCM、编码帧、单条假设和临时解码图均受段长上限约束，不保存无限历史转写。模型权重每个句柄独立持有，多个句柄会增加常驻内存，宿主仍需小型引擎缓存。`get_stats`返回当前/峰值PCM、编码帧、输入计数、累计编码/解码耗时，不包含宿主保存的事件或播放缓冲。
- accept/finish同步执行回调，借用字符串只在回调内有效；快速复制/入队，不得重入或free。回调非零或独立cancel均使取消保持到reset；可以从另一线程cancel，检查发生在20ms tick、编码前后及解码token边界，不能中断单个tensor kernel。reset清除音频、假设、分段计数与取消状态；free不得与任何操作/cancel并发。
- INVALID输入不会消耗音频；推理/回调异常后必须reset。取消可能使一次accept只处理部分输入，received计数仍记录该次提供的总帧数，processed记录实际进入tick的帧数。此时不要重送未处理尾部，先reset并重新开始一段。

Rust `speech::streaming::{Stream,Settings,Event,Kind,Stats,Cancellation}` 封装所有权并捕获回调panic，句柄保持!Send/!Sync；`cancellation()`返回可跨线程克隆的取消token，UI可以在推理中取消。token不保活权重，句柄释放后cancel为no-op。`accept`/`finish`返回拥有字符串的事件Vec；`accept_with`/`finish_with`在回调返回true继续、false取消。示例见 `rust/examples/asr_stream.rs`；Swift导入检查见 `examples/ImportSpeech.swift`。

```rust,ignore
use ortts_engine::speech::{Config, streaming::{Stream, Settings}};
let mut config = Config::new("moonshine_asr", "/models/moonshine-streaming-tiny-q8_0.gguf");
config.streaming = true;
let mut asr = Stream::new(&config, Settings::default())?;
for event in asr.accept(&pcm16k)? { /* 用segment_id/revision替换partial或提交final */ }
for event in asr.finish()? { /* flush最后一段 */ }
```

本机验收：C/Rust、跨线程取消、任意分块、reset复用、两会话交错、静音、自动与限长分段；303秒音频加速回放检查RSS平台。固定音色与自然13秒长句另做offline对照。详细记录见 `benchmarks/asr-stream-sdk-20261107.json`、`benchmarks/asr-stream-quality-20261107.json`。iOS/Android仅完成构建和接口检查，**新增ASR手机执行尚未验证**；中文仍使用SenseVoice离线接口。

### 调度、缓存与内存

新旧接口共用进程级try-lock，活跃操作返回BUSY；这是保留旧环境配置依赖的限制，不是已实现并行推理。不要在回调里创建其他引擎或由另一份直接audio.cpp绕过调度。需要全双工低延迟ASR时，宿主现有Sherpa路线应继续保留，不能因统一接口就删除它。

运行时不做无限引擎池、模型下载或自动保活。宿主以模型资产SHA、family、profile和session选项作为缓存键；同一模型换音色用请求字段，避免每音色重复持有权重。设置小型缓存/逐出策略，移动端优先只保留当前模型。Kokoro本轮仍接近GiB级RSS，省内存补丁不等于手机认证。

## Rust示例和验收

```rust,ignore
use ortts_engine::speech::{Config, Request, Tts};
let mut config = Config::new("kokoro_tts", "/models/kokoro.gguf");
config.espeak_library = Some("/embedded/platform/espeak-library");
config.espeak_data = Some("/models/espeak-ng-data");
let mut tts = Tts::new(&config)?;
let mut req = Request::new("你好，欢迎使用。");
req.language = Some("zh"); req.voice = Some("zf_xiaobei"); req.seed = Some(42);
let audio = tts.synthesize(&req)?; // PCM + 原生rate/channels
```

完整Rust闭环见`rust/examples/speech.rs`：Piper原生采样率→宿主显式重采样→SenseVoice离线/缓冲一致→Pocket pull流取消后复用。

```sh
python3.12 tools/test_speech.py --build build/speech-macos --source _work/runtime-speech \
  --assets local/compat/assets --espeak-library /opt/homebrew/lib/libespeak-ng.dylib \
  --espeak-data /opt/homebrew/share/espeak-ng-data --out outputs/speech-acceptance
```

还需保留原ABI回归、模型包验证、Swift头文件导入与Android ELF依赖/符号检查。具体本轮结果见`docs/development/ortavern-speech-handoff-2026-11-07.md`和`benchmarks/speech-integration-20261107.json`。音频听感/音色相似度仍由人确认。

发行状态复核：参见[完整开源发行审计与扩展计划](../docs/development/speech-license-and-expansion-2026-11-07.md)。特别是测试的ZipVoice Emilia Distill权重，上游已明确非商业限制，不能沿用转换仓库的Apache标记；完整开源也不等于模型无使用限制。catalog的license_review是审计记录，不是自动授权。
