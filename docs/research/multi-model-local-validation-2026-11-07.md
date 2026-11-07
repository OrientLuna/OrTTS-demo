# 多模型单底层本机验证结果

> 后续集成更正：首次PL-BERT候选在取消后复用时暴露固定位置/类型输入被graph allocator复用的问题。当前补丁已将这两组持久输入标记为输出保护，并增加同配置eager A/B、取消/复用与真实C/Rust验收。历史统计保留为当时结果；交付状态以[多模型SDK](../../runtime/SPEECH.md)及`vendor/speech/`锁文件为准。

2026-11-07。Apple M5 MacBook Air，24GB，macOS ARM64，CPU四线程、DotProd/I8MM/FP16，无GPU。测试为独立切片，不改OrTavern、不替换现有OrTTS ABI1或App默认实现。新增可复现探针在 `tools/compatibility/`，机器结果在 `benchmarks/multi-model-macos-smoke-20261107.json`。

## 结论

**技术执行兼容已得到实证：同一份audio.cpp共享库、同一ggml后端和同一组C ABI，可以顺序执行Kokoro、Piper、SenseVoice；不需要ONNX Runtime执行这些路径。** 这比统一接口更进一步，是本次所选模型的共同底层验证。但不能据此承诺所有模型都支持，或声称已经完成生产SDK迁移。

本切片选择四个family：`kokoro_tts,piper_tts,sense_asr,qwen3_tts`；registry报告6个family，另两个是构建自动带入的Silero和MarbleNet VAD。新库中实际执行了前三者；Qwen仅注册，不能把历史自研测试冒充这次新库回归。主工程C ABI仍固定自研模型，候选库是上游泛化 `audiocpp_*` ABI，是否稳定封装为新版OrTTS合同仍待后续小改造。

**当前不能直接回填为默认的两个原因：** Kokoro峰值内存偏大；SenseVoice静音路径存在可复现逻辑问题。人工听感、同模型ORT数值对照、iOS/Android尚未完成。

## 资产与构建

使用既有已准备的audio.cpp源树 `_work/runtime-apple`，锁定base `e9303b76983993cc59576bf6d16d8a0635ae4d85`，包含本仓库原有补丁。本轮没有改该源树。固定资产下载清单见 `tools/compatibility/assets.json`，本次均验证大小及SHA256：

| 模型 | 维护者资产 | 文件大小（十进制） |
|---|---|---:|
| Kokoro v1.0 Q8_0 / 54音色 | audio-cpp/audio.cpp-gguf @57de533382ad47d5527e7562d1f80c41f769553b | 189,550,976 B |
| Piper en_US-lessac-medium orig | 同仓库、同revision | 62,662,016 B |
| SenseVoice-Small Q8 | FunAudioLLM/SenseVoiceSmall-GGUF-audiocpp @5c3fcfe748a8714216bc135476d5863084fddb72 | 254,211,200 B |

本机新增eSpeak-ng1.52.0及其pcaudiolib依赖，英语G2P使用本机字典。Kokoro中文使用GGUF内的前端资源；没有安装日语MeCab/UniDic，因此不声称日语兼容。没有拉取整套上游模型，也没有使用用户凭据或私人录音。下载总量约506MB，不含既有源码。

## 合成结果与试听

全部正常合成返回码为0；以下WAV均单声道、非空、finite，无样本达到或超过满幅。本次输出为默认PCM16，非剪裁分数只说明保存后数据检查，不能证明量化前不存在削峰、音质或发音正确。

| 样本 | 采样率 | 音频 | 合成API时间 | 物理footprint峰值（CLI报告MB） |
|---|---:|---:|---:|---:|
| Piper英语 | 22050Hz | 5.817s | 0.440s | 256 |
| Kokoro英语女声af_heart | 24000Hz | 6.850s | 3.175s | 1618 |
| Kokoro英语男声am_adam | 24000Hz | 6.575s | 3.103s | 1598 |
| Kokoro中文女声zf_xiaobei，三块流式 | 24000Hz | 18.825s | 9.342s（session trace） | 未独立采集 |
| Kokoro中文数字/中英混合 | 24000Hz | 12.500s | 6.937s | 2094 |

每项一次独立进程，计时不含加载、字典初始化与最终播放；trace/日志也有开销。完整进程耗时另存JSON。不能与之前App或其它设备的热请求RTF直接排名。Kokoro短句RTF约0.46，中文分块约0.50，尚未做最佳线程或NEON生成器调优。

本地试听文件（不提交Git）：

- `outputs/compatibility-2026-11-07/piper-en.wav`
- `outputs/compatibility-2026-11-07/kokoro-en.wav`
- `outputs/compatibility-2026-11-07/kokoro-en-male.wav`
- `outputs/compatibility-2026-11-07/kokoro-zh-stream.wav`
- `outputs/compatibility-2026-11-07/kokoro-zh-mixed.wav`

英语两模型使用相同文本：

> The northern wind crossed the quiet harbor. At nine thirty, please check the train ticket and call the station.

中文分块文本：

> 今天是十一月七日，上午九点三十分的列车即将出发。请检查身份证、车票和随身行李，确认手机电量充足。欢迎使用本地语音合成，祝你旅途愉快。

混合文本（重点试听数字和Latin词，不预设G2P正确）：

> 今天是2026年11月7日，订单编号A123，价格是99.50元。请在下午3:30检查GPU和WiFi设置。

