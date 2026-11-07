# 多模型语音运行时研究记录

这些文档是2026-11-07本机研究与独立验证记录；后续实装见[多模型SDK](../../runtime/SPEECH.md)。研究时的候选能力不能直接当作已交付能力。

1. [技术调研与路线](multi-model-speech-runtime-2026-11-07.md)：后端、模型、平台证据和收敛方案。
2. [首轮本机验证](multi-model-local-validation-2026-11-07.md)：Piper、Kokoro、SenseVoice，C ABI生命周期与取消。
3. [内存定位](memory-and-framework-support-2026-11-07.md)：Kokoro分配探针、被拒绝方案与最小候选，Kitten/Moonshine补充。
4. [统一设备对照](unified-model-comparison-2026-11-07.md)：PocketTTS、ZipVoice、F5、Whisper与前述模型，CPU/RTF/RSS。

5. [中英文混合验收](mixed-zh-en-acceptance-2026-11-07.md)：混读成为默认路线门槛，ZipVoice正例与Kokoro当前问题。

6. [单语言与音色抽测](languages-and-voices-2026-11-07.md)：最新要求，中文候选与固定音色样本，不再强制混读。

可复现工具在 `tools/compatibility/`，结构化结果在 `benchmarks/`；权重和试听音频只在本地忽略目录。
