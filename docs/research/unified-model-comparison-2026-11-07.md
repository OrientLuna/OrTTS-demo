# 本机统一 CPU 基线：PocketTTS、ZipVoice、F5 与 Whisper

日期：2026-11-07。设备：M5 MacBook Air，24GB，macOS 27.2（26B123）。这是本机 CPU 兼容性小切片，不代表 iOS/Android 验收，也不代表已交付统一 SDK。没有改 OrTavern 主线。

> 后续要求更新：已补中英文混读测试；随后用户明确接受单语言，因此混读不再是所有默认候选的强制门槛。当前语言与音色评估见[languages-and-voices](languages-and-voices-2026-11-07.md)。新增实测中ZipVoice通过自动回读检查，Kokoro当前中文前端未通过，Pocket英语包不适合作默认。详见[混合验收](mixed-zh-en-acceptance-2026-11-07.md)。

## 结论和边界

PocketTTS English Q8、ZipVoice Distill Q8 已通过现有 audio.cpp 的独立多模型构建合成，Piper、Kokoro、Kitten作同机对照；SenseVoice、Moonshine作ASR对照。Whisper是独立 whisper.cpp v1.7.6，而不是把其名字注册到当前audio.cpp。F5另见下节，不能把其他项目的GGUF直接当作audio.cpp包。

所有TTS输入同一句：`At nine thirty, please check the train ticket and call the station.`，seed42，CPU四线程，Release，Metal/CUDA/OpenMP关闭。Piper合成的另一句 `The northern wind crossed the quiet harbor.` 为ZipVoice和F5的合成参考音频，无私人说话人素材。参考音频用于技术测试，不作为克隆质量基准。

每个模型独立进程连续测两次、顺序运行，未清理系统文件缓存。它是短句冒烟性能对照，非充分统计基准；线程数一致不保证不同图或Accelerate内部的调度完全一致。不同模型生成时长和语速不同，因此RTF与CPU秒都应看，不能只按RTF推断质量、架构优劣或电池耗电。

下表内存统一为操作系统记录的**进程峰值RSS，MiB**，避免把macOS物理footprint与RSS混用。CPU秒=user+system，含加载、推理、退出，四核工作一秒可产生约四CPU秒。RTF=推理墙钟/音频时长，小于1快于实时。功率与焦耳未测；CPU秒只能作为计算成本近似，不能称为耗电实测。

| 模型/精度 | 资产大小 MiB | 输出或输入 s | 推理RTF（两次范围） | 峰值RSS MiB | 全进程CPU秒 |
|---|---:|---:|---:|---:|---:|
| Piper Lessac medium orig | 59.8 | 3.692输出 | 0.068–0.071 | 194 | 1.02–1.05 |
| PocketTTS English Q8 + alba | 122.0 + 5.9 | 3.040输出 | 0.127–0.167 | 489–496 | 1.38–1.58 |
| Kitten mini 0.8 orig | 288.2 | 5.592输出 | 0.437–0.438 | 908–931 | 9.63–9.67 |
| Kokoro 82M Q8，原版 | 180.8 | 4.150输出 | 0.470–0.480 | 1211–1272 | 8.23–8.37 |
| Kokoro，仅PL-BERT候选复用 | 同上 | 4.150输出 | 0.450–0.462 | 1141–1142 | 8.04–8.22 |
| ZipVoice Distill Q8，默认8步 | 151.0 | 3.509输出 | 0.842–0.847 | 298–301 | 11.24–11.71 |
| F5 v1 Base F16，独立32步基线 | 952.8 | 3.861输出 | 69.645–74.312 | 1104–1107 | 981.64–1056.49 |
| Moonshine streaming tiny Q8 | 57.6 | 3.692输入 | 0.0075–0.0080 | 172–173 | 0.15–0.16 |
| SenseVoice small Q8 | 242.4 | 3.692输入 | 0.0267–0.0274 | 497–498 | 0.45–0.46 |
| Whisper base F16，独立基线 | 141.1 | 3.692输入 | 0.0748–0.0939 | 351–352 | 0.94–1.09 |