建议人工逐句核对漏字、数字读法、中英切换、长句重音、句间衔接、噪声和尾音。波形finite或ASR回读不能代替此项；本轮尚未人工试听确认。

## ASR 与VAD结果

1. Piper英语音频回读内容基本对应原文，但出现 `harborb` 等字符/数字格式差异；只算闭环结构smoke，不算识别准确率基准。
2. Kokoro中文回读与输入内容大体对应，ITN把日期时间转为数字并出现重复标点；不能证明每个字都发音正确。
3. 独立公开参考音频来自模型作者仓库 `FunAudioLLM/SenseVoiceSmall` @3847d57b6bdf2dd8875cb1508d2af43d80a16bf7 的 `example/zh.mp3`，转为16kHz mono PCM，时长5.616s。未启用VAD回读“开饭时间早上9点至下午5点。”；启用VAD后为“开放时间早上9点至下午5点。”。无人工标注/统计语料，不报告CER/WER通过。
4. **纯零PCM 5s，`audio_chunk_mode=none`识别为 `I.`，失败。** 使用正确Silero资产并启用自动VAD仍返回 `I.`，同样失败。
5. 默认相对VAD路径 `assets/framework/models/silero_vad` 从本工程cwd运行时会报资源不存在；实际权重已经在源码树中，改为绝对 `sense_asr.vad_model_path` 后可加载。它是路径/打包合同缺口，不是“模型根本没有VAD实现”。

源逻辑核对：`src/framework/audio/chunking.cpp::plan_vad_audio_chunks` 在无语音时返回空列表；`src/community_models/sense_asr/session.cpp::run` 将空列表理解为直接全音频 `run_single`。该列表同时用于 `none`（不分段）和VAD无语音，含义发生冲突。后续小修复应区分“NoSpeech / WholeInput / Segments”，或在明确VAD模式且无语音时返回空transcript；不能简单删除所有空plan的回退，否则会破坏none模式。

尚未修改上游源以掩盖该失败；结果报告保留失败证据。`run_smoke.py` 已将非空静音识别列为质量失败，返回0的进程状态不等于产品质量通过。

## C ABI 生命周期和分块合同

- 共享 `libaudiocpp` 下一个registry，三个执行模型依次各加载/释放6轮，每次session连续调用2次，共36次，全部返回成功。
- Piper输出22050Hz、Kokoro24000Hz，探针实际检查frames/channels/rate、非空和每个float finite，并在释放前复制/保存借用PCM；ASR独立使用音频输入和文本结果。没有把ASR硬塞进TTS接口。
- Kokoro callback第一块返回取消，status=4、恰好1个audio chunk；`stream_reset`后同session再次生成3块，callback总260400样本，final也260400样本，24000Hz。
- 释放后RSS最后约168MB，各轮曾在约23–304MB间波动，没有单调无限增长，但只有6轮，不能断言无泄漏；allocator/缓存残留不是零。各次采样和运行时长在机器JSON。
- 仅编译注册Qwen，不认证新共享库中自研Qwen/LiquidCodec的资产与行为；没有原生有状态流式ASR、噪声/麦克风/endpoint或设备中断测试。

## 是否臃肿

相同源、编译配置、Release、macOS单架构，复制后 `strip -x` 删除本地符号；比较不是完整安装包，也不是全模型构建：

| 范围 | 字节 | MiB |
|---|---:|---:|
| 仅Qwen family共享库（仍带上游公共/VAD模块） | 3,863,024 | 3.68 |
| 四family共享库 | 4,479,360 | 4.27 |
| 增量 | 616,336 | 0.59 |
| 四family CLI | 5,116,144 | 4.88 |

CLI和共享库是两个供测试/部署选择的入口，不应为了算总SDK体积把共同静态代码的重复两份都默认装入App。共享库动态依赖libSystem、libc++、Accelerate，源构建未链接ORT。eSpeak通过dlopen调用，不能漏算：dylib约508KiB，完整字典约25MiB，另有pcaudiolib。字典可以后续按已验语言裁剪，不能直接删除认为无影响。

**代码增量不大，模型资源和推理峰值才是目前主要成本。** 此前Kokoro图metadata arena从默认384/256/640调整为64/64/128MiB，英语WAV哈希完全一致，但峰值footprint仍约1620MB，未见收益；不应把这些参数容量等同于实际内存来源。Kokoro混合文本达2094MB，移动端仍是阻塞风险。下一步应测组件激活/算子中间buffer、图生命周期和可用NEON generator，而不是宣称单底层后自动省内存。

## 下一小切片建议

1. 先人工试听以上5个样本，确认希望保留的模型/语言/音色；当前Kokoro是v1.0，不能回填成宿主v1.1-zh/103音色。
2. 在独立源副本补NoSpeech/WholeInput/Segments区别，回归静音、正常参考、none模式、长音频分段；再做同模型Sherpa/ORT基线，避免只证明“能跑”。
3. 为SenseVoice和Kokoro逐组件采集内存；设峰值预算，若移动端超预算则按模型保留必要兼容执行器。继续使用selected families，不扩成全模型发行。
4. 仅在这些门槛通过后，新增版本化OrTTS通用模型合同/ASR接口并完成Android/Apple接线。公共音频合同显式保留22050/24000/16000等采样率。

本轮本地候选构建已恢复为四family配置。模型、音频、下载元数据和构建目录均未提交；脚本、固定资产身份与机器结果可审查。没有修改OrTavern主线，也没有推送新提交。
