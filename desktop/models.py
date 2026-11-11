"""Offline model import. Trust roots match apple/OwnModelPackage.m."""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import hashlib
import json


PACKAGES = {
    "Q4": ("0.6B · Q4量化（精简）", "v0.3.1-ptq-q4", "26cf9f79991fa38eb766541ee34a964c4521cb5130fd61034dad3302bebd0017"),
    "Q8": ("0.6B · Q8量化（均衡）", "v0.3.1-preview", "2b23c30f658e88ce8b3215e4ea24dacf8898ffca159a7908f61a8942e9e93720"),
    "Legacy": ("0.6B · LFM解码（历史版）", "v0.2.0-preview", "20e24b0bc7fd0e3b58e31dcb409c07102f9e0ddf33f8e70153f69073271b5f7f"),
}
VOICE_NAMES = {"female": "女声1", "female_2": "女声2", "male": "男声1", "male_2": "男声2"}


class Cancelled(Exception):
    pass


def safe_path(root, name):
    if not isinstance(name, str) or "\\" in name or "\x00" in name:
        raise ValueError("模型清单包含非法路径")
    p = PurePosixPath(name)
    if p.is_absolute() or not p.parts or any(s in ("", ".", "..") for s in name.split("/")):
        raise ValueError(f"模型路径越界：{name}")
    target = root.joinpath(*p.parts).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"模型路径越界：{name}")
    return target


def sha256_file(path, cancel=None):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while data := f.read(1024 * 1024):
            if cancel is not None and cancel.is_set():
                raise Cancelled("已停止模型校验")
            h.update(data)
    return h.hexdigest()


@dataclass(frozen=True)
class ModelPack:
    root: Path
    package: str
    manifest_sha256: str
    bridge_sha256: str
    voices: tuple
    variants: tuple
    # Detect changes before reusing a verified directory/loaded engine.
    signatures: tuple

    def unchanged(self):
        try:
            return all(p.resolve().is_relative_to(self.root) and signature(p) == sig
                       for p, sig in self.signatures)
        except OSError:
            return False


def signature(path):
    s = path.stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def verify_pack(directory, package, progress=lambda text: None, cancel=None):
    root = Path(directory).expanduser().resolve(strict=True)
    candidates = [root / "DOWNLOAD_MANIFEST.json", root / "download-manifest.json"]
    manifest = next((p for p in candidates if p.is_file()), None)
    if manifest is None:
        raise ValueError("请选择完整模型目录（需含 DOWNLOAD_MANIFEST.json 或 download-manifest.json）")
    if not manifest.resolve().is_relative_to(root) or manifest.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("清单路径或大小无效")
    data = manifest.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != PACKAGES[package][2]:
        raise ValueError("模型清单 SHA256 不匹配：请选择对应的 Q4 / Q8 / 历史版，勿混用模型包")
    doc = json.loads(data)
    if (doc.get("schema") != "ortts-download-manifest-v1" or
            doc.get("revision") != PACKAGES[package][1] or
            doc.get("model_id") != "OrientLuna/OrTTS-Qwen3-LFM-0.6B"):
        raise ValueError("模型清单身份不匹配")
    files = doc["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= 256:
        raise ValueError("模型清单文件数无效")
    entries, signatures = {}, [(manifest, signature(manifest))]
    for i, entry in enumerate(files):
        if cancel is not None and cancel.is_set():
            raise Cancelled("已停止模型校验")
        name = entry["path"]
        if name in entries:
            raise ValueError(f"清单重复路径：{name}")
        path = safe_path(root, name)
        progress(f"校验模型 {i + 1}/{len(files)}：{name}")
        before = signature(path)
        if before[2] != entry["bytes"]:
            raise ValueError(f"模型文件大小不匹配：{name}")
        if sha256_file(path, cancel) != entry["sha256"] or before != signature(path):
            raise ValueError(f"模型文件 SHA256 不匹配或校验期间发生修改：{name}")
        entries[name] = entry
        signatures.append((root / name, before))
    decoder = doc.get("runtime", {})
    decoder = decoder.get("decoder", {}) if isinstance(decoder, dict) else {}
    bridge = decoder.get("dequant_manifest", "native/bridge/MANIFEST.json")
    if bridge not in entries:
        raise ValueError("清单中缺少受信任的 bridge/dequant 条目")
    voices = tuple(v for v in VOICE_NAMES if f"voices/{v}.f32" in entries)
    if not voices:
        raise ValueError("模型包没有可用音色")
    return ModelPack(root, package, digest, entries[bridge]["sha256"], voices,
                     ("P3",) if package == "Q4" else ("P3", "P5"), tuple(signatures))