Whisper使用其计时`total-load`，包含少量初始化，无法假装与audio.cpp API计时边界完全等价。其他模型使用CLI `metrics.wall_ms`，不含会话构造。全进程墙钟也保存于JSON：Piper0.289–0.300s、Pocket0.434–0.653s、ZipVoice3.093–3.151s、Kokoro原版2.686–3.076s、Whisper0.333–2.458s。Whisper第一次启动有明显额外开销，不能拿2.458s当其纯推理耗时，也不能将0.333s声称冷启动性能。

## Kokoro：82M为什么超过1GB

82M指8200万参数，不是82MB。仅按参数数算，F32约328MB十进制，F16约164MB，Q8约82MB，但实际包有混合精度、量化元数据、音色和附属资源；本次Q8 GGUF实际189,550,976字节。

推理峰值还包括权重执行副本、PL-BERT/时长预测/F0/声码器激活、卷积展开与图缓冲、allocator保留页。此前较长英文中探针记录权重backend约281.6MiB；PL-BERT中间张量约232.5MiB，predictor tail约236.7MiB，声码器graph约247.4MiB，其中单个展开节点约176.6MiB。这些分配有不同生命周期，不能全部直接相加。详细记录见[内存定位](memory-and-framework-support-2026-11-07.md)。

所以当前高占用**有这份模型移植/图分配实现的因素，也有模型激活和句长的因素**；没有证据说ggml必然要这么多内存，更不能由此断言ONNX一定更省。需要同权重/文本/音色/输出质量的后端A/B才能判断框架差异。多次create/run/free结果尚未证明稳定泄漏，不能混称“内存泄漏”。

只改PL-BERT生命周期复用的候选与原版固定seed WAV逐字节一致。此前较长英文ABBA物理footprint1617→1386MB（约14%），中文混合单次2094→1646MB（约21%）。本轮短句峰值RSS降幅更小，说明收益依赖形状、allocator和指标。全面复用predictor的方案虽然更省，却改变波形，已拒绝。候选补丁仍未回填生产源树，未认证移动端/GPU。

## 自动正确性检查与试听

六个TTS（含独立F5）输出PCM均有限、非空；Whisper base回读均覆盖完整目标句，差别主要是`nine thirty`被写为`930`或`9.30`以及标点。ASR三者识别同一Piper音频也覆盖目标句。这不是人类听感认证，base的回读也不能证明无发音问题。

Moonshine包名含streaming，但当前audio.cpp接线的process_audio_chunk只累积音频、finalize才转写，不能据此宣称已支持实时partial。ZipVoice是文本分块合成，不等于原生逐帧增量生成。Pocket本轮只测离线合成，首包延迟、背压与取消另需验收。SenseVoice此前纯静音仍产生`I.`，不能因本次正样本通过就忽略其VAD/空段逻辑缺陷。

试听文件位于`outputs/unified-2026-11-07/{piper,pocket,zipvoice,kitten,kokoro-baseline}-1.wav`。F5试听为同目录`f5-native-1.wav`。原始日志、逐项JSON、回读文本留在同目录，不提交模型和音频。

## 来源和复现

