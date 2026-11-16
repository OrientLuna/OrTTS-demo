#!/usr/bin/env python3
"""Apply explicit qwen3_tts.* session options to a prepared audio.cpp tree."""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def apply(source):
    source = Path(source).resolve()
    lock = json.loads((ROOT / "vendor/explicit-options/lock.json").read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    patch = ROOT / lock["patch"]
    if sha(patch) != lock["patch_sha256"]:
        raise ValueError("Explicit-options patch SHA mismatch")
    for entry in lock["files"]:
        p = source / entry["path"]
        actual = sha(p) if p.exists() else None
        if actual != entry["base_sha256"]:
            raise ValueError("Explicit-options base mismatch: " + entry["path"])
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(source.parent), "TMPDIR": "/tmp"}
    for args in [["git", "apply", "--check", str(patch)], ["git", "apply", str(patch)]]:
        subprocess.run(args, cwd=source, env=env, check=True)
    for entry in lock["files"]:
        if sha(source / entry["path"]) != entry["sha256"]:
            raise ValueError("Explicit-options output mismatch: " + entry["path"])
    (source / "ORTTS_EXPLICIT_OPTIONS_RECEIPT.json").write_text(json.dumps(lock, indent=2) + "\n")
    return lock


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, type=Path)
    a = p.parse_args()
    print(json.dumps(apply(a.source), indent=2))
