"""Explicit, pinned model downloads. Never execute model content or replace old files."""
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from desktop.models import Cancelled, PACKAGES, safe_path, sha256_file, verify_pack


CHANNELS = {"ModelScope": "https://modelscope.cn/models/", "Hugging Face": "https://huggingface.co/"}
MAX_MANIFEST = 2 * 1024 * 1024
MAX_PACKAGE = 16 * 1024**3


def base_url(package, channel):
    revision = PACKAGES[package][1]
    suffix = "variants/ptq-q4/" if package == "Q4" else ""
    return f"{CHANNELS[channel]}OrientLuna/OrTTS-Qwen3-LFM-0.6B/resolve/{revision}/{suffix}"


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled("下载已取消，已验证文件保留")


def valid_https(address):
    parsed = urlparse(address)
    return parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password


class SecureRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not valid_https(newurl):
            raise ValueError("拒绝不安全的下载重定向")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_https(url, offset=0):
    if not valid_https(url):
        raise ValueError("下载地址需要无凭据 HTTPS")
    headers = {"Accept-Encoding": "identity"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    response = build_opener(SecureRedirect()).open(Request(url, headers=headers), timeout=20)
    if not valid_https(response.geturl()):
        response.close()
        raise ValueError("拒绝不安全的下载重定向")
    return response


def parse_manifest(data, package):
    if len(data) > MAX_MANIFEST or hashlib.sha256(data).hexdigest() != PACKAGES[package][2]:
        raise ValueError("下载清单 SHA256 不匹配")
    doc = json.loads(data)
    if (doc.get("schema") != "ortts-download-manifest-v1" or
            doc.get("revision") != PACKAGES[package][1] or
            doc.get("model_id") != "OrientLuna/OrTTS-Qwen3-LFM-0.6B"):
        raise ValueError("下载清单身份不匹配")
    files = doc.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 256:
        raise ValueError("下载清单文件数无效")
    seen = set()
    for entry in files:
        name, size, sha = entry.get("path"), entry.get("bytes"), entry.get("sha256")
        # Use the same path grammar as offline import, without creating any files.
        safe_path(Path.cwd().resolve(), name)
        if name in seen or name in ("DOWNLOAD_MANIFEST.json", "download-manifest.json"):
            raise ValueError("下载清单重复或保留路径")
        seen.add(name)
        if type(size) is not int or not 0 <= size <= MAX_PACKAGE or not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{64}", sha):
            raise ValueError("下载清单文件长度或 SHA 无效")
    if sum(e["bytes"] for e in files) > MAX_PACKAGE:
        raise ValueError("模型包超过下载预算")
    return doc


def guarded_target(root, name):
    target = safe_path(root, name)
    current = root
    for part in Path(name).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("下载目录不允许软链接")
    return target


def publish(temp, target):
    # Atomic no-clobber install. An unexpected existing file is never overwritten.
    os.link(temp, target)
    temp.unlink()


def download_error(exc):
    if isinstance(exc, HTTPError):
        if exc.code in (401, 403):
            return f"下载通道拒绝访问（HTTP {exc.code}）。请切换到 ModelScope 或确认该版本的访问权限。"
        if exc.code == 404:
            return "所选通道没有此版本（HTTP 404）。请切换下载通道；已有文件保留。"
        return f"下载服务器返回 HTTP {exc.code}。请稍后手动继续；已有文件保留。"
    if isinstance(exc, (TimeoutError, URLError)):
        return "网络连接失败或超时。请检查网络或切换通道，再选择相同位置继续。"
    return str(exc)


def retain_partial(temp, reason):
    retained = temp.with_name(temp.name + f".{reason}-{time.time_ns()}")
    os.link(temp, retained)
    temp.unlink()


def receive_file(root, target, entry, url, source, progress, cancel, notify):
    """Resume only checked 206 responses; promote only a full trusted SHA match."""
    size, digest = entry["bytes"], entry["sha256"]
    relative = str(target.parent.relative_to(root) / f".ortts-{digest}.part")
    temp = guarded_target(root, relative)
    h, offset = hashlib.sha256(), 0
    if temp.exists():
        progress(f"检查下载断点：{entry['path']}")
        if not temp.is_file() or temp.stat().st_size > size:
            raise ValueError("下载断点长度异常，已保留；请选择新的下载位置")
        with temp.open("rb") as partial:
            while block := partial.read(1024 * 1024):
                check_cancel(cancel)
                h.update(block)
                offset += len(block)
        if offset == size:
            if h.hexdigest() != digest:
                retain_partial(temp, "bad-sha")
                raise ValueError("完整下载断点 SHA256 不匹配，坏文件已保留；再次点击继续可重新下载")
            publish(temp, target)
            notify(size, 0, "复用已校验断点")
            return
    check_cancel(cancel)
    if shutil.disk_usage(root).free < size - offset + 64 * 1024**2:
        raise OSError("下载目录可用空间不足（另保留 64 MiB）")
    stream = source.open("rb") if source else (open_https(url, offset) if offset else open_https(url))
    with stream:
        if source:
            stream.seek(offset)
        else:
            code = getattr(stream, "status", 200)
            headers = getattr(stream, "headers", {})
            if headers.get("Content-Encoding", "identity").lower() != "identity":
                raise ValueError("下载响应压缩方式无效，未写入模型文件")
            if code == 206:
                expected = f"bytes {offset}-{size - 1}/{size}"
                if headers.get("Content-Range") != expected:
                    raise ValueError("服务器断点响应范围不匹配，原断点已保留；可切换通道重试")
            elif code == 200 and offset:
                # Range ignored: keep the old prefix as evidence, never append a full response.
                retain_partial(temp, "range-ignored")
                progress("服务器不支持续传，保留旧断点并重新下载当前文件")
                h, offset = hashlib.sha256(), 0
                if shutil.disk_usage(root).free < size + 64 * 1024**2:
                    raise OSError("重新下载所需空间不足，旧断点已保留")
            elif code != 200:
                raise ValueError(f"下载响应状态无效：{code}")
        check_cancel(cancel)
        flags = os.O_WRONLY | (os.O_APPEND if temp.exists() else os.O_CREAT | os.O_EXCL)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temp, flags, 0o600)
        received = offset
        phase = "本地复用" if source else "断点续传" if offset else "下载"
        progress(f"{phase}：{entry['path']}")
        with os.fdopen(fd, "ab") as output:
            while True:
                check_cancel(cancel)
                block = stream.read(min(1024 * 1024, size - received + 1))
                if not block:
                    break
                received += len(block)
                if received > size:
                    raise ValueError(f"下载文件超出声明长度：{entry['path']}")
                output.write(block)
                h.update(block)
                notify(received, 0 if source else len(block), phase)
        check_cancel(cancel)
        if received != size:
            raise ValueError(f"下载未完成，断点已保留，可继续：{entry['path']}")
        if h.hexdigest() != digest:
            retain_partial(temp, "bad-sha")
            raise ValueError(f"下载文件 SHA256 不匹配，坏文件已保留，请手动继续或切换通道：{entry['path']}")
        publish(temp, target)


