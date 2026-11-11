#!/usr/bin/env python3
"""Package the existing .app into a simple drag-to-Applications, unsigned DMG."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=ROOT / "dist/macos-arm64/OrTTS.app")
    parser.add_argument("--out", type=Path, default=ROOT / "dist/OrTTS-macos-arm64-0.1.0.dmg")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("hdiutil packaging requires macOS")
    app, output = args.app.resolve(strict=True), args.out.resolve()
    if output.exists():
        parser.error(f"Refusing to overwrite existing DMG: {output}")
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="desktop-dmg-", dir=ROOT / "build") as temporary:
        stage = Path(temporary)
        shutil.copytree(app, stage / "OrTTS.app", symlinks=True)
        (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
        shutil.copyfile(ROOT / "desktop/packaging/DMG_README.txt", stage / "安装说明.txt")
        subprocess.run(["hdiutil", "create", "-volname", "OrTTS", "-srcfolder", str(stage),
                        "-fs", "HFS+", "-format", "UDZO", str(output)], check=True)
    subprocess.run(["hdiutil", "verify", str(output)], check=True)
    report = {"dmg": str(output), "bytes": output.stat().st_size,
              "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
              "dmg_signed": False, "app_signing": "ad-hoc", "notarized": False,
              "contents": ["OrTTS.app", "Applications -> /Applications", "安装说明.txt"]}
    output.with_suffix(".dmg.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
