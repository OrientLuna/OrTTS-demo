"""Assemble a local Linux folder bundle; does not rebuild/download the native engine."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new directory, never overwritten")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    library = args.library.resolve(strict=True)
    # Collect all evidence before creating the output directory.
    dependencies = subprocess.check_output(["ldd", str(library)], text=True)
    if "not found" in dependencies:
        raise RuntimeError(dependencies)
    versions = subprocess.check_output(["readelf", "--version-info", str(library)], text=True)
    required_versions = sorted(set(re.findall(r"Name: ((?:GLIBC|GLIBCXX|CXXABI|GOMP|OMP)_[0-9.]+)", versions)))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True)
    args.output.mkdir(parents=True, exist_ok=False)
    for package in ("linux", "desktop"):
        target = args.output / package
        target.mkdir()
        # No caches, build products, weights or macOS packaging tools.
        for path in (source / package).glob("*.py"):
            shutil.copy2(path, target / path.name)
    brand = args.output / "assets/brand"
    brand.mkdir(parents=True)
    shutil.copy2(source / "assets/brand/ortts-icon.png", brand)
    native = args.output / "native"
    native.mkdir()
    shutil.copy2(library, native / "libortts.so")
    shutil.copy2(source / "linux/README.md", args.output / "README.md")
    for path in (source / "LICENSE", source / "NOTICE.md"):
        if path.is_file():
            shutil.copy2(path, args.output / path.name)
    launcher = args.output / "ortts"
    launcher.write_text('#!/bin/sh\nset -eu\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\ncd "$HERE"\nexport PYTHONDONTWRITEBYTECODE=1\nexec python3 -m linux.app --library "$HERE/native/libortts.so" "$@"\n')
    launcher.chmod(0o755)
    report = {"source_head": head, "uncommitted_source": bool(dirty), "platform": platform.platform(),
              "architecture": platform.machine(), "libc": platform.libc_ver(), "native_dependencies": dependencies,
              "required_symbol_versions": required_versions,
              "python_required": ">=3.10 with tkinter", "audio_required": "alsa-utils / aplay",
              "isa": "inherited from supplied engine; this script does not change CPU features",
              "files": {str(p.relative_to(args.output)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in args.output.rglob("*") if p.is_file()}}
    (args.output / "BUILD.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(args.output / "ortts")


if __name__ == "__main__":
    main()
