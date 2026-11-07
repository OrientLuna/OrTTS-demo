# 语音后端：开源发行审计与兼容扩展

2026-11-07复核。用户最新选择：后端兼容按**完整开源发行**评估；这不自动授权把所有宿主组件重许可。这是工程侧的发行准备审计，不是完整法律授权结论。代码开源、可分发二进制、可分发权重/音色、允许商业使用是四个不同问题。

## 当前交付状态

本地main的`ca630c5`是研究，`525d419`是SDK实装。已有自研P3/P5之外，新增5个TTS和2个ASR：Kokoro、Pocket、Piper、Kitten、ZipVoice；SenseVoice、Moonshine。它们共用一份audio.cpp/ggml，C/Rust接线不是只改名字。macOS真实模型回归通过；iOS/Android只有交叉编译/头文件/符号检查，新增模型还没有手机执行证据。

Kokoro/Pocket/ZipVoice有PCM回调（分别是文本块/codec块/文本块）；Piper/Kitten仅离线。两个ASR目前只有离线或有界输入缓冲后final，没有真实partial或自动endpoint。全库仍串行/BUSY。没有通用ONNX执行器，F5/Whisper/Cosy/Melo未注册进交付ABI。

## 发行结论：已有基础，尚未闭环

OrTTS自有集成代码Apache-2.0，audio.cpp Apache-2.0，ggml MIT，既有NOTICE与大部分基础库许可证已保存。但“根目录有Apache LICENSE”不能证明整个App和所有下载模型都已合规。当前至少还有：

1. 宿主OrTavern的根LICENSE在核查时仍列部分核心/外壳为proprietary。后端完整开源不意味着宿主已开源；若组合分发GPL组件，主开发需确认宿主开源范围、许可兼容与第三方权利，或选择不依赖GPL组件的路线。本轮只读核查，没有擅自重许可宿主。
2. eSpeak GPL组合发行、完整对应源码/构建材料、平台库及字典来源需要按真实发布包落实。当前OrTTS库是`AUDIOCPP_STATIC_ESPEAK=OFF`，按需动态打开外部库，不等于“dlopen免除GPL”。
3. 下载目录的权重、voice embedding、原参考音频和G2P字典需逐资产保留版本、许可证、署名和修改记录。当前catalog是校验样例，所有`distribution_cleared`仍为false，不是发布白名单。
4. 新增ZipVoice中文分词代码的jieba/cppjieba MIT二进制署名已补入NOTICE和`licenses/zipvoice-jieba-MIT.txt`；其他模型资源仍应在模型包中附其各自notice。
5. 实际APK/framework/桌面包应产出“实际携带组件”的SBOM与源码/许可证附件；不能把未打包的框架全算成已携带，也不能漏掉运行时动态装载的组件。iOS实际发行渠道条款与GPL义务需单独核对，不能仅因GitHub开源就宣布可上架。

完整开源使GPL路线可作为方案，而非必然要避开；建议运行时独立组件保留Apache/MIT等原许可证，若应用组合包含GPL组件，则选择兼容的组合发行许可并履行相应义务。此处没有自动把OrTTS或宿主重许可为GPL，也没有把模型数据改许可。

## 当前模型/依赖审计矩阵

下表是2026-11-07所核查的原始来源。转换包固定revision/SHA见catalog；原始模型/音色与转换包之间仍需保存完整来源绑定，主分支最新模型卡不能替代部署资产的最终归档。

