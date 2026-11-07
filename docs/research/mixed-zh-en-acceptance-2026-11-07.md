# 中英文混合能力验收

> 要求已更新：随后用户明确接受单语言，不再把同句混读作为所有默认候选的强制门槛；本文保留为当时实验记录。当前评估见[语言与音色抽测](languages-and-voices-2026-11-07.md)。

2026-11-07当时要求：运行时默认路线必须至少有一个TTS与一个ASR能够处理**同一句中的中文和英文**。分别支持中文模型、英文模型不能自动算混读支持；不能把中文/英文段静默丢弃或用英语模型兜底。

本机M5 CPU4，复用已校验权重，没有新下载。输入：

> 请打开 WiFi，然后说 Hello world。今天的 meeting 在下午三点开始。

TTS采用此前相同seed42与配置。Kokoro用zh/zf_xiaobei；ZipVoice用Emilia中文/英文前端和此前Piper合成的英文参考。输出转16k分别交给Whisper base（zh提示）和SenseVoice（auto），检查混合内容是否保留。回读是自动筛查，不等于人工听感或正式ASR准确率基准。

| 项目 | 结果 | 接入判定 |
|---|---|---|
| ZipVoice Distill Q8 | 3.349s输出，RTF0.790；两种ASR均保留中文、WiFi、Hello world、meeting及时间内容 | 自动混读检查通过，人工试听待确认；当前优先候选 |
| Kokoro Q8 + 中文前端 | 6.800s输出，RTF0.460；两种ASR均把英文片段回读错误 | 当前接线不通过混读验收，不能作为混读默认 |
| PocketTTS English | 本次资产是英语专用，不做中文能力假设 | 仅英语可选，不作为混读默认 |
| Piper Lessac / Kitten English | 已测是英语路线，未验证中文混合 | 不作为混读默认 |
| F5 v1 Base | 独立原生库有中文G2P实现，但未做本轮混合合成；此前CPU RTF69.6–74.3 | 未验收，不因源码写了中文就宣称通过 |
| Whisper base / SenseVoice small | 同一ZipVoice混合音频均保留两种语言内容 | 本例离线混合识别自动检查通过；不等于真流式验收 |
| Moonshine streaming tiny English | 当前资产英语专用，且当前接线只在finalize转写 | 不作为中英混合ASR默认 |

ZipVoice → Whisper原始回读：`請打開 Wi-Fi 然後說 Hello World 今天的Meeting 在下午3點開始。`

ZipVoice → SenseVoice原始回读：`请打开wifi，然后说hello worldl今天的meeting在下午3点开始。`（存在额外l，不能写成逐字零错）

Kokoro → Whisper：`請打開要已然後說Low-R了 今天的內定在下午3點開始。`

Kokoro → SenseVoice：`请打开LE，然后说L world今天的魅定在下午3点开始。`

Kokoro日志还记录`kokoro.skipped_phoneme F/H/g`，表明前端音素到模型词表存在跳过路径，是应调查的直接线索。尚未证明全部读音错误只由这三种音素造成；不把ASR错误直接全归因于TTS。保留原音频供人工判断。

## 后续接入门槛

- 中英混合是默认路线的必需能力；英语专用模型必须显式标注语言限制，选择时不能静默接收不支持的中文请求。
- 当前候选组合：ZipVoice TTS + SenseVoice/Whisper离线ASR。PocketTTS仅作英语可选。此前英语性能表不再单独决定默认引擎。
- 后续扩展验收集：中文主句夹英文、英文主句夹中文、产品名/缩写、数字/日期、长句及文本分块边界；检查音素OOV、漏字、首包与取消。当前只完成一个代表性混合句，不能宣称任意混读都已通过。
- 本轮是独立兼容性探针，未改OrTavern或生产SDK的路由。App接入和iOS/Android仍需分别验收。

复现：`python3.12 tools/compatibility/check_mixed.py`。资产需先准备，脚本不下载。结构化记录：`benchmarks/mixed-zh-en-20261107.json`；试听：`outputs/mixed-2026-11-07/zipvoice.wav`、`kokoro.wav`。原英文基线见[统一设备对照](unified-model-comparison-2026-11-07.md)。
