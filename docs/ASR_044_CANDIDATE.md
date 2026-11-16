# Android ASR 0.4.4-rc candidate

This integrates the frozen Android Sherpa and interaction patches onto main
`75aa55f1cc37c58def1907f9842731dcbb8d7bdf`. Public speech ABI remains 1.
The Qwen executor is Android-only and requires the optional pinned Sherpa SDK.
SenseVoice, Moonshine and existing TTS remain available; Qwen is not selected
automatically. The rejected Zipformer experiment is hidden from the menu.

## Build and provenance

The ordinary app is `com.orient.ortts`, versionCode 29 / `0.4.4-rc`.
`--qa` builds `com.orient.ortts.qa`; QA activities are not exported in the
ordinary package. These are development Debug candidates, not public releases.
An installed ordinary app must be updated using its existing signing identity;
do not uninstall or erase user data to bypass a signature mismatch.

`tools/build_android.py` accepts `--speech --g2p-install <local-install>` and
`--sherpa-asr-prefix <local-sdk>` alongside the existing source/toolchain flags.
The SDK header and both shared libraries are pinned in
`vendor/sherpa-android.lock.json`. `--qa` is explicit. No SDK/model downloads
are performed by these build entries. Package notices include Sherpa 1.13.8,
ONNX Runtime 1.28.2 and the existing runtime licenses.

The tested candidate reused locked static engine inputs and rebuilt/relinked
the speech/JNI wrappers. It was **not** a full engine rebuild from source.
The new build-entry plumbing was separately dry-run checked.

## Local model import

Qwen is an optional high-memory offline profile. Use the model catalog's
seven exact size/SHA entries in `runtime/models/qwen3-asr-headslice.json`.
A local ZIP must contain paths beneath `Qwen3-ASR-0.6B-int8/`, including
`tokenizer/`. Graph and external `decoder.weights.bin` must share the same
real directory. No automatic download or model conversion is enabled.
The runtime independently verifies payload identities before creating the
recognizer. An arbitrary similarly named model is not accepted.

The verified profile keeps 28 layers, INT8, KV F32, arena enabled, CPU2,
automatic language, original EOS, seed 42, temperature 1e-6, top_p 1,
max_total_len 1024 and max_new_tokens 256. Head-slice compatibility output
is for the last-row ASR consumer only: earlier rows are placeholders, not
full teacher-forcing logits. No 24-layer/calibration/arena-off experiment
is included. Raw transcription, including erroneous headers, is preserved.

## Rollback and limits

For native/JNI callers, set `qwen3_asr.decoder_profile=original-int8`
(`SpeechBridge.openAsrProfile`) and retain the exact original
`decoder.int8.onnx` from the existing model lock. The default compatibility
profile is `headslice-compat`. Model switching remains explicit.
Existing SenseVoice/Moonshine selection is the ordinary UI fallback;
no silent fallback or automatic selection is introduced.

Qwen buffers bounded input and emits one final, not real partial streaming.
Cancel discards output after offline computation; callers must join before
freeing and reset before reuse. One-active-inference gating remains.
Three recorded-language parity examples and lifecycle checks are technical
evidence, not broad ASR quality certification, live-mic acceptance or low-end
device approval. Rust/iOS sources and public layouts/exports are unchanged;
no physical iOS execution was performed. Model redistribution and full
package license review remain pending; no weights are embedded or published.
