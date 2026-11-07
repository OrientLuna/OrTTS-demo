# 单语言与固定音色抽样

2026-11-07。最新要求接受单语言，英文模型可以保留；中文单独评估，同句混读作为附加能力，不再是所有候选的门槛。用户反馈ZipVoice在手机上效果不好，这属于用户已有设备经验，本轮未重测手机，也不以Mac结果覆盖该反馈。现有改良后端继续作为手机端基线。

## 本轮范围

M5 MacBook Air 24GB、CPU4、固定seed42，每个音色一次。Kokoro仍使用此前PL-BERT候选CPU构建，不是生产SDK；Pocket English Q8、Kitten mini 0.8 orig与此前相同。声音按固定名单抽样，不遍历全部。每个成功输出做PCM检查、Whisper base回读；音色辨识/自然度/说话人相似度待人工试听，不能由波形不同替代。

中文：`今天上午九点半，请检查车票和随身行李。`

英文：`At nine thirty, please check the train ticket and call the station.`

| 模型 | 本次固定音色 | 输出秒 | RTF | 峰值RSS MiB | 自动回读 |
|---|---|---:|---:|---:|---|
| Kokoro中文 | zf_xiaobei、zf_xiaoyi、zm_yunjian、zm_yunxi | 4.850–5.575 | 0.459–0.506 | 984–1003 | 四项均保留完整句子 |
| Kokoro英文 | af_heart、am_adam、bf_emma（英音） | 4.150–4.275 | 0.465–0.489 | 1141–1169 | 三项保留完整句子 |
| Pocket English | alba、anna、george | 3.040–3.920 | 0.129–0.143 | 488–567 | 三项保留完整句子 |
| Kitten English | Bella、Leo | 5.592–5.717 | 0.441–0.449 | 988–993 | 两项保留完整句子 |
| F5 v1 Base中文，英文参考 | 克隆参考与此前英文基线相同 | 1.088 | 87.619 | 1087 | 明显截断，未通过 |
| F5 v1 Base中文，匹配中文参考 | 克隆参考为Kokoro小伊合成样本 | 2.037 | 116.933 | 1107 | SenseVoice完整；Whisper有字词误差，待试听 |
| 中文VITS AISHELL3，Sherpa独立基线 | sid0、21、100（共174） | 3.373–5.915 | 0.0163–0.0167 | 178–188 | Whisper回读错误较多，未通过自动内容检查 |

Kokoro同语言不同voice输出SHA不同，Pocket三个embedding输出也不同；没有看到相同输出冒充切换音色的情况。Kitten首轮探针错误地发送其接口不接受的`language`选项，修正探针后Bella/Leo都成功；不能把该参数错误归类为模型不支持英语。Pocket额外下载anna/george两个embedding约14MB，固定revision/SHA见`tools/compatibility/voice-assets.json`。

## 中文候选判断

- **Kokoro**：本轮四个纯中文音色通过自动完整内容检查，值得继续听感与手机内存验收。此前混读异常不能扩大解释为纯中文也不支持。现有端口仍有接近1GiB的RSS，不能直接作为手机推荐。
- **F5**：[官方模型](https://github.com/SWivid/F5-TTS)覆盖中文/英文，但本机独立CrispASR端口用英文参考读中文时只产生1.088s，不通过。日志`ref_T=192 duration=294`，目标只剩102 mel帧；时长估计明显不足是直接线索。尚不能单凭该线索认定是唯一问题，已追加中文参考复测，见下文。
- **Qwen3-TTS**：[官方](https://github.com/QwenLM/Qwen3-TTS)支持中文和英语，有预置说话人与克隆路线。是已有自研路径的相关对照；本轮未另下载官方CustomVoice权重或将已有自研0.6B/1.7B结果冒充官方原版测试。
- **CosyVoice**：[官方](https://github.com/QwenAudio/CosyVoice)支持中文等语言，有零样本克隆路线；当前audio.cpp有CosyVoice3实现，但未在本轮下载完整包、未本机验收，不宣称可直接部署手机。
- **MeloTTS**：[官方](https://github.com/myshell-ai/MeloTTS)支持中文等语言，属于可考虑的传统TTS路线。本轮未跑其权重，不把“有中文模型”混称“当前OrTTS已兼容”。
- **中文VITS/Matcha**：Sherpa提供[中文VITS及Matcha包和用法](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/offline-tts.py)。本轮只测VITS AISHELL3，不代表所有VITS或Matcha质量。它与现有Piper port同属相关架构并不意味着能直接导入当前audio.cpp。

## 新增中文VITS的限制

官方发布包`vits-icefall-zh-aishell3.tar.bz2`，asset ID160855141、2024-04-08发布，31,559,701字节；模型30,482,262字节，**输出8kHz**。不是与24kHz模型同等音质的公平速度比赛。测试用本机已安装sherpa-onnx Python1.13.8/ONNX CPU4；进程RSS和CPU包含Python导入，不能当作纯C++运行时体积或同模型后端A/B。

只提取model/lexicon/tokens/speakers与phone/date/number FST。包内还有约172MiB的可选`rule.far`，本例未提取或加载；这是“附属资源体积”与“权重大小”需要分开的实例。发布metadata未给digest，本地SHA作为下载收据，不能称为与独立上游SHA核对通过。许可证不能由Sherpa代码许可证自动推断为数据/模型许可证，本轮不做商用授权结论。

## 复现与交付

- `tools/compatibility/check_voices.py`：固定音色抽测及F5英文参考中文实验。
- `tools/compatibility/check_vits_zh.py`：官方VITS三个speaker的独立ONNX基线。
- `tools/compatibility/check_voice_followup.py`：修正Kitten请求、VITS回读及F5中文参考诊断复测。
- `benchmarks/voices-and-languages-20261107.json`与`vits-zh-voices-20261107.json`：逐项资源、参数、回读和资产收据。
- 音频：`outputs/voices-2026-11-07/`。不提交权重、音频，不改OrTavern或生产路由。

## F5中文参考复测结果

使用Kokoro小伊合成的完整中文参考与准确匹配的参考文本，目标改为`欢迎使用本地语音合成。`。仍为独立F5 v1 F16、CPU4、32步、seed42。参考原长4.975s，发布者的默认内部预处理截为3.51s（`ref_T=330`），生成191 mel帧，得到2.037s输出。推理238.232s、RTF116.933、峰值RSS约1107MiB。

SenseVoice回读`欢迎使用本地语音合成。`，Whisper回读`欢迎使用本地与银合成。`。本例证明中文参考下可以产出完整中文短句，不代表音质、任意中文长句或移动性能验收通过。与英文参考实验的目标文本也不同，不能称严格单变量A/B或认定参考语言是唯一原因。源码时长估计、内部参考裁剪与转写长度的关系仍需单独诊断。

VITS三个音色另用SenseVoice复查，仍出现“摄像/摄效”等替换、漏字；结合Whisper结果，不将错误全部归因于某一个识别器，保留待人工试听。该8kHz包不是当前推荐的高音质手机方案。F5无有限预置音色表，本轮是两类合成参考的克隆诊断，不能把它们当作官方预置音色。
