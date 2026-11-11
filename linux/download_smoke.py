"""Explicit small network check: Q4 manifest + LICENSE only, never model weights."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from urllib.parse import quote

from desktop.download import CHANNELS, MAX_MANIFEST, base_url, open_https, parse_manifest, receive_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"scope": "Q4 pinned manifest and LICENSE only", "channels": {}}
    for channel in CHANNELS:
        entry = {}
        report["channels"][channel] = entry
        try:
            url = base_url("Q4", channel)
            with open_https(url + "DOWNLOAD_MANIFEST.json") as response:
                data = response.read(MAX_MANIFEST + 1)
            doc = parse_manifest(data, "Q4")
            file = next(e for e in doc["files"] if e["path"] == "LICENSE")
            if file["bytes"] > 64 * 1024:
                raise ValueError("Small-file test budget exceeded")
            with open_https(url + quote(file["path"], safe="/")) as response:
                content = response.read(file["bytes"] + 1)
            if len(content) != file["bytes"] or hashlib.sha256(content).hexdigest() != file["sha256"]:
                raise ValueError("LICENSE size/SHA mismatch")
            entry.update(status="passed", manifest_sha256=hashlib.sha256(data).hexdigest(),
                         file_sha256=file["sha256"], received_bytes=len(data) + len(content))
            resume_root = Path(tempfile.mkdtemp(prefix="license-resume-", dir=args.output)).resolve()
            part = resume_root / f".ortts-{file['sha256']}.part"
            part.write_bytes(content[:32])
            phases = []
            receive_file(resume_root, resume_root / "LICENSE", file, url + "LICENSE", None,
                         lambda text: None, None, lambda received, network, phase: phases.append(phase))
            if (resume_root / "LICENSE").read_bytes() != content:
                raise ValueError("Real HTTP resume output mismatch")
            entry["range_check"] = "206_resume" if "断点续传" in phases else "200_safe_restart"
        except Exception as exc:
            entry.update(status="failed", error=str(exc))
    (args.output / "NETWORK.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not any(e["status"] == "passed" for e in report["channels"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
