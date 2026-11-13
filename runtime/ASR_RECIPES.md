# 低配中英 ASR 配方（筛查未通过，未启用默认）

## 2026-11-13 实测更新

两个双语 Zipformer 候选均未通过预先规定的质量门槛，因此不设为默认。SenseVoice 多语言档、Moonshine 英语档保留，低配设备白名单仍为空。下文原型说明中的“候选”不表示推荐下载。

同一 ASCEND test 真人语料固定60条：中文、英文、混说各20条，每类每位说话人10条；只有两位说话人，属于淘汰筛查，不能代替部署验收。参考为数据集人工转写，未由我们重新标注。数据集 revision `737e9800ae31be9932ba8464c80366559bd28424`，parquet SHA `a4c81d2b5ed6124f052089a695972808c16e0ce0c365ec9773c5d1a8fcf043a7`，CC-BY-SA-4.0，音频仅保留本地。

| Mac CPU2，同语料 | 中文 CER | 英语 WER | 混说 MER | 混说英语 WER |
|---|---:|---:|---:|---:|
| 60.4MB small Zipformer，OrTTS 原生 | 11.7% | 50.0% | 49.4% | 94.2% |
| 199MB Zipformer，standalone Sherpa | 9.0% | 40.7% | 46.9% | 93.0% |
| 已有 SenseVoice INT8，standalone Sherpa 离线 | 7.5% | 21.5% | 19.3% | 27.9% |

完整参考、输出、资产 SHA 和采样规则在 `benchmarks/asr-*-quality-screen-20261113.json`。199MB 候选固定 revision `98590b7ed6443e77b714204da2757d75e1a642f4`，模型卡声明 Apache-2.0。离线 SenseVoice ONNX 对照尚未接入本次原生配方，不能将其 Mac 速度当成手机流式表现。英语门槛保持20%，不根据结果放宽。

iOS ARM64 完整运行时和 QA App 已构建、安装；USB 连接恢复。small 模型三轮原生流式/取消恢复测试通过：冷加载466–488ms、热计算RTF 0.0147–0.0156、应用采样 physical footprint 约140–144MiB。这是 iPhone17 高端参照、单条10秒上游样音加速输入，不是实时麦克风或低端认证。[三轮原始结果](../benchmarks/asr-lite-iphone17-20261113.json) 同时记录独立功能样例：已有 ggml SenseVoice 中文、Moonshine 英文均成功；输入长度和内容不同，不作为模型间性能排名。无效测试模型ID曾回退到首个模型，相关无效结果未纳入报告，QA代码已改为直接失败。

官方 iOS SDK 1.13.8 内置源码提交 `793c2405ada0e9ee55a55037fa2d56111b8e7206`，桌面同版本为 `11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf`；二者 ORT 均1.28.2。已分别严格校验，不以版本号相同假定源码相同。iOS SDK 压缩包 SHA `e259a7d3b38ad7dec49bb078252a30bb42ede8355e2bb130cf8c1c78ed131f75`。

官方全功能 SDK 可能携带 TTS/音素化传递依赖，不能只凭顶层 Sherpa Apache/ORT MIT 声称整包分发许可已清查。发布前仍须做传递依赖审计及 ASR-only 裁剪。当前变更未提交或推送。

核对日期：2026-11-13。源码基线 `4c276b2`。SenseVoice 多语言档、Moonshine 英语档保留；不改变已有模型下载或默认 ASR。正式低配默认与设备白名单当前为空。

## 当前实际完成的范围

- [配方、固定资产 SHA、许可和能力](models/asr-recipes.json)。质量未通过的实验配方 `asr-lite-zh-en-v1`，用户名称为「轻量中英」。
- 可选 `ORTTS_ENABLE_SHERPA_ASR` 执行器接入**同一份 OrTTS 原生库**，沿用 `ortts_asr_stream_*` 的 PCM/partial/final/reset/cancel 接口，不另加一套面向用户的后端选择。宿主按配方解析 family，不让用户选择 ggml/ONNX。
- Mac ARM64 原生 C ABI 功能与取消恢复测试通过。该构建是 ASR 兼容原型，不含 LiquidCodec，不能直接替换手机当前完整运行时。
- Android 尚未构建；iOS 已构建且初步真机运行通过，但未完成低配验收；本轮无低配真机质量、冷加载、峰值内存或 RTF 证据，不能声称手机已经集成完成。

