# Third-party notices

OrTTS-demo integration code is licensed under Apache-2.0 (LICENSE). Third-party code retains the licenses below. This does not relicense model weights.

| Component | Use | License text |
|---|---|---|
| [audio.cpp](https://github.com/0xShug0/audio.cpp), Copyright 2026 ShugoAI LLC | Native runtime, with OrTTS model/session/streaming integration modifications | [Apache-2.0](licenses/audio.cpp-LICENSE) |
| [ggml](https://github.com/ggml-org/ggml), The ggml authors | Tensor operations and quantized CPU backends | [MIT](licenses/ggml-MIT.txt) |
| [llama.cpp](https://github.com/ggml-org/llama.cpp), The ggml authors | Tokenizer/Unicode code inherited through audio.cpp | [MIT](licenses/llama.cpp-MIT.txt) |
| [speech.cpp](https://github.com/nyosegawa/speech.cpp), Copyright 2026 Sakasegawa | Adapted transposed-convolution GEMM helper | [MIT](licenses/ortts_tconv_LICENSE.MIT) |
| SentencePiece | Tokenizer support | [Apache-2.0](licenses/sentencepiece-Apache-2.0.txt) |
| SentencePiece bundled dependencies | protobuf-lite, Abseil, Darts-clone and esaxx | Corresponding sentencepiece-*-LICENSE.txt files in licenses/ |
| cJSON | JSON parsing | [MIT](licenses/cJSON-MIT.txt) |
| LibYAML | Configuration parsing | [MIT](licenses/libyaml-MIT.txt) |
| utf8proc | Unicode support in enabled runtime components | [Notices](licenses/utf8proc-LICENSE.md) |
| cpp-httplib | Optional upstream HTTP components | [MIT](licenses/cpp-httplib-MIT.txt) |
| Android NDK / LLVM | Distributed Android libc++ runtime | [NDK notices](licenses/Android-NDK-NOTICE.txt) |

The pinned audio.cpp revision and OrTTS patches are recorded in vendor/runtime.lock.json. The speech.cpp adaptation is from commit d074e1b9d84fe5ec530c959292ffe3d94ffd288b; its original copyright notice is retained. No upstream endorsement is implied.

## Model components

Model weights are downloaded separately from the model repository. Qwen3-TTS retains Apache-2.0; Liquid AI LFM-derived weights retain LFM Open License v1.0, including its commercial-use terms. The inherited model-side iSTFT implementation credits [Vocos](https://github.com/gemelo-ai/vocos) ([MIT](licenses/Vocos-MIT.txt)). Runtime licensing does not grant additional rights to those models, speaker recordings or presets.

The distributed APK includes native third-party binaries. Corresponding notices must accompany binary releases; future APK builds include this file and the license texts under assets/licenses/.
