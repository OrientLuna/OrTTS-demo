# Apple PTQ / Lazy integration

The shared C ABI engine now applies the same model-pack policy as Android before constructing a model/session. It restores caller environment through the existing execution gate and environment scope. Public C and Rust headers and ABI are unchanged. Apple UI files are preserved.

## Supported package

Only the validated 0.6B P3 + Liquid100k Q8 combination: Talker196 matrices Q4_0, native P3, KV F32. Keep the matching full-compatible model package and all existing SHA/shape validation. Do not apply this policy to P5 or1.7B. Standard Q8/legacy packages continue without lazy enabled.

The existing package uses `research_policy.schema=ortts-ptq-lazy-qa-v1`. Despite that historical field name, the runtime explicitly validates its P3 scope, own1024 speaker dimension,196-matrix resident type and Liquid decoder. No flag needs to be added by an Apple caller. Lazy enables only for literal `1`; unset/`0` disable. Do not use a process-wide shell setting or keep two unmanaged audio.cpp engines active concurrently.

## Source preparation

Use the existing pinned source workflow: `prepare_runtime.py`, then `prepare_unified_runtime.py --release-compat`, then `prepare_speech_runtime.py` when enabling speech families. The release-compatible unified step now applies `vendor/ptq-lazy.lock.json` and its patch. `source_identity.py` validates the extra receipt and exact changed-source hashes. Build the engine framework using the normal Apple build tools; no Android `.so` is reusable on iOS.

Use the existing model import, `ortts_engine_create`, streaming callback and audio format contract. Ensure the matching model/dequant manifest and model's own speaker vector are selected. Fixed voices remain the ordinary demo flow; speaker-only WAV reference was checked through the Android adapter. Reference-text ICL is unsupported by this Liquid path and must retain its guard. MOSS additionally needs reference WAV/transcript and48k stereo playback; the generic MOSS descriptor is separate until the Apple frontend supports these capabilities.

## Evidence and remaining Apple checks

Android OPPO CPU4 has23 successful streams with natural EOS, finite PCM, callback/final agreement, complete playback and zero observed underruns. Warm short/long RTF: Q8 .690/.732, PTQ+Lazy .687/.766; warm sampled peak PSS1570→1155MiB. Quality was accepted by the user for the earlier Honor batch. These are Android results, not iPhone performance claims.

Linux validation covers shared-engine syntax, policy binding/negative cases and source-patch identity. The Apple owner must build/sign on macOS and check import, first synthesis, repeated streaming/EOF, release/reload and memory on a real iPhone. Public download defaults and model URLs are unchanged; this source update creates no GitHub Release.

## Apple build follow-up (2026-11-11)

Apple Demo now includes an optional PTQ Q4/P3 selector; the standard Q8 default and legacy entry remain. The PTQ package is isolated in `models-ptq-q4/` and rejects P5 at the UI/package boundary as well as in the shared runtime policy. Its fixed manifest is:

- URL: https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B/resolve/v0.3.1-ptq-q4/variants/ptq-q4/DOWNLOAD_MANIFEST.json
- SHA256: `26cf9f79991fa38eb766541ee34a964c4521cb5130fd61034dad3302bebd0017`
- Declared assets: 92 files, 1,588,857,280 bytes. The repository-root manifest at this tag still describes standard Q8; it is not the PTQ manifest.

Package-specific pin verification and wrong-package/tamper/P5 rejection are checked by `tests/apple_own_model_packages.m` with the three published manifests (no weights). Both CMake and the Xcode project generator include the package metadata and download-channel sources. Device/simulator frameworks and Demo builds are separate from model acceptance: import with full asset SHA checks, first/repeated streaming/EOS, release/reload, memory and listening remain pending on a physical iPhone. No model inference or performance ranking is claimed by these builds.
