# MOSS Nano Android QA integration

This additive path keeps the existing P3/P5 defaults, download-channel routing,
public `ortts_speech.h` layout, and a single shared audio.cpp/ggml runtime.
Enable `--speech --liquidcodec` in the normal native build; `AUDIOCPP_MODELS`
adds `moss_tts_nano` alongside all previous families. No MOSS-only SO is loaded.
Use the existing verified/prepared source and a task-private output directory;
the implementation needs no MOSS algorithm or private engine patch.

## Contract

- Catalog `moss-100m-bf16` pins GGUF revision
  `ae77d06579f5ed1be99dd7614d99929e76a46d9e`, 332423040 bytes, SHA256
  `249a7eb9a8ae2e919946971e8270960f6657c0fbc06c5c7c4929b94af83ade0b`.
  Source weights are BF16, global/local runtime storage is F32. This is not the
  previously compared FP32 ONNX profile or a same-precision backend benchmark.
- Use task `clon`, actual female/male PCM reference plus exact transcript, seed
  1234 and max_tokens 1024 with the family's other defaults. Preset labels are
  not voice IDs and not Qwen speaker vectors. The bundled small reference WAVs
  are SHA-verified just like downloaded model files.
- The loader's `Auto` language declaration is not an English-only restriction:
  the pinned family spec supports Chinese. Only this known family bypasses the
  generic Han-text language-list rejection; other packages keep that protection.
- Before loading embedded specs/extracting embeddings, set `TMPDIR` to writable
  app-private cache. Each request gets an isolated trace through the existing
  `audiocpp_ortts_trace_file` export. No new trace hook is required.
- Native result/callback frames are **per channel**. JNI arrays contain
  `frames * channels` floats. AudioTrack is explicitly mono/stereo as appropriate;
  playback head, buffering and drain use frames, not interleaved sample counts.
  The two-argument mono sink remains supported.
- Store original interleaved IEEE FLOAT WAV without clipping/gain/trim. Validate
  finite samples, frame counts, callback/final exact equality and all MOSS chunk
  stop reasons `eoc`. API success alone is not EOS or a listening pass.

## Local QA build and tests

Build the unified native libraries with `tools/build.py --platform android-arm64
--android-jni --speech --liquidcodec`, supplying installed NDK/Ninja and explicit
private source/output paths. Package `assembleDebug -Pqa` using the resulting
JNI libraries and existing G2P assets; this is `com.orient.ortts.qa`, not the
ordinary application. Check the installed QA signing certificate before
`adb install -r`; never uninstall or clear user/model data for a smoke test.

Host tests `tests/PinnedAssetTest.java` exercise the same verifier used by
models/references (wrong SHA/length, corruption, cancellation, missing file and
invalid pin). `tests/moss_pcm.cpp` exercises stereo frames, invalid channels,
missing reference, and exact preservation of FLOAT samples above 1.0. Existing
download routing tests and all original C exports must stay valid. No weights
are bundled or downloaded by these tests.

The 2026-11-10 review artifact was tested on Honor REP-AN00 in bounded exclusive
device stages: backend 2 threads, actual OS-controlled foreground affinity
recorded per request, Chinese female/male short/long, English, voice switching,
release/reload, stop/resume, and one existing 0.6 P3 mono-stream regression.
Native callback PCM equalled final PCM and playback drained all frames.
Backend 2 with dynamic foreground affinity must not be called the old CLI's
fixed two-core run or a CPU4-equivalent result. First callback latency is not
audible onset. No OS governor/cpuset/thermal policy was changed.

Technical logs, original audio hashes, build/signing receipts and remaining
listening/network validation are in the task's worker report. Full public-network
332MB download was not exercised: the already verified on-device model was
imported into private cache, then the normal cached download/check UI verified
it. Existing HF/HF Mirror rules remain; no ModelScope mirror is invented.

## License and review boundary

Keep `licenses/MOSS-TTS-Nano-Apache-2.0.txt`, `MOSS-SOURCES.txt`, upstream model
notices and the existing runtime/eSpeak GPL notices/source obligations in the
APK. The source dialog exposes the complete MOSS license. A mixed GGUF
repository's top-level `other` tag is not the original model component license.
This local QA integration is not a legal-risk clearance, cloud release, or
human listening/content-quality certification.
