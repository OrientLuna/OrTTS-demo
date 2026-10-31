# OrTTS CPU engine

Embed P3/P5 speech synthesis in your application through a small C ABI. Linux and Android use `libortts.so`, macOS uses `libortts.dylib`, and iOS uses `OrTTS.framework`. Model files are external and shared by the variants.

The API supports model loading, offline synthesis, incremental float PCM, cancellation, timing and explicit release. It does not create an app, play audio, download weights or write generated files. Audio is mono float32 at 24 kHz.

## Build

Use the verified local audio.cpp source prepared by `tools/prepare_runtime.py`, plus existing compilers and SDKs. Nothing is downloaded by the build tool.

```sh
python3 tools/build_engine.py --target linux-x86_64 --profile x86_64-baseline \
  --source _work/runtime --out build/engine-linux-baseline
```

| Target | CPU profiles |
|---|---|
| Linux x86-64 | `x86_64-baseline`, `x86_64-avx2` |
| Linux ARM64, Android ARM64 | `arm64-baseline`, `arm64-dotprod`, `arm64-i8mm` |
| macOS Apple Silicon | `arm64-baseline`, `arm64-dotprod`, `arm64-i8mm` |
| macOS Intel | `x86_64-baseline`, `x86_64-avx2` |
| iOS device | `arm64-baseline`, `arm64-dotprod`, `arm64-i8mm` |
| Apple Silicon simulator | `arm64-baseline` |

Choose the profile before loading the library. AVX2 also requires SSE4.2, FMA, F16C, BMI2 and OS support for AVX state. ARM optimized profiles require the named extensions and FP16. An unsupported profile can crash before an API call; this prototype does not automatically dispatch between separate libraries. Use the baseline when uncertain. Optimized profiles are candidates until tested on the target device.

`python3 tools/cpu_profile.py` recommends a profile from Linux CPU features before any engine library is loaded, taking the common features across exposed cores. It falls back to a baseline when features are unknown. Apple uses the baseline in this helper. This is a host-side selection aid; an Android app needs equivalent native capability checks before loading an optimized library.

Instruction-set compatibility and OS compatibility are separate. Linux binaries built on a new distribution can require a newer glibc/libstdc++; build on the oldest supported Linux toolchain for redistribution. Model execution must still be checked on each target.

Linux cross-builds require `--toolchain` for an existing Linux ARM64 compiler; Android requires `--ndk`. Apple targets require a Mac with Xcode. For example:

```sh
python3 tools/build_engine.py --target macos-arm64 --profile arm64-baseline \
  --source _work/runtime --out build/engine-macos
python3 tools/build_engine.py --target ios-arm64 --profile arm64-baseline \
  --source _work/runtime --out build/engine-iphone
python3 tools/build_engine.py --target ios-simulator-arm64 --profile arm64-baseline \
  --source _work/runtime --out build/engine-simulator
python3 tools/package_apple_engine.py \
  --device build/engine-iphone/install/OrTTS.framework \
  --simulator build/engine-simulator/install/OrTTS.framework \
  --out build/OrTTS.xcframework
```

Apple CPU prototypes and local verification notes are in [apple/README.md](../apple/README.md). Minimum deployment targets are macOS 13.3 and iOS 16.3. Engine builds use Ninja to preserve same-basename upstream objects; app projects can use Xcode. Apple Silicon Mac and iPhone 17 model execution has been tested; this does not cover all Apple devices. See [CPU profiles and measurements](../docs/CPU_PROFILES.md). CPU is the implemented route. These recipes do not enable Metal or Core ML.

## C interface

Include [`ortts_engine.h`](include/ortts_engine.h) and link the library. Set the configuration/request `struct_size` fields to `sizeof` their types. Create a streaming or offline engine, synthesize, copy/use the result, then release the audio and engine. Errors return a status; read `ortts_last_error()` immediately on that thread.

Pass the installed asset root, P3/P5, a legitimate speaker vector, and the trusted bridge manifest SHA from your verified model manifest. The initial loader accepts the current native package layout. It does not replace download-manifest verification. Input paths must remain available for the engine lifetime.

The PCM callback runs on the generating thread. Copy or enqueue each chunk and return promptly; do not block it on speaker playback. Return nonzero to cancel. The C API also permits a cancellation request from another thread while the engine remains alive. Streaming cancellation is checked at chunk boundaries; offline cancellation discards the completed result rather than interrupting an in-flight matrix operation.

API wall includes callback time; `generation_ms` excludes that callback time and is not pure kernel time. `first_pcm_ms` is PCM availability, not acoustic onset. Success returns finite PCM; it does not certify EOS, pronunciation or voice quality.

## Rust

The dependency-free binding in [`rust/`](rust/) owns handles and copies final PCM into a Rust `Vec<f32>`. Its streaming closure receives borrowed chunks and may return `false` to cancel; panics are caught before returning across FFI. Create/use the engine on a dedicated worker. The safe wrapper is intentionally neither `Send` nor `Sync`.

```sh
ORTTS_LIB_DIR="$PWD/build/engine-linux-baseline/install/lib" \
LD_LIBRARY_PATH="$PWD/build/engine-linux-baseline/install/lib" \
cargo run --offline --manifest-path runtime/rust/Cargo.toml --example synthesize -- \
  /path/to/models P3 TRUSTED_BRIDGE_SHA '你好，欢迎使用。' sample.f32 stream
```

On macOS use `DYLD_LIBRARY_PATH` during development. For deployment embed/sign the dylib or framework with the host application and configure its runpath. The iOS binding uses `ORTTS_FRAMEWORK_DIR` for the selected framework slice. Rust is optional: other hosts can use the same C ABI, including runtime symbol loading after checking `ortts_abi_version()`.

## Concurrency

The prototype serializes engine operations within one loaded library. A concurrent load/synthesis returns `ORTTS_BUSY`. Existing runtime configuration uses process environment; our calls restore their changes on return. Do not concurrently use direct audio.cpp sessions or a second independently loaded copy of the engine in the same process. Do not reenter or free the engine in its callback, or free it concurrently with synthesis/cancellation. Per-session configuration isolation is a later improvement; this is not a multi-model concurrent server.

The wrapper and Rust binding follow the repository license. Runtime and model component licenses remain applicable; see the repository notices.
