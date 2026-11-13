# Runtime maintenance notes

The [user README](README.md) is a quick integration guide. Keep source identities,
verification procedures, raw measurements and build caveats here or in the
[Rust maintainer guide](rust/AGENT_README.md), not in the main usage flow.

## Build and source identity

- `tools/prepare_runtime.py` and the optional unified/PTQ/speech/cancellation preparation
  tools produce source receipts. `tools/build_engine.py` validates them before building;
  it does not download dependencies, models or toolchains.
- Do not edit prepared vendor sources without updating the appropriate locked patch
  and its before/after file identities. A Git HEAD alone does not identify a dirty build.
- Keep model weights, build directories, SDK archives and signing files outside Git.
  Record portable metadata in receipts; avoid personal paths, device IDs and raw crash logs.
- Linux cross-builds need an existing toolchain; Android needs an NDK. Apple builds use
  Ninja to preserve same-basename upstream objects and require Xcode.
- iOS device and simulator frameworks are different slices. Combine with
  `tools/package_apple_engine.py`; do not load a simulator binary on a device.

## Platform selection

`arm64-baseline` and `x86_64-baseline` are the conservative profiles. AVX2 also requires
SSE4.2, FMA, F16C, BMI2 and OS AVX state support; ARM optimized builds need their named
extensions and FP16. An unsupported binary may fault before any runtime capability call.

`tools/cpu_profile.py` selects from Linux CPU features common to exposed cores and
falls back to baseline when uncertain. Apple uses baseline in that helper. Android
hosts need native feature checks before loading optimized libraries. Android CPU
auto-dispatch remains incompatible with cooperative cancellation and is rejected in
both preparation orders, source validation and CMake.

Linux redistribution also depends on glibc/libstdc++ compatibility, not just ISA.
Build with the oldest supported toolchain. Cross-compilation is not target execution
acceptance. These build recipes use CPU, not Metal or Core ML.

## Model identities and C ownership

The host verifies the model download manifest and passes its selected trusted
bridge/dequant identity, not a self-computed replacement trust root. P3/P5 and voices
must match the installed model package. Voices may contain 1024 or 2048 F32 values.
Keep asset paths available for the engine lifetime; the loader does not implement
download orchestration or replace full package verification.

PCM callbacks run on the generation thread. Borrowed chunks must not outlive the
callback; copy/enqueue and return promptly. `api_ms` includes callback time,
`generation_ms` excludes it, and `first_pcm_ms` is not acoustic onset. Successful finite
PCM does not prove EOS, pronunciation or subjective quality.

The native execution gate rejects concurrent load/synthesis with `ORTTS_BUSY`.
Calls temporarily alter process environment and restore it on return. Do not combine
direct audio.cpp sessions or a second independently loaded runtime with these operations,
reenter from callbacks, or free handles concurrently. This is not a multi-model server.

## Cancellation contract

Prepared cooperative builds report `ortts_cooperative_cancel_version() == 1`; legacy
builds report 0 or lack optional symbols. ABI1 layouts remain unchanged. Cooperative
checkpoints cover generation steps and supported CPU graphs, including Liquid
translator/codec work, but cannot preempt arbitrary kernels or blocking I/O.

- `ortts_engine_cancel()` targets the current request while its engine is alive;
  it is not generation-bound. Do not expose it as a long-lived task handle.
- `ortts_engine_create_cancellable` and `ortts_engine_synthesize_cancellable` accept
  sticky tokens. Create a fresh token before each operation, keep it alive until the
  native call returns and synchronize request versus free.
- A cancelled load returns `ORTTS_CANCELLED` and no published engine. A cancelled
  synthesis resets request/KV/decoder state while retaining model/session ownership.
- Never free the engine to request cancellation. Free is for unload, model switch
  or shutdown after the worker has finished.
- Probe optional symbols when integrating older libraries; missing token APIs require
  honest boundary/discard-after-return degradation, not a promise of early interruption.

Prefer Rust `Task` / `CancelHandle` for safe token ownership. Detailed invariants,
tests, source locks and delivery records are in [rust/AGENT_README.md](rust/AGENT_README.md).
The optional speech SDK has model-specific formats and bounded ASR input/finish/reset
semantics; it is not a general ONNX importer. See [SPEECH.md](SPEECH.md).
