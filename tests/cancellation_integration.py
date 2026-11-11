#!/usr/bin/env python3
"""Opt-in Q4 CPU cancellation/reuse test. No model downloads or playback."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.engine import Config, Engine
from desktop.models import Cancelled, sha256_file, verify_pack


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "library_sha256": sha256_file(args.library), "samples": []}
    engine = None
    cancel = threading.Event()
    text = "你好，欢迎使用本地语音合成。"
    long_text = "这是一段安全停止测试。停止当前任务后，模型保持驻留，可以继续输入文字并合成。" * 4
    try:
        pack = verify_pack(args.model, "Q4")
        report["model_sha256"] = pack.manifest_sha256
        engine = Engine(args.library)
        assert engine.cooperative_cancel and engine.cancellable_create, "Build with the cancellation receipt first"
        token = engine.lib.ortts_cancel_token_create()
        assert token
        try:
            engine.lib.ortts_cancel_token_request(token)
            cfg = Config(C.sizeof(Config), os.fsencode(pack.root), b"P3", None, pack.bridge_sha256.encode(), 4, 0)
            handle = C.c_void_p()
            assert engine.lib.ortts_engine_create_cancellable(C.byref(cfg), token, C.byref(handle)) == 4
            assert not handle
        finally:
            engine.lib.ortts_cancel_token_free(token)
        report["pre_cancelled_create"] = "passed"

        def interrupted(action, delay):
            requested = []
            def stop():
                requested.append(time.perf_counter())
                cancel.set()
                engine.cancel()
            timer = threading.Timer(delay, stop)
            timer.start()
            try:
                try:
                    action()
                    raise AssertionError("operation returned success instead of CANCELLED")
                except Cancelled:
                    assert requested
                    return (time.perf_counter() - requested[0]) * 1000
            finally:
                timer.join()
                cancel.clear()

        report["loading_cancel_ms"] = interrupted(lambda: engine.load(pack, cancel=cancel), 0.1)
        assert not engine.handle
        for streaming in (False, True):
            engine.load(pack, streaming=streaming)
            handle, loads = engine.handle.value, engine.loads
            reference = engine.synthesize(text, cancel)
            expected = hashlib.sha256(reference.f32).hexdigest()
            for delay in (0.03, 0.2, 0.7, 0.05, 0.4, 1.0):
                record = {"mode": "streaming" if streaming else "offline", "delay_s": delay, "status": "running"}
                report["samples"].append(record)
                record["cancel_latency_ms"] = interrupted(lambda: engine.synthesize(long_text, cancel), delay)
                engine.load(pack, streaming=streaming)
                assert engine.handle.value == handle and engine.loads == loads, "resident engine was replaced"
                recovery = engine.synthesize(text, cancel)
                record.update(pcm_sha256=hashlib.sha256(recovery.f32).hexdigest(), same_handle=True,
                              engine_loads=engine.loads, recovery_api_ms=recovery.api_ms,
                              rss_kib=int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())], text=True)))
                assert record["pcm_sha256"] == expected, "cancelled request contaminated recovery"
                record["status"] = "passed"
                print(json.dumps(record), flush=True)
            if streaming:
                observed = []
                def sink(data, rate):
                    observed.append(len(data))
                    cancel.set()
                try:
                    try:
                        engine.synthesize(long_text, cancel, pcm_sink=sink)
                        raise AssertionError("callback cancellation returned success")
                    except Cancelled:
                        assert observed
                finally:
                    cancel.clear()
                assert hashlib.sha256(engine.synthesize(text, cancel).f32).hexdigest() == expected
                report["pcm_callback_cancel_and_recovery"] = "passed"
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        if engine:
            engine.close()
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