统一的是宿主接口和配方，不是 tensor 底层。此可选路径新增 Sherpa-ONNX/ONNX Runtime；默认 ggml 构建保持关闭。没有宣称任意 ONNX 可以导入，也没有添加跟踪主线的 Sherpa submodule。

## 选型与资产

候选为官方 small 双语 Zipformer 的 chunk32 模型，固定仓库：

`csukuangfj/k2fsa-zipformer-bilingual-zh-en-t`，revision `e2382758de9a0219b4efe682b95af30b399db3b8`。

采用 INT8 encoder、FP32 decoder、INT8 joiner，以及 tokens/BPE 文件。各文件完整 SHA/大小/不可变下载 URL 在配方 JSON，原生加载也逐文件校验相同身份，拒绝损坏和越界路径。不下载约458MB的全集压缩包，只取配方需要的约60.4MB文件。FP32 decoder 是官方量化示例的选择，不将“全部 INT8”自动当成质量相同。

参考：[官方小模型列表](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/small-online-models.html)、[上游模型卡](https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/blob/e2382758de9a0219b4efe682b95af30b399db3b8/README.md)。上游示例有混说输出，但不代表我们的语料质量已经通过。

权重模型卡声明 Apache-2.0；Sherpa 代码 Apache-2.0，源码 `11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf` / v1.13.8；ONNX Runtime v1.28.2 为 MIT。许可证文本已放入 `licenses/`，其原始 URL/SHA 与模型卡 SHA 均记录在 JSON。模型卡提及内部训练数据，不能声称已做训练数据权属审计；模型卡、来源及署名应随模型包保留。公开样音的分发许可不能由权重许可自动推导，仓库不提交其音频。

SenseVoice 的自定义模型许可原样保留，不改写为代码许可 Apache-2.0。Moonshine 原有英语模型/MIT记录保留。多语言与音色声明不得代替实际识别验证。

## 能力合同

- 16kHz、单声道、有限 F32 输入，每次1..32000 samples；宿主负责采样率/声道处理。
- 同一模型处理中英，不做两个单语模型的语言切换拼接。支持可修订 partial，显式 flush/段长上限 final；默认15s段长。
- 当前未接自动 VAD、标点、热词或单句语言识别；事件语言标记 `und`。`silence_ms` 必须为0，不把能量门控冒充神经 VAD。
- 配方默认 CPU2、chunk32、greedy search。`update_ms/min_partial_ms` 限制输出更新，不改变锁定模型的 encoder chunk。
- cancel 在 decode 调用之间检查，保持到 reset；reset 重建流状态、保留 recognizer/模型。不能中断任意 ORT kernel，也未实现加载中的取消。
- 所有推理继续共用 OrTTS 进程执行门；不得从回调重入/释放。原有 SenseVoice/Moonshine 接口不变。
- Sherpa 内部缓存大小不可从这版 C API观测。统计结构相应整数返回 `UINT64_MAX`，encoder/decoder 分离耗时返回 NaN，不能当零内存或导出假精确分项。

低内存设备应在任务切换时结束 worker 并释放 TTS，再加载 ASR；反向同理。取消同一 ASR 任务时仍保留模型以便恢复。不能将“执行互斥”误认为“多个驻留模型不占内存”，也不能由 ASR 通过推断自研 Q4 TTS 在2GB手机必然通过。

## 复现原型

提供本地 Sherpa v1.13.8 SDK 前缀，布局为 `include/sherpa-onnx/c-api/c-api.h` 和 `lib/` 下匹配目标的 C API/ORT 库。构建器固定头文件 SHA，并记录实际依赖 SHA；运行时验证 Sherpa版本、源码前缀与 ORT版本。Mac/iOS 使用各自目标 SDK，不跨平台复用二进制。