@contextmanager
def package_lock(root):
    # Linux/macOS advisory lock is released automatically on process exit.
    import fcntl
    target = guarded_target(root, ".ortts-download.lock")
    fd = os.open(target, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("此目录正在被另一实例下载，请等待其完成或选择其他位置") from None
        yield
    finally:
        os.close(fd)


def download_pack(directory, package, channel, progress=lambda text: None, cancel=None, reuse_roots=(), transfer=lambda value: None):
    requested = Path(directory).expanduser().absolute()
    if any(p.is_symlink() for p in (requested, *requested.parents)):
        raise ValueError("下载根目录不允许软链接")
    requested.mkdir(parents=True, exist_ok=True)
    root = requested.resolve(strict=True)
    with package_lock(root):
        return _download_pack(root, package, channel, progress, cancel, reuse_roots, transfer)


def _download_pack(root, package, channel, progress, cancel, reuse_roots, transfer):
    manifest = guarded_target(root, "DOWNLOAD_MANIFEST.json")
    check_cancel(cancel)
    url = base_url(package, channel)
    if manifest.exists():
        data = manifest.read_bytes() if manifest.stat().st_size <= MAX_MANIFEST else b""
    else:
        progress("正在获取固定版本清单…")
        with open_https(url + "DOWNLOAD_MANIFEST.json") as response:
            data = response.read(MAX_MANIFEST + 1)
    doc = parse_manifest(data, package)
    check_cancel(cancel)
    if not manifest.exists():
        fd, name = tempfile.mkstemp(prefix=".manifest-", suffix=".part", dir=root)
        temp = Path(name)
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        publish(temp, manifest)
    total = sum(entry["bytes"] for entry in doc["files"])
    complete = 0
    network_bytes, started = 0, time.monotonic()

    def notify(received, network, phase):
        nonlocal network_bytes
        network_bytes += network
        transfer({"completed": complete + received, "total": total, "phase": phase,
                  "file": name, "speed": network_bytes / max(0.001, time.monotonic() - started)})

    for entry in doc["files"]:
        check_cancel(cancel)
        name, size, digest = entry["path"], entry["bytes"], entry["sha256"]
        target = guarded_target(root, name)
        if target.exists():
            progress(f"校验已有文件：{name}")
            if target.stat().st_size != size or sha256_file(target, cancel) != digest:
                raise ValueError(f"已有文件校验失败，已原样保留，请选择新的下载目录：{name}")
            notify(size, 0, "复用已校验文件")
            complete += size
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        guarded_target(root, name)
        source = None
        for reuse_root in reuse_roots:
            try:
                candidate = safe_path(Path(reuse_root).resolve(strict=True), name)
                if candidate.is_file() and candidate.stat().st_size == size and sha256_file(candidate, cancel) == digest:
                    source = candidate
                    break
            except (OSError, ValueError):
                continue
        receive_file(root, target, entry, url + quote(name, safe="/"), source, progress, cancel, notify)
        complete += size
    transfer({"completed": total, "total": total, "phase": "完整性复核", "file": "下载完成，正在校验模型包…", "speed": 0})
    return verify_pack(root, package, progress, cancel)
