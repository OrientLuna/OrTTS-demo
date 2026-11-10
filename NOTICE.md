# Third-party notices

OrTTS-demo integration code is licensed under Apache-2.0 (LICENSE). Third-party code retains the licenses below. This does not relicense model weights.

| Component | Use | License text |
|---|---|---|
| [audio.cpp](https://github.com/0xShug0/audio.cpp), Copyright 2026 ShugoAI LLC | Native runtime, with OrTTS model/session/streaming integration modifications | [Apache-2.0](licenses/audio.cpp-LICENSE) |
| [ggml](https://github.com/ggml-org/ggml), The ggml authors | Tensor operations and quantized CPU backends | [MIT](licenses/ggml-MIT.txt) |
| [llama.cpp](https://github.com/ggml-org/llama.cpp), The ggml authors | Tokenizer/Unicode code inherited through audio.cpp; optional native LiquidCodec integration | [MIT](licenses/llama.cpp-MIT.txt) |
| [speech.cpp](https://github.com/nyosegawa/speech.cpp), Copyright 2026 Sakasegawa | Adapted transposed-convolution GEMM helper | [MIT](licenses/ortts_tconv_LICENSE.MIT) |
| SentencePiece | Tokenizer support | [Apache-2.0](licenses/sentencepiece-Apache-2.0.txt) |
| SentencePiece bundled dependencies | protobuf-lite, Abseil, Darts-clone and esaxx | Corresponding sentencepiece-*-LICENSE.txt files in licenses/ |
| cJSON | JSON parsing | [MIT](licenses/cJSON-MIT.txt) |
| LibYAML | Configuration parsing | [MIT](licenses/libyaml-MIT.txt) |
| utf8proc | Unicode support in enabled runtime components | [Notices](licenses/utf8proc-LICENSE.md) |
| cpp-httplib | Optional upstream HTTP components | [MIT](licenses/cpp-httplib-MIT.txt) |
| Optional LiquidCodec dependencies | nlohmann/json, miniaudio, stb, xxHash, rotate-bits, SHA helpers and subprocess.h | Corresponding license texts in licenses/ |
| jieba / cppjieba | MIT-derived ZipVoice Chinese segmenter in the optional speech build; embedded model dictionaries are separate assets | [MIT attribution](licenses/zipvoice-jieba-MIT.txt) |
| eSpeak NG 1.52.0 in expanded mobile Demo | Shared G2P library/data for Kokoro, Piper and Kitten; SDK-only Pocket/ASR can still omit it | [GPL-3.0-or-later](licenses/espeak-ng-GPL-3.0.txt); combined mobile distributions must meet GPL source/license obligations, not merely the repository's Apache license. `tools/build_mobile_g2p.py` produces the corresponding eSpeak source archive; distribute it together with matching OrTTS source/build instructions. |
| Android NDK / LLVM | Distributed Android libc++ runtime | [NDK notices](licenses/Android-NDK-NOTICE.txt) |

The pinned audio.cpp revision and OrTTS patches are recorded in vendor/runtime.lock.json. The speech.cpp adaptation is from commit d074e1b9d84fe5ec530c959292ffe3d94ffd288b; its original copyright notice is retained. No upstream endorsement is implied.

## Model components

Model weights are downloaded separately from the model repository. Qwen3-TTS retains Apache-2.0; Liquid AI LFM-derived weights retain LFM Open License v1.0, including its commercial-use terms. The inherited model-side iSTFT implementation credits [Vocos](https://github.com/gemelo-ai/vocos) ([MIT](licenses/Vocos-MIT.txt)). Runtime licensing does not grant additional rights to those models, speaker recordings or presets.

The distributed APK includes native third-party binaries. Corresponding notices must accompany binary releases; future APK builds include this file and the license texts under assets/licenses/.

## Optional speech assets (reviewed 2026-11-07)

### MOSS Nano APK integration (parent review 2026-11-10)

MOSS-TTS-Nano-100M and MOSS-Audio-Tokenizer-Nano retain Apache-2.0, including
Copyright 2026 OpenMOSS Team, Fudan University, Shanghai Innovation Institute,
and MOSI attribution in [the upstream license](licenses/MOSS-TTS-Nano-Apache-2.0.txt).
The fixed GGUF is from `audio-cpp/audio.cpp-gguf` revision
`ae77d06579f5ed1be99dd7614d99929e76a46d9e`; its mixed-repository top-level
`other` label does not replace the original component licenses. Model/card
identity receipts are bundled alongside the full license. The small female/male
reference WAVs are existing published OrTTS synthetic presets, with original
WAV identity and exact transcript recorded in the catalog; they are not Qwen
speaker-vector inputs. Weights are not bundled in the APK or committed.
No change to existing eSpeak GPL obligations or a claim of zero legal risk is
made by this addition. Existing audio.cpp/ggml/SentencePiece notices are retained.

The model catalog is a compatibility/verification example, not a cleared distribution bundle. See [license and expansion review](docs/development/speech-license-and-expansion-2026-11-07.md). Model weights, preset embeddings, source recordings and phonemizer dictionaries retain their own terms.

- Kokoro and Kitten model cards identify Apache-2.0; Moonshine streaming tiny identifies MIT. Keep the relevant model notices as well as these runtime notices.
- Pocket TTS model weights identify CC-BY-4.0; voice origins require separate attribution. The sampled alba/anna/george origins are documented separately in the catalog; not every Pocket voice is permissively licensed.
- The tested ZipVoice-Distill Emilia checkpoint is subject to the upstream non-commercial statement (CC-BY-NC), despite the converter's Apache-2.0 label. Conversion cannot enlarge rights. It is not a cleared default distribution asset.
- The tested Piper Lessac card links a research-only dataset license. This is an unresolved distribution-rights review, not a blanket conclusion about every Piper voice.
- SenseVoice uses the linked FunASR model agreement, not Apache-2.0 for its weights. Attribution, model-name and other agreement terms apply.

The integration code's Apache-2.0 license is unchanged. A host combining GPL-covered components must evaluate the resulting distribution and provide the corresponding source/build material where required; using dynamic loading is not an automatic exemption. No complete binary distribution compliance certification is asserted by this notice.