```sh
python3 tools/build_engine.py --target macos-arm64 --profile arm64-baseline \
  --source /prepared/speech/audio.cpp --speech \
  --sherpa-asr-prefix /local/sherpa-sdk --out build/asr-lite-macos
python3 tools/test_asr_lite.py --build build/asr-lite-macos \
  --assets /verified/model-root --out local/asr-lite-test \
  --report local/asr-lite-macos.json
python3 -m unittest discover -s tests -p test_asr_device_policy.py
```

SDK和模型不由构建器自动下载。编译功能/依赖前缀变化用新目录。兼容依赖必须按目标平台一起打包，不能出现开发机路径或第二份 ORT。发布应进一步使用 ASR-only 构建裁剪；本轮复用本机SDK，未声称是最小发布包。

[本机原始结果](../benchmarks/asr-lite-macos-20261113.json)：独立原生测试程序、CPU2、5条固定上游样音，首条3个新进程，覆盖NaN拒绝、partial早于finish、重复finish、回调/跨线程/idle取消、reset后结果与原识别一致及数字静音不出假文本。新进程冷加载不等于操作系统磁盘缓存已清空；峰值RSS包含该程序内的恢复测试。输入加速回放，不是实时麦克风、热稳定性或手机耗电证据。

这些样音尚无人工核对的参考转写，所以这些样音不计算 CER/WER/MER（另行真人语料筛查见顶部）；模型卡的 AIShell/Wenet数字也不能当成本次 checkpoint/量化方案的验收结果。

## 白名单与验收

规则在 [固定验收门槛](models/asr-acceptance-policy.json)，名单在 [设备白名单](models/asr-device-whitelist.json)。当前 `approved=[]`、`rejected=[]`；未测试与实测失败分开，未知设备不自动下载、不静默降级到英语。

每台设备使用同一套带人工转写与 SHA 的真人语料：至少各20条中文、英语、中英混说，分别包含短/长句、安静/日常噪声、数字与常见英文实体。每次完整记录模型、运行时/依赖、CPU档位、线程、包版本、固件和语料身份，不用合成语音替代真人质量验收。

拟定通过门槛（不是已测结果）：warm compute RTF p95 **严格低于1**，CER≤15%、英语 WER≤20%、混说 MER≤25%且其中英语 WER≤30%；至少3次新进程冷加载p95≤3s，实时输入最后一块到final p95≤1.5s，取消p95≤1s。基于ASR阶段的整个应用峰值，2/3/4GB档预算700/900/1000MiB；另做TTS卸载/ASR加载的任务切换和10分钟实时稳定性检查。门槛如需调整，须在目标试验前明确，不根据失败结果放宽。

- RTF分子为accept/finish实际计算耗时之和，不计等待麦克风/回放睡眠；cold load独立报告，首轮推理与热轮分开。
- Android用实际目标包，记录SoC/核心/内存/OS/温度状态，采样应用PSS；iOS记录硬件型号/内存/OS，采样physical footprint。采样间隔≤50ms，说明采样峰值可能漏掉瞬时尖峰；RSS不能冒充PSS/footprint。
- 取消覆盖回调、跨线程、reset前持续取消、恢复后下一条与新流结果一致；回调不得等UI或音频输出。加载取消尚未实现，单列为限制。
- 型号/OS、原生库SHA、配方identity与协议必须精确匹配才可推荐。RTF不达标、质量/内存/恢复失败的设备明确“不推荐”；新固件/新二进制默认“未验证”，不能只按RAM或A53/A55指令集泛化。
- `tools/evaluate_asr_acceptance.py`计算指标并拒绝证据不全的报告；不会自行写生产白名单。`tools/asr_device_policy.py`返回能力档而不是后端选择。当前是SDK/策略接线，手机UI尚未新增候选下载入口。

待实际设备：2GB A53安卓、3/4GB A55安卓、旧款iPhone（具体型号/内存需设备实测）；iPhone17可作高端参照，不能代替这些目标。2026-11-13本轮检测无ADB真机，iPhone17已恢复USB连接并完成初步原生测试。禁止因此填充假白名单或标记任务已完成。