- [audio.cpp代码](https://github.com/0xShug0/audio.cpp/tree/e9303b76983993cc59576bf6d16d8a0635ae4d85)，独立准备树/画像树，CPU ARM `armv8.2-a+dotprod+i8mm+fp16`；画像树仅PL-BERT候选改动和分配日志。
- [Pocket/Piper/Kokoro/Kitten/Moonshine包](https://huggingface.co/audio-cpp/audio.cpp-gguf/tree/57de533382ad47d5527e7562d1f80c41f769553b)，具体SHA见工具manifest。
- [ZipVoice GGUF](https://huggingface.co/davidxifeng/zipvoice-gguf/tree/cf07ad4c9f87cf4b5cd99e140d6935b157c41347)，[官方代码](https://github.com/k2-fsa/ZipVoice)。
- [Whisper v1.7.6](https://github.com/ggml-org/whisper.cpp/tree/v1.7.6)，[base资产固定revision](https://huggingface.co/ggerganov/whisper.cpp/tree/5359861c739e955e79d9a303bcbc70fb988958b1)。
- [Kokoro官方82M说明](https://github.com/hexgrad/kokoro)。

测量入口：`tools/compatibility/compare_local.py`。完整结果：`benchmarks/unified-models-macos-20261107.json`。下载manifest：`tools/compatibility/four-assets.json`和`f5-assets.json`，加此前`assets.json`和`extra-assets.json`。`fetch_assets.py --manifest <manifest> --out local/compat/assets`会校验尺寸与SHA。默认比较不应将缺失资产误报为兼容失败，需先准备指定模型。

## 接入建议

- 马上保留PocketTTS与ZipVoice的CPU CLI小切片，用人工试听决定是否纳入候选；不要把CLI成功等同于移动端FFI、流式与取消成功。
- 优先回填可逐字节验证的Kokoro PL-BERT补丁，继续定位predictor的别名/跨图输出生命周期；拒绝用错误波形换内存下降。
- Whisper可先作为独立执行器，ASR必须有输入流、partial/final、endpoint/reset；后续若合并ggml，需按其固定版本算子和ABI做兼容验证，不能直接同进程链接两份导出同名ggml的库。
- F5应先验证其独立基线质量与开销，再决定移植包格式或流水线。不要直接把CrispASR整个全模型库引入当前工程。最小原生探针约2.6MiB（未strip），其ggml三库约1.74MiB，另有约57KiB BLAS插件；这些是本机开发产物，不是移动端发布体积。庞大的完整源码构建不等于部署必须全部携带。
- 当前已验证的是部分模型共用audio.cpp/ggml，另有Whisper/F5独立基线；尚未实现“一套底层兼容全部”。其他后端是否值得并入，需要模型级正确性和实测资源成本决定。

## F5：资产格式与独立基线

本轮选择[cstr/F5-TTS v1 Base F16](https://huggingface.co/cstr/f5-tts-GGUF/tree/28d4461e4706df2c44e5e5b93d462b98dc94732e)，999,097,152字节，DiT+Vocos打包。模型权重CC-BY-NC-4.0，不能把上游MIT代码许可证当作权重许可证。模型卡的量化误差推论未在本轮验证，不据此推断所有F5量化路线不可行。

当前audio.cpp直接加载报`does not embed an audio.cpp model spec`。头部检查还发现`f5.*`/`voc.*`张量命名，而当前audio.cpp期望`transformer`/`vocos`命名并另读`vocab.txt`；该包词表在`f5.vocab`元数据。因此`--model-spec-override`不能单独解决，不能宣称兼容。没有做盲目改名或将不同shape强行解释。

独立基线采用发布者指定的[CrispASR](https://github.com/CrispStrobe/CrispASR/tree/34a3f0007b949a0868fc99c3c43d8920ec3e5e64)的`f5-tts`目标和本仓库小探针，不携带完整CLI；CPU4、seed42、32步、CFG2、sway−1。探针先做24k参考PCM、按其CLI提升低RMS，然后直接调用F5 C接口，分别量加载、参考准备和合成。发布者内部参考预处理从2.28s截出2.04s；这是其默认流程，并非所有克隆模型具有完全相同前处理。

首次合成3.861s输出用了268.921s（RTF69.645），全进程271.968s、981.644 CPU秒，峰值RSS1106.6MiB；加载284.8ms、参考准备8.9ms。一次1秒`sample`取样显示DiT的`ggml_compute_forward_mul_mat`、`ggml_vec_dot_f16_f32`/`ggml_vec_dot_f32`是热点，非停在下载/加载；第一次计时包含这次采样的小额扰动。该结果只能说明**此版本F5端口的此CPU配置很慢**，不是F5所有实现或ggml所有模型的结论。Vocos只用了约193ms，不是主要瓶颈。

第二次F5合成286.943s（RTF74.312）、全进程287.193s、1056.489 CPU秒、峰值RSS1104.1MiB，输出仍为3.861s。首次音频经Whisper回读，结果为`At 930, please check the train ticket and call the station.`；没有据此宣称人工听感通过。复测比首次慢约6.7%，本轮未测温度/功耗，不归因于已证实的热降频。

F5两次原始F32 PCM的SHA256完全相同，说明本次固定seed重复输出一致。
