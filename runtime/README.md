# OrTTS CPU engine

Embed P3/P5 speech synthesis through a small C ABI, or use the [Rust SDK](rust/README.md).
The runtime supports loading, offline/streaming synthesis and cancellation. It returns
24 kHz mono float32 PCM; playback, model downloads and file saving belong to the host app.

For other TTS and ASR models, see the optional [speech API](SPEECH.md).

## Optional streaming ASR (Sherpa / ONNX Runtime)

Enable `--sherpa-asr-prefix` / `ORTTS_ENABLE_SHERPA_ASR` to include the pinned Sherpa/ONNX Runtime executor for bilingual streaming ASR (`streaming_paraformer`, `zipformer_bilingual`) under the same [`ortts_speech.h`](include/ortts_speech.h) API. Default builds remain ggml-only. See [ASR recipes](ASR_RECIPES.md) for model identities and selection rules.

## Build

Prepare the native sources using the [build guide](../docs/BUILD.md), then build the
library for your target. For example:

```sh
python3 tools/build_engine.py --target macos-arm64 --profile arm64-baseline \
  --source _work/runtime --out build/engine-macos
```

| Platform | Library | Host setup |
|---|---|---|
| Linux / Android | `libortts.so` | Link or load the matching architecture |
| macOS | `libortts.dylib` | Embed the library and configure its runpath |
| iOS | `OrTTS.framework` / XCFramework | Select the device or simulator slice; embed and sign |

Use a baseline CPU profile unless you know the device supports the optimized one.
Apple builds require Xcode; minimum deployment targets are macOS 13.3 and iOS 16.3.
Other build profiles and toolchains are listed in [CPU profiles](../docs/CPU_PROFILES.md).

## C API

Include [`ortts_engine.h`](include/ortts_engine.h). Set each configuration/request
`struct_size`, create an engine, synthesize, then release the audio and engine.
Read `ortts_last_error()` on the calling thread when an operation fails.

- Supply a prepared model directory, P3/P5, a matching voice and the model's manifest identity.
- PCM chunks are borrowed during the callback. Copy or enqueue them without blocking generation.
- Return nonzero from the callback to stop generation.
- Cooperative builds support cancellable loading and synthesis with a fresh token per operation.
  Older libraries may only stop at boundaries or discard the result after compute returns.
- Keep each active handle on a dedicated worker; re-entering the same active handle
  returns `ORTTS_BUSY`, while independent handles (and Sherpa online ASR when enabled,
  detected via `ortts_parallel_inference_version()`) can run concurrently without
  mutating process environment. Do not free an engine during a call or from its callback.

For token ownership and older-library capability checks, see [maintainer notes](AGENT_README.md).

## Rust

The [Rust SDK](rust/README.md) owns native handles and returns PCM in a `Vec<f32>`.
`Task` and `CancelHandle` provide task-scoped cross-thread cancellation; cancelled
operations return `Error::Cancelled`, and the loaded engine can be used again.

Set `ORTTS_LIB_DIR` to the native library directory, or `ORTTS_FRAMEWORK_DIR` to the
parent of the selected iOS framework. For example, on macOS:

```sh
ORTTS_LIB_DIR="$PWD/build/engine-macos/install/lib" \
DYLD_LIBRARY_PATH="$PWD/build/engine-macos/install/lib" \
cargo run --offline --manifest-path runtime/rust/Cargo.toml --example synthesize -- \
  /path/to/models P3 TRUSTED_BRIDGE_SHA '你好，欢迎使用。' sample.f32 stream
```

On Linux use `LD_LIBRARY_PATH` instead. Embed/sign the native library for deployment.
Android CPU auto-dispatch and cooperative cancellation cannot currently be combined.

See [licenses and notices](../NOTICE.md) for runtime and model dependencies.
