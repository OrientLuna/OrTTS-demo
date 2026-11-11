#!/usr/bin/env python3
"""Build an onedir .app on Apple Silicon. No model weights are bundled."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def git_metadata(root):
    """Report actual repository state, including untracked but not ignored files."""
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root)

    def count_paths(*args):
        return len([p for p in git(*args).split(b"\0") if p])

    staged = count_paths("diff", "--cached", "--name-only", "-z", "--no-renames")
    unstaged = count_paths("diff", "--name-only", "-z", "--no-renames")
    untracked = count_paths("ls-files", "--others", "--exclude-standard", "-z")
    return {"git_head": git("rev-parse", "HEAD").decode().strip(),
            "working_tree": {"dirty": bool(staged or unstaged or untracked),
                             "staged_files": staged, "unstaged_files": unstaged,
                             "untracked_files": untracked,
                             "scope": "repository-wide; ignored files excluded"}}


def host_licenses():
    """Collect actual interpreter dependency licenses from local package receipts."""
    destination = ROOT / "local/desktop-host-licenses"
    destination.mkdir(parents=True, exist_ok=True)
    wanted = {"python", "tk", "libffi", "libzlib", "bzip2", "xz", "openssl", "libexpat"}
    found = {}
    for path in (Path(sys.base_prefix) / "conda-meta").glob("*.json"):
        record = json.loads(path.read_text())
        name = record["name"]
        if name not in wanted:
            continue
        source = Path(record["link"]["source"]) / "info/licenses"
        if not source.is_dir() or not any(p.is_file() for p in source.rglob("*")):
            raise SystemExit(f"Missing host component license: {source}")
        shutil.copytree(source, destination / name, dirs_exist_ok=True)
        found[name] = record["version"]
    if set(found) != wanted:
        override = os.environ.get("ORTTS_HOST_LICENSES")
        if not override or not Path(override).is_dir():
            raise SystemExit("Non-Conda interpreter: set ORTTS_HOST_LICENSES to its Python/Tcl/Tk and native dependency license directory")
        shutil.copytree(override, destination / "interpreter", dirs_exist_ok=True)
    dist = importlib.metadata.distribution("pyinstaller")
    for item in dist.files or []:
        if "/licenses/" in str(item) and dist.locate_file(item).is_file():
            target = destination / "pyinstaller" / Path(str(item).split("/licenses/", 1)[1])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dist.locate_file(item), target)
    return destination, found


def main():
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise SystemExit("This recipe must run on an Apple Silicon Mac")
    source_state = git_metadata(ROOT)
    library = ROOT / "build/pc-engine-macos/install/lib/libortts.dylib"
    receipt = json.loads((ROOT / "build/pc-engine-macos/ENGINE_BUILD_RECEIPT.json").read_text())
    if receipt["target"] != "macos-arm64" or receipt["cpu_profile"] != "arm64-baseline" or receipt["status"] not in ("BUILT_NOT_TARGET_TESTED", "TARGET_TESTED"):
        raise SystemExit("Build the macos-arm64 baseline runtime first")
    deps = subprocess.check_output(["otool", "-L", str(library)], text=True)
    for line in deps.splitlines()[1:]:
        path = line.strip().split(" (", 1)[0]
        if not path.startswith(("/usr/lib/", "/System/Library/", "@rpath/libortts.dylib")):
            raise SystemExit(f"Unbundled native dependency: {path}")
    license_dir, host_components = host_licenses()
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed",
                    "--name", "OrTTS", "--osx-bundle-identifier", "com.orient.ortts.desktop",
                    "--target-architecture", "arm64", "--icon", str(ROOT / "assets/brand/ortts.icns"),
                    "--paths", str(ROOT), "--add-binary", f"{library}:native",
                    "--add-data", f"{ROOT / 'assets/brand/ortts-icon.png'}:assets/brand",
                    "--add-data", f"{ROOT / 'LICENSE'}:licenses",
                    "--add-data", f"{ROOT / 'NOTICE.md'}:licenses",
                    "--add-data", f"{ROOT / 'licenses'}:licenses/components",
                    "--add-data", f"{license_dir}:licenses/desktop-host",
                    "--distpath", str(ROOT / "dist/macos-arm64"),
                    "--workpath", str(ROOT / "build/desktop-pyinstaller"),
                    "--specpath", str(ROOT / "local"), str(ROOT / "desktop/app.py")], check=True)
    app = ROOT / "dist/macos-arm64/OrTTS.app"
    import plistlib
    plist_path = app / "Contents/Info.plist"
    with plist_path.open("rb") as f:
        plist = plistlib.load(f)
    plist.update(LSMinimumSystemVersion="13.3", CFBundleShortVersionString="0.1.0", CFBundleVersion="1",
                 NSHighResolutionCapable=True)
    with plist_path.open("wb") as f:
        plistlib.dump(plist, f)
    # Only ad-hoc signing: no developer certificate or notarization is implied.
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    native = app / "Contents/Frameworks/native/libortts.dylib"
    # Scan every bundled Mach-O, not just OrTTS: Python/Tcl/Tk must also be portable.
    macho_count = 0
    for path in app.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as f:
            magic = f.read(4)
        if magic not in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
            continue
        macho_count += 1
        output = subprocess.check_output(["otool", "-L", str(path)], text=True)
        for line in output.splitlines()[1:]:
            dependency = line.strip().split(" (", 1)[0]
            if dependency.startswith("/") and not dependency.startswith(("/usr/lib/", "/System/Library/")):
                raise SystemExit(f"Nonportable dependency in {path}: {dependency}")
    info = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "app": str(app.relative_to(ROOT)), "architecture": "arm64", "cpu_profile": "arm64-baseline",
            **source_state,
            "python_version": platform.python_version(),
            "pyinstaller_version": importlib.metadata.version("pyinstaller"),
            "runtime_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
            "bundled_runtime_sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
            "desktop_source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in sorted((ROOT / "desktop").rglob("*")) if p.is_file() and p.suffix in (".py", ".txt", ".md")},
            "dependency_audit_macho_files": macho_count,
            "host_components": host_components,
            "native_build_receipt": receipt, "models_included": False,
            "signing": "ad-hoc; not notarized", "build_host": platform.platform(),
            "app_bytes": sum(p.stat().st_size for p in app.rglob("*") if p.is_file() and not p.is_symlink())}
    (app.parent / "BUILD_INFO.json").write_text(json.dumps(info, indent=2) + "\n")
    print(app)


if __name__ == "__main__":
    main()
