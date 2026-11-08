# Kokoro CPU backend comparison (2026-11-08)

Standalone experiment; does not add Sherpa to the main runtime or change OrTavern.

Host: Apple M5, 24GiB RAM, 10 physical cores. Runtime-configured threads: 4. CPU only. Current OrTTS macOS `arm64-baseline` build uses Apple BLAS. Sherpa 1.13.8 (git 11afbd00), ONNX Runtime 1.28.2, uses `provider=cpu`. Each case runs in a fresh process, creates one engine, then performs four calls. First call is separated; warm values are medians of the remaining three. No playback/callback is timed. Peak RSS is the process high-water mark, not just weight size.

| Pipeline | English warm RTF | Chinese warm RTF | Long English warm RTF | Peak RSS range (MiB) |
|---|---:|---:|---:|---:|
| Current ggml Q8_0 | 0.472 | 0.482 | 0.526 | 1044–1935 |
| Sherpa ONNX INT8 | 0.711 | 0.916 | 0.752 | 512–514 |
| Sherpa ONNX FP32 | 0.272 | 0.318 | 0.296 | 679–744 |

For English, ggml takes 7.031s for the first inference versus 1.949s warm; model creation separately takes 2.618s. Sherpa FP32 takes 0.762s first, 0.892s warm, plus 0.382s creation. The mobile Demo previously destroyed the engine after every request, repeatedly paying first-graph costs. Retaining a bounded current engine is therefore a necessary fix independent of backend selection.

These are practical package/pipeline comparisons, **not a weight-identical tensor-backend ablation**. The ONNX packages are official Kokoro v1.0 exports; the GGUF converter targets `kokoro-v1_0.pth`, but the exact GGUF checkpoint revision was not reconstructed. The chosen voice embeddings (`af_heart`, `zf_xiaobei`) match byte-for-byte between GGUF and ONNX; FP32/INT8 voice tables also match. Q8_0, dynamic INT8, and FP32 are different quantizations. Frontends differ (including lexicon handling). Generated durations differ: English is 4.125s ggml versus 3.273s Sherpa FP32, so compare synthesis wall time alongside RTF. Warm wall times are 1.949s versus 0.892s, respectively. This cannot be attributed solely to the framework.

All nine WAVs passed finite/nonempty/native-rate checks. SenseVoice readbacks preserve the main English and Chinese text for ggml and FP32. INT8 long-sentence readback has extra syllables at boundaries; original results are retained. ASR is a diagnostic, not a listening-quality certificate. No randomized multi-session or thermal/power study was performed. These numbers are not iPhone measurements.

Raw timings, hashes, waveform metrics, voice identity and transcripts: [benchmark JSON](../../benchmarks/kokoro-backend-ab-macos-20261108.json). Generated samples remain in local ignored `outputs/kokoro-ab-macos-20261108/`.

## Reproduce

Use locally prepared models and matching Sherpa headers/static libraries; no downloads are performed by the harness:

```sh
python3.12 experiments/kokoro-ab/run.py \
  --sherpa-lib-dir /path/to/sherpa-onnx-v1.13.8/lib \
  --sherpa-header /path/to/v1.13.8/c-api.h \
  --ggml-install build/demo-unified-macos/install \
  --assets local/compat/assets \
  --int8-root local/kokoro-ab/kokoro-int8-multi-lang-v1_0 \
  --fp32-root local/kokoro-ab/kokoro-multi-lang-v1_0 \
  --out outputs/kokoro-ab-repeat --threads 4
```

The current ggml harness uses existing Homebrew eSpeak NG at `/opt/homebrew`; adjust those two paths if reproducing elsewhere. `readback.cpp` reads mono F32 RIFF/WAVE chunks (including afconvert exports), resamples their native rate to 16kHz, and runs the existing SenseVoice package. Filenames containing `-zh` select Chinese. It is a diagnostic helper, not a general audio importer.

Official model assets: [INT8 v1.0](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-int8-multi-lang-v1_0.tar.bz2), [FP32 v1.0](https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_0.tar.bz2). GGUF asset revision and SHA are pinned in `runtime/models/catalog.example.json`. Downloaded weights and third-party binaries are not committed.
