# Rust cancellation: maintainer/agent contract

User API: [README](README.md). Do not change OrTavern UI/download orchestration.

## Recorded Apple delivery

Portable acceptance/provenance summary: [acceptance/apple-20261113.json](acceptance/apple-20261113.json).
It records the immutable r2 ZIP, fixed-source and runtime SHAs, actual platform coverage and remaining limits.
Full raw receipts/logs are in that local delivery's `acceptance/`; do not commit models, binaries,
provisioning, personal device identifiers, absolute signing paths or raw system crash logs.
The delivered source archive predates the product version bump and Git preparation summary; do not
claim a later commit hash was the source identity of that dirty build or overwrite the original ZIP.

Subsequent source-only cleanup fixes the three historical `speech.rs` Clippy warnings without
suppression (private option-pair alias and equivalent channel range checks). Strict `--all-targets -- -D warnings`
passes for macOS and cross-checks for both iOS targets; matched/v1/pre-token macOS tests each pass
9 unit + 4 integration + 2 compile-fail docs tests. Frozen r2 binaries/receipts still describe the original
source; they must not be retroactively relabeled as built from this cleanup.

[Observed regression data](../../benchmarks/rust-cancellation-apple-20261113.json) records cancellation
correctness and per-request elapsed observations separately from the product's single synthesis smoke.
These are not controlled performance rankings or hard latency thresholds. In particular, load cancellation
was 2244.655 ms on the recorded Mac run and 1543.983 ms on the simulator, despite a 3.48 ms device run.
Do not generalize the device value to every platform. Existing performance matrices retain their original
numbers and pending-controlled-retest status; this cleanup does not initiate new device performance runs.

The separately installed product app is 0.4.1 / build 2026111301 under its existing bundle ID.
It is an Objective-C host of the same native C ABI framework, not a migration to Rust Task calls.
Its existing selected AppIcon was compiled with actool; no new icon artwork or UI/download orchestration
was added. Signing/install receipts remain local; the SDK ZIP does not contain private signing material.

## Ownership and linearization

- `Engine` deliberately remains `!Send + !Sync`; native `execution_gate` is unchanged.
  Concurrent runtime work still returns `BUSY`; Rust does not replace it with a global blocking mutex.
- Each `Task` owns a new sticky native token and a monotonically assigned diagnostic generation.
  Identity is its unique Arc allocation, not a reusable engine pointer or an integer matched against a global current operation.
- `CancelHandle` is Send/Sync and cloneable; it owns only task state, NEVER an engine pointer.
  It may be shared before loading starts. One Task can be consumed only once, including invalid-input or failed calls.
- The operation guard survives synchronous native compute/unwind; only after return is the task marked finished
  and token freed. Cancel request, completion and token free serialize under a short per-task mutex.
  No user callback or long compute runs under that mutex, so callback cancellation does not deadlock.
- Success completion checks requested and marks finished atomically with respect to cancel. A request winning
  before completion produces `Cancelled`; one arriving later sees `Inactive`. Old tickets cannot target new tasks.
- On load cancellation the unpublished engine is freed after native return. On synthesis cancellation the same
  Engine remains owned on its worker; native request/KV/codec state is reset without unloading weights.
- Additive `ortts_engine_synthesize_cancellable` accepts a sticky per-call token, closing the legacy Running
  reset/start race. A separate token is mandatory for each operation; legacy raw C engine_cancel is not generation-bound.
- Optional function pointers are discovered from the already linked ABI1 image (`dladdr` + image-scoped dlsym),
  not from RTLD_DEFAULT. No hard relocation to optional symbols; SDK still loads with pre-token libraries.
  Missing discovery on unsupported platforms conservatively degrades. Do not load a second unrelated runtime.
- v1 cancellation libraries may support token creation/load but lack token synthesis: report the two capability
  modes independently. Fallback never fabricates early interruption; it checks before call and discards on completion.
- Native status 4 is `Error::Cancelled`; other status codes/messages remain structured `Native` errors.
  Existing string-returning APIs and speech wrappers stay source-compatible.

## Validation

```sh
export ORTTS_LIB_DIR=/path/to/macos/install/lib
export DYLD_LIBRARY_PATH="$ORTTS_LIB_DIR"
ORTTS_EXPECT_CANCEL_MODE=cooperative cargo test --offline --manifest-path runtime/rust/Cargo.toml
cargo run --offline --release --manifest-path runtime/rust/Cargo.toml --example cancellation -- \
  /path/to/verified/q4 TRUSTED_DEQUANT_SHA /new/path/acceptance.json
```

Run unchanged against v1 and pre-token libraries (`ORTTS_EXPECT_CANCEL_MODE=v1` / `legacy`); use separate
Cargo target directories if building concurrently. Acceptance is opt-in, no downloads. It covers actual load
cancel, both run modes, repeated cancellation, recovery PCM equality, stale handles during NEXT task, post-drop
handles, native execution BUSY gate, callback cancellation/panic and recovery. Unit tests exercise precancel,
ticket consumption, completion/cancel races and token request/free serialization. This is not Miri/TSan or a
long-duration leak proof; observed cancellation latency includes environment load, not a guaranteed deadline.

iOS isolated harness: `tests/apple_rust_cancel_probe/` links this same acceptance into a static Rust shim.
Build with `tools/build_apple_rust_cancel_probe.py --framework ... --target device|simulator --out ...`.
Device additionally needs a local authorized profile/identity. Copy a verified model to the probe's Documents/models;
launch it and retrieve Documents/rust-cancellation.json. Keep the probe separate from production applications.
The probe declares a UIWindowScene delegate and scene manifest: physical iOS 27.0.1 traps legacy lifecycle
apps before acceptance completes. Do not interpret devicectl exit code 0 without the persisted passed JSON
and RUST_CANCEL_PROBE_STATUS=0 marker as success; retrieve systemCrashLogs if the report is absent.
Never include provisioning/private signing credentials in public SDK archives. Physical-device and simulator receipts
must be separate; successful framework compilation alone is BUILT_NOT_TARGET_TESTED.

## Source identity / Android boundary

Prepare locked base → release-compatible unified/PTQ → speech → cancellation using existing tools.
`vendor/cancellation.lock.json` pins audio and mtmd patches plus before/after file SHAs; preserve all source/build
receipts when packaging dylib/framework/XCFramework with Rust SDK source and artifact SHA256 manifest.

**Android CPU auto-dispatch + cooperative cancellation is unsupported** in this delivery. Reject it in BOTH
preparation orders, source identity verification and direct CMake configuration; do not just disable the capability
flag while linking incompatible modules. Fixed CPU profiles are build candidates but not Android device-certified
by Apple tests. No Android auto-dispatch cancellation artifact is claimed. Existing Android auto builds without
cancellation remain unchanged; a cooperative auto-dispatch implementation needs per-module callback wiring and
its own pinned patch/ABI and device tests.
