#!/usr/bin/env python3
"""Package tested Apple runtime slices, Rust SDK, fixed sources and SHA receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

from source_identity import identity

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_files(directory):
    # Never archive model weights, build caches, git database or signing material.
    excluded = {".git", "target", "__pycache__", "build", "dist", ".DS_Store"}
    for path in sorted(directory.rglob("*")):
        if excluded.intersection(path.relative_to(directory).parts):
            continue
        if path.is_file() and not path.is_symlink() and path.suffix not in {".pyc", ".gguf", ".f32", ".wav", ".p12", ".mobileprovision"}:
            yield path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--base-source", type=Path, required=True)
    for name in ("macos", "device", "simulator"):
        p.add_argument("--" + name, type=Path, required=True, help="native build directory")
        p.add_argument("--" + name + "-rust", type=Path, required=True, help="compiled libortts_engine.rlib")
    p.add_argument("--acceptance", type=Path, required=True, help="directory containing per-target JSON receipts/logs")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    source = args.source.resolve(strict=True)
    base = args.base_source.resolve(strict=True)
    lock = identity(source, True, True)
    identity(base, True, True)
    output = args.out.resolve()
    if output.exists():
        p.error("Choose a new output directory")
    # Reject stale receipts before creating a deliverable.
    receipts = {}
    for name in ("macos", "device", "simulator"):
        build = getattr(args, name).resolve(strict=True)
        receipt = json.loads((build / "ENGINE_BUILD_RECEIPT.json").read_text())
        if receipt.get("status") != "BUILT_NOT_TARGET_TESTED" or receipt.get("cancellation") != lock["cancellation"]:
            p.error(f"Missing/current cancellation build receipt: {name}")
        for relative, expected in receipt["plugin_source_sha256"].items():
            if sha(ROOT / relative) != expected:
                p.error(f"Stale source receipt: {name}: {relative}")
        for artifact in receipt["artifacts"]:
            if sha(build / artifact["path"]) != artifact["sha256"]:
                p.error(f"Artifact SHA mismatch: {name}: {artifact['path']}")
        receipts[name] = receipt
    output.mkdir(parents=True)
    for name in receipts:
        target = output / name
        shutil.copytree(getattr(args, name) / "install", target / "native", symlinks=True)
        (target / "rust").mkdir()
        shutil.copyfile(getattr(args, name + "_rust"), target / "rust/libortts_engine.rlib")
        (target / "ENGINE_BUILD_RECEIPT.json").write_text(json.dumps(receipts[name], indent=2) + "\n")
    subprocess.run(["python3", str(ROOT / "tools/package_apple_engine.py"),
                    "--device", str(output / "device/native/OrTTS.framework"),
                    "--simulator", str(output / "simulator/native/OrTTS.framework"),
                    "--out", str(output / "OrTTS.xcframework")], check=True)
    shutil.copytree(args.acceptance, output / "acceptance")
    shutil.copytree(ROOT / "licenses", output / "licenses")
    for name in ("LICENSE", "NOTICE.md"):
        shutil.copyfile(ROOT / name, output / name)
    (output / "source").mkdir()
    files = []
    # Scope the repository snapshot; do not capture unrelated benchmark workspace edits.
    for name in ("runtime", "tools", "vendor", "src", "tests", "licenses"):
        files += [(path, "repository/" + str(path.relative_to(ROOT))) for path in source_files(ROOT / name)]
    for name in ("CMakeLists.txt", "LICENSE", "NOTICE.md"):
        files.append((ROOT / name, "repository/" + name))
    unified = json.loads((source / "ORTTS_UNIFIED_SOURCE_RECEIPT.json").read_text())
    llama = Path(unified["llama_source_read_only"])
    for directory, prefix in ((source.parent, "prepared-cancellable"), (base.parent, "prepared-base"), (llama, "pinned-llama")):
        files += [(path, prefix + "/" + str(path.relative_to(directory))) for path in source_files(directory)]
    manifest = {}
    with tarfile.open(output / "source/fixed-sources.tar.gz", "w:gz") as archive:
        for path, name in files:
            archive.add(path, arcname=name, recursive=False)
            manifest[name] = sha(path)
    (output / "source/SOURCE_SHA256.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # A convenient standalone Cargo source tree; source archive contains its pinned dependencies too.
    for path in source_files(ROOT / "runtime/rust"):
        destination = output / "rust-sdk" / path.relative_to(ROOT / "runtime/rust")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    (output / "DELIVERY.json").write_text(json.dumps({
        "schema": 1, "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()),
        "source_identity": "Exact delivered source bytes are pinned in SOURCE_SHA256.json; HEAD alone is not the source identity of a dirty build",
        "rustc": subprocess.check_output(["rustc", "--version"], text=True).strip(),
        "cancellation_lock": lock["cancellation"], "models_included": False,
        "android_cpu_auto_cancellation": "UNSUPPORTED: rejected in both preparation orders, source identity and CMake",
        "notes": ["Per-target runtime acceptance is separate from build success; read acceptance/*.json",
                  "Unsigned SDK frameworks require signing by the host app; no provisioning/private keys included",
                  "Source receipts preserve original paths. On another machine, point unified receipt paths to the included byte-identical pinned-llama and re-prepare cancellation from prepared-base; never alter expected SHA values",
                  "rlib files require the matching Rust toolchain/target; prefer building rust-sdk source for integration"],
    }, indent=2) + "\n")
    (output / "README.md").write_text("""# OrTTS Apple cancellation SDK