| 项目 | 当前证据 | 发行判断 |
|---|---|---|
| Kokoro-82M | [模型卡Apache-2.0](https://huggingface.co/hexgrad/Kokoro-82M) | 可作为开源发行候选；模型notice/训练与音色署名、G2P另核；不是仅靠代码MIT/Apache就全包通过 |
| Kitten mini0.8 | [模型卡Apache-2.0](https://huggingface.co/KittenML/kitten-tts-mini-0.8) | 候选；保留模型声明，预置音色/资源来源与eSpeak另核 |
| Pocket TTS | [模型卡CC-BY-4.0](https://huggingface.co/kyutai/pocket-tts) | 要署名、给许可链接并标记转换/量化；访问条件和音色来源分别核对。不是MIT权重 |
| Pocket alba / anna / george | [官方映射源码](https://github.com/kyutai-labs/pocket-tts/blob/main/pocket_tts/utils/utils.py)分别指向Alba MacKenna casual、VCTK p228、VCTK p315；[来源页](https://huggingface.co/kyutai/tts-voices)标CC-BY-4.0 | 本轮三音色有明确署名路线，转换embedding仍需绑定来源。不能将所有Pocket音色同等处理：同页Expresso/EARS是CC-BY-NC，donation/voice-zero则有CC0来源 |
| Moonshine streaming tiny | [模型卡MIT](https://huggingface.co/moonshine-ai/moonshine-streaming-tiny) | 许可较简单的候选，带MIT文本/版权；不因此宣称当前接口有partial |
| SenseVoice Small | [模型卡指向FunASR协议](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)、[协议v1.1](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE) | 自定义协议，要求来源/作者/模型名等；含行为及修订条款，需按原文审查。不能当作权重Apache-2.0或自动称标准开放许可证 |
| **ZipVoice Distill，Emilia** | [上游模型卡明确权重CC-BY-NC](https://huggingface.co/k2-fsa/ZipVoice)；[转换包却标Apache-2.0](https://huggingface.co/davidxifeng/zipvoice-gguf) | **纠正此前unknown/转换标记：测试的Emilia Distill不进入无限制默认发行包。**若做非商业独立附加包也必须保留限制；需要无限制用途就取得额外授权或改用授权明确的检查点，不能仅改GGUF元数据 |
| Piper Lessac medium | [具体模型卡](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD)指向[研究用途数据许可](https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html) | 权利未清，不进入默认包。不能仅由数据许可直接推断所有衍生权重法律结论，也不能忽略它；Piper每个voice需单独审查 |
| F5 v1 Base | [原权重CC-BY-NC-4.0](https://huggingface.co/SWivid/F5-TTS) | 未集成；非商业权重、当前CPU又慢，不是下一步优先默认方案 |
| 自研路径的Qwen部分 | [Qwen原始0.6B模型卡Apache-2.0](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base) | 不能代替整个自研组合包的许可审计 |
| **自研路径的LFM衍生部分** | [LFM2.5-Audio许可](https://huggingface.co/LiquidAI/LFM2.5-Audio-1.5B/blob/main/LICENSE)，本仓库也保留LFM Open License v1.0 | 存在商业收入门槛：定义为年度收入达到1000万美元的主体不获该协议的商业使用许可；不是无限制Apache/MIT。代码完整开源不会自动消除继承权重限制 |
| eSpeak NG | [GPL-3.0-or-later](https://github.com/espeak-ng/espeak-ng/blob/master/README.md#license-information) | 开源方案可考虑，但需要匹配GPL组合分发义务、源码/构建材料及适用安装信息；不要以动态库边界作免责断言。当前SDK没有静态嵌入它 |
| **Pocket的G2P依赖** | 当前锁定源码走文本conditioner而不是eSpeak | **纠正catalog：Pocket不需要eSpeak；ASR也不需要。**Kokoro/Piper/Kitten及ZipVoice英文前端才列外部eSpeak依赖 |

CC-BY允许商业使用但有署名/变更标记要求；CC-BY-NC不因软件开源就允许商业使用。见[CC BY说明](https://creativecommons.org/licenses/by/4.0/)和[CC BY-NC说明](https://creativecommons.org/licenses/by-nc/4.0/)。声纹、肖像/隐私或参考录音权利也不自动由模型权重许可授予。

## 更广泛兼容：采用“共用底座优先，必要兼容执行器可选”

不建议把每个框架都静态塞进默认库，也不建议承诺一个ggml loader执行任意ONNX/GGUF。当前统一的是选定流水线的ggml底层；加入Sherpa/ORT或CoreML等将是统一接口下的多执行器，必须这样表述。

| 扩展 | 收益与真实状态 | 下一步最小切片 |
|---|---|---|
| **Whisper共享现有ggml** | MIT代码与权重；本轮已做真实编译/链接/中英转写探针，候选只链接现有OrTTS静态ggml档案，符号检查只有一个ggml_init | 将固定版本适配到独立ASR接口，加入模型选项/取消/reset/语言声明，再做长音频与手机测试；本轮尚未注册进SDK |
| **原生中文CosyVoice3** | 当前pin已有该流水线；[具体0.5B模型卡Apache-2.0](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512)，但未下载/执行此包 | 固定1个检查点+必要声学/声纹资产+两种合法参考，测内容/峰值内存/RTF；通过后再裁剪进构建，不能把训练框架可运行当手机证据 |
| **MeloTTS中文** | [具体中文权重卡MIT](https://huggingface.co/myshell-ai/MeloTTS-Chinese)；当前SDK未接入，G2P/BERT/词典均要核对 | 与Cosy先选一个做完整流水线；缺少成熟同ggml port时，保留明确的ONNX兼容执行器，不重新造所有算子 |
| **真流式ASR** | 现在缺的是partial/endpoint/状态语义，不只是模型名单 | 优先Moonshine原生增量状态或宿主已有Sherpa流式Zipformer；为partial/final/endpoint/reset建独立能力，不用循环离线伪装 |
| **更多现有语言/音色** | 一些已有流水线可复用权重和注册层 | 固定对应语言包/合法音色先测；Pocket小模型/新语言若架构变化仍需核对，不假定100M实现兼容全部新版本 |
| **Sherpa/ONNX可选模块** | 扩展VITS/Matcha/Paraformer/Zipformer等已有成熟流水线，通常增加ORT等真实依赖 | 宿主已有Sherpa先复用一份，按需装载；模型包声明executor/schema/hash，核心库不自动打包所有框架 |
| Apple CoreML/MLX等 | 可能利用硬件，但不是跨平台通用替换 | 后续只选具体模型做平台A/B；不凭平台宏宣布支持，不将转换成功当完整G2P/codec可用 |

建议顺序：**发行元数据/署名闭环 → Whisper共享底座接入 → 一个中文新模型 → 真流式ASR → 可选Sherpa兼容模块 → 特定平台硬件优化**。可选模块应支持构建裁剪，宿主按executor+model SHA+profile+session选项缓存，避免每音色重复持有权重。单个包必须说明真实语言、格式、采样率、流式种类、取消粒度和许可，而非只写框架名字。

## 本轮Whisper小切片证据

固定whisper.cpp v1.7.6（commit `a8d002cfd879315632a579e73f0148d06959de36`），复用已下载的base F16权重。先直接用当前ggml头编译失败，缺`GGML_KQ_MASK_PAD`；从其原配头恢复值64的编译兼容定义后，复用当前OrTTS四个静态ggml档案链接成功，未再引入Whisper自己的ggml库。

使用相同probe和解码配置分别跑原配库与共享底座候选，中、英文各一个短样例，转写分别相同；中文本身有识别错误，不是质量通过。仅检查一个ggml_init强定义。详见`benchmarks/shared-ggml-whisper-20261107.json`和`tools/compatibility/shared_whisper_probe.cpp`。这个结果只支持“值得继续移植”，不能推出所有模型尺寸、量化、长音频、GPU、手机均兼容。

没有升级生产ggml pin，没有改变现有ABI，没有新下载大模型，没有重许可宿主。当前SDK仍维持5 TTS/2 ASR；新增Whisper是独立实验，不应被宿主UI提前列成已交付能力。

Pocket依赖补充验证：将`AUDIOCPP_ESPEAK_LIBRARY`和`AUDIOCPP_ESPEAK_DATA`均指向不存在路径，在独立CLI进程中仍成功合成2.48秒音频，退出0。结合当前源码的文本conditioner路径，支持删除该包的eSpeak必需依赖标记；本轮没有卸载系统eSpeak，也不将该测试当完整许可证结论。
