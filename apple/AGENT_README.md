# Apple Demo maintenance notes

Keep [README.md](README.md) focused on installation and app operation. Model manifest
rules, deployment evidence and test launch arguments belong here and in linked guides.

## Models and import

- Default mobile own-model selection is Q4/P3. The built-in Q4 manifest is
  `v0.3.1-ptq-q4/variants/ptq-q4/DOWNLOAD_MANIFEST.json`; its package is stored in
  `Documents/models-ptq-q4/`, supports only 0.6B P3, and is roughly 1.59 GB for that version.
- LiquidCodec Q8 uses `models-liquid/`; historical LFM uses `models/`. These are
  separate model/decoder versions, not interchangeable directories.
- Validate the selected package's pinned manifest, file sizes and hashes. Do not use
  the repository's Q8 manifest for Q4. LiquidCodec passes its trusted dequant manifest
  identity to the runtime, not the legacy bridge identity.
- Downloads reuse verified identical assets across installed own-model packages.
  This avoids some transfers but does not promise a single physical copy on disk.
- Import takes a native model folder, not ZIP; it does not overwrite conflicting
  files. Preserve user models and outputs on app updates; use same-bundle-ID install,
  not uninstall/reinstall, when upgrading an authorized development device.
- Download routing, discovery and cache behavior are documented in
  [OWN_MODEL_CATALOG.md](../docs/OWN_MODEL_CATALOG.md) and
  [MOBILE_SPEECH_DEMO.md](../docs/MOBILE_SPEECH_DEMO.md). Do not rewrite that orchestration
  to integrate an SDK or refresh an icon.

## Build, icons and signing

`apple/CMakeLists.txt` links the native framework selected by `ORTTS_ENGINE_INSTALL`.
The product remains an Objective-C C ABI host, not a Rust Task UI migration. Provide
`ORTTS_G2P_INSTALL` for the mobile TTS catalog's eSpeak library/data/licenses.
The native deployment minimum is iOS 16.3; a new SDK does not imply every supported
OS/device/model was runtime-tested.

Compile `apple/Assets.xcassets` with `tools/compile_apple_app_icons.py`, merge actool's
primary icon keys into Info.plist, then sign nested frameworks and finally the app.
Use the selected formal brand assets, not proposals or new artwork. Asset presence and
device install metadata do not replace a visual check of the SpringBoard icon/cache.
Provisioning, entitlements and private signing material stay local.

The app already uses Scene lifecycle. Keep the isolated Rust cancellation probe's
Scene delegate/manifest too: its legacy lifecycle trapped on physical iOS 27.0.1.
Device launch exit 0 without a persisted report is not acceptance success; inspect
the app/system crash log if the report and completion marker are missing.

## Manual and automated checks

Normal startup does not automatically download weights or synthesize. Catalog-only
discovery may run. Explicit development launch arguments include:

- `--synthesis-smoke`: synthesize the selected/default text and play it.
- `--cancel-stream-smoke`: stop after streaming has begun.
- `--download-smoke`: check/download the selected package; do not use without authorization.
- `--benchmark-text TEXT`, `--benchmark-p5`, `--benchmark-male`: override the test selection.

Back up `Documents/ortts-output.caf` before synthesis tests in a user's product
container; restore and verify it afterward if preserving the last output is required.
Persistent UIKit console sessions can return nonzero when deliberately terminated.
Judge synthesis by its result, PCM format and playback markers, not a launch code alone.

Product 0.4.1 / build 2026111301 was installed and launched on iPhone 17 / iOS 27.0.1.
Q4 synthesis/playback and stop smoke passed; original output was restored. The separate
Rust probe passed on that device and an iOS 26.5 simulator. Portable provenance:
[Apple SDK receipt](../runtime/rust/acceptance/apple-20261113.json).
Observed timings are in [regression data](../benchmarks/rust-cancellation-apple-20261113.json),
not controlled RTF rankings. Older measurements in `benchmarks/iphone17-cpu.json` are
historical, not evidence that the current Q4 build has the same performance.

Uncovered areas include all older iOS releases, every file-picker interaction, audio
interruptions, long-text EOS/completeness and subjective listening quality. Do not
expand a smoke success into blanket platform or quality certification.