Native Apple libraries and a Rust binding for local speech synthesis with task-scoped cancellation.
Model weights are not included.

## Choose a library

- macOS arm64: `macos/native/`.
- iOS: `OrTTS.xcframework`, or the separate `device/native/` and `simulator/native/` slices.
- Rust source and usage: [rust-sdk/README.md](rust-sdk/README.md).

## Rust

Prefer building `rust-sdk` with your toolchain. Set `ORTTS_LIB_DIR` to the macOS
native lib directory, or `ORTTS_FRAMEWORK_DIR` to the parent of the selected iOS
framework. Prebuilt target-specific rlibs require the matching Rust toolchain.
Embed/sign the native library with your app and configure its runpaths.

Keep Engine on one worker, use a fresh Task per operation, and share only its CancelHandle.
Android CPU auto-dispatch cannot currently be combined with cooperative cancellation.

Source rebuilds, platform acceptance and integrity records: [AGENT_README.md](AGENT_README.md).
""")
    (output / "AGENT_README.md").write_text("""# Apple SDK delivery maintenance

## Integrity and provenance

- `DELIVERY.json` records build identity, toolchain and the cancellation lock.
- `SHA256SUMS` lists delivered regular files; verify them before redistribution.
- `source/fixed-sources.tar.gz` contains repository build sources, prepared input/output
  trees and pinned llama/ggml dependencies. `source/SOURCE_SHA256.json` identifies their bytes.
- A dirty build is identified by its exact source manifest, not by Git HEAD alone.
- Keep original archives and their hashes immutable. Later source changes need a new
  delivery revision; never retroactively relabel an old binary or acceptance receipt.

## Acceptance and signing

Read `acceptance/*.json` for per-target execution status. Native build receipts marked
BUILT_NOT_TARGET_TESTED establish compilation only; an installed probe or launch code
does not prove physical-device acceptance. Keep device and simulator evidence separate.
Full Rust ownership and validation notes are in `rust-sdk/AGENT_README.md`.

SDK frameworks need signing by the host app; this is not a notarized installer.
No provisioning or private signing material is included. Prebuilt rlibs depend on the
recorded toolchain/target; source integration is preferred.

## Relocated rebuild

For a relocated source rebuild, use the included byte-identical pinned-llama source,
update ONLY path fields in the prepared-base unified receipt, then rerun the normal
locked cancellation preparation/build tools. Keep original receipts as provenance;
do not change any expected source/patch SHA values.

Cooperative cancellation plus Android CPU auto-dispatch remains unsupported. Apple
acceptance does not certify Android execution or every deployment-compatible iOS release.
""")
    sums = [f"{sha(path)}  {path.relative_to(output)}" for path in source_files(output) if path.name != "SHA256SUMS"]
    (output / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    print(output)


if __name__ == "__main__":
    main()
