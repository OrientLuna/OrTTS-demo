#!/usr/bin/env python3
"""Copy a verified unified/PTQ source and apply locked cooperative cancellation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

try:
    from source_identity import identity
except ModuleNotFoundError:
    from tools.source_identity import identity

ROOT = Path(__file__).resolve().parents[1]


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    speech = (source / "ORTTS_SPEECH_SOURCE_RECEIPT.json").exists()
    identity(source, liquidcodec=True, speech=speech)
    if (source / "ORTTS_CPU_DISPATCH_RECEIPT.json").exists():
        raise ValueError("Cancellation currently requires the statically linked CPU backend, not CPU dispatch modules")
    if output.exists():
        raise ValueError("Choose a fresh output directory")
    lock = json.loads((ROOT / "vendor/cancellation.lock.json").read_text())
    patch = ROOT / lock["patch"]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if sha(patch) != lock["patch_sha256"]:
        raise ValueError("Cancellation patch SHA mismatch")
    mtmd_patch = ROOT / lock["mtmd_patch"]
    if sha(mtmd_patch) != lock["mtmd_patch_sha256"]:
        raise ValueError("Cancellation mtmd patch SHA mismatch")
    for entry in lock["mtmd_files"]:
        if sha(source.parent / "mtmd" / entry["path"]) != entry["base_sha256"]:
            raise ValueError("Cancellation mtmd base mismatch: " + entry["path"])
    for entry in lock["files"]:
        path = source / entry["path"]
        actual = sha(path) if path.exists() else None
        if actual != entry["base_sha256"]:
            raise ValueError("Cancellation base mismatch: " + entry["path"])
    output.mkdir(parents=True)
    destination = output / "audio.cpp"
    shutil.copytree(source, destination, symlinks=True)
    shutil.copytree(source.parent / "mtmd", output / "mtmd", symlinks=True)
    for name in ("fullchain_probe.cpp", "lc_fixture.cpp", "compat_probe.cpp"):
        shutil.copy2(source.parent / name, output / name)
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(output)}
    for args in (("--check",), ()):
        subprocess.run(["git", "apply", *args, str(patch)], cwd=destination, env=env, check=True)
        subprocess.run(["git", "apply", *args, str(mtmd_patch)], cwd=output / "mtmd", env=env, check=True)
    for entry in lock["files"]:
        if sha(destination / entry["path"]) != entry["sha256"]:
            raise ValueError("Cancellation output mismatch: " + entry["path"])
    for entry in lock["mtmd_files"]:
        if sha(output / "mtmd" / entry["path"]) != entry["sha256"]:
            raise ValueError("Cancellation mtmd output mismatch: " + entry["path"])
    (destination / "ORTTS_CANCELLATION_RECEIPT.json").write_text(json.dumps(lock, indent=2) + "\n")
    identity(destination, liquidcodec=True, speech=speech)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.source, args.out))
