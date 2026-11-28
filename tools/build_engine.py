#!/usr/bin/env python3
"""Build or inherit the standalone OrTTS CPU plugin (`libortts`) without downloading SDKs or models."""
import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "linux-x86_64": ("x86_64-baseline", "x86_64-avx2"),
    "linux-aarch64": ("arm64-baseline", "arm64-dotprod", "arm64-i8mm"),
    "android-arm64": ("arm64-baseline", "arm64-dotprod", "arm64-i8mm", "arm64-auto"),
    "macos-arm64": ("arm64-baseline", "arm64-dotprod", "arm64-i8mm"),
    "macos-x86_64": ("x86_64-baseline", "x86_64-avx2"),
    "ios-arm64": ("arm64-baseline", "arm64-dotprod", "arm64-i8mm"),
    "ios-simulator-arm64": ("arm64-baseline",),
}


def git_head(path: Path):
    if not (path / ".git").exists() and not (path / ".git").is_file():
        return None
    r = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", choices=TARGETS, required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--generator", choices=["Ninja", "Unix Makefiles"], default="Ninja")
    p.add_argument("--engine-dir", type=Path, help="Prebuilt ortts-engine build or install directory to inherit")
    p.add_argument("--engine-source", type=Path, default=ROOT / "third_party/ortts-engine")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cmake", default="cmake")
    p.add_argument("--ninja", type=Path)
    p.add_argument("--ndk", type=Path)
    p.add_argument("--toolchain", type=Path)
    p.add_argument("--rebuild", action="store_true", help="Incrementally rebuild an existing matching receipt")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if a.profile not in TARGETS[a.target]:
        p.error("Profile does not match target")
    if not 1 <= a.jobs <= 16:
        p.error("Use 1..16 build workers")

    engine_source = a.engine_source.resolve()
    engine_dir = a.engine_dir.resolve() if a.engine_dir else None
    if not engine_dir and not (engine_source / "CMakeLists.txt").is_file():
        raise ValueError(f"Missing ortts-engine source at {engine_source}; init submodule or pass --engine-dir")

    out = a.out.resolve()
    apple = a.target.startswith(("macos", "ios"))
    cmd = [
        a.cmake,
        "-S", str(ROOT),
        "-B", str(out),
        "-G", a.generator,
        "-DCMAKE_BUILD_TYPE=Release",
        "-DORTTS_BUILD_ENGINE_PLUGIN=ON",
        "-DORTTS_CPU_PROFILE=" + a.profile,
        "-DORTTS_ENGINE_SOURCE=" + str(engine_source),
        "-DORTTS_ENGINE_PREFIX=" + (str(engine_dir) if engine_dir else ""),
        "-DORTTS_ANDROID_CPU_AUTO=" + ("ON" if a.profile == "arm64-auto" else "OFF"),
    ]
    if a.ninja:
        cmd.append("-DCMAKE_MAKE_PROGRAM=" + str(a.ninja.resolve()))
    if apple:
        cmd += ["-DCMAKE_OSX_ARCHITECTURES=" + ("x86_64" if a.target == "macos-x86_64" else "arm64"), "-DGGML_ACCELERATE=OFF"]
        if a.target.startswith("ios"):
            cmd += [
                "-DCMAKE_SYSTEM_NAME=iOS",
                "-DCMAKE_OSX_SYSROOT=" + ("iphonesimulator" if "simulator" in a.target else "iphoneos"),
                "-DCMAKE_OSX_DEPLOYMENT_TARGET=16.3",
            ]
        else:
            cmd.append("-DCMAKE_OSX_DEPLOYMENT_TARGET=13.3")
    elif a.target == "android-arm64":
        if not a.ndk:
            p.error("--ndk is required; no SDK will be fetched")
        cmd += [
            "-DCMAKE_TOOLCHAIN_FILE=" + str(a.ndk.resolve() / "build/cmake/android.toolchain.cmake"),
            "-DANDROID_ABI=arm64-v8a",
            "-DANDROID_PLATFORM=android-28",
            "-DANDROID_STL=c++_shared",
        ]
    elif a.target == "linux-aarch64" and platform.machine() not in ("arm64", "aarch64"):
        if not a.toolchain:
            p.error("Cross-build requires --toolchain pointing at an existing Linux ARM64 toolchain file")
        cmd.append("-DCMAKE_TOOLCHAIN_FILE=" + str(a.toolchain.resolve()))

    commands = [
        cmd,
        [a.cmake, "--build", str(out), "--config", "Release", "--target", "ortts_engine", "--parallel", str(a.jobs)],
        [a.cmake, "--install", str(out), "--config", "Release", "--component", "Engine", "--prefix", str(out / "install")],
    ]
    if a.target == "android-arm64" and not engine_dir:
        commands[-1].append("--strip")

    if out.exists():
        if not a.rebuild:
            raise ValueError("Use a fresh build directory, or --rebuild for the same receipt")
        prior = json.loads((out / "ENGINE_BUILD_RECEIPT.json").read_text())
        if prior.get("status") == "BUILDING":
            raise ValueError("Build still marked active; do not race another builder")
        if prior.get("target") != a.target or prior.get("cpu_profile") != a.profile or prior.get("argv", [None])[0] != cmd:
            raise ValueError("Existing build receipt does not match requested configuration")
    elif a.rebuild:
        raise ValueError("--rebuild requires an existing matching receipt")

    receipt = {
        "status": "PLAN_ONLY",
        "target": a.target,
        "cpu_profile": a.profile,
        "backend": "CPU",
        "engine_mode": "prebuilt" if engine_dir else "submodule",
        "engine_dir": str(engine_dir) if engine_dir else None,
        "engine_source": str(engine_source),
        "engine_commit": git_head(engine_source),
        "argv": commands,
        "models_included": False,
        "liquidcodec": True,
        "p3_four_round": True,
        "per_request_speaker": True,
    }
    print(json.dumps(receipt, indent=2))
    if a.dry_run:
        return
    if apple and platform.system() != "Darwin":
        raise RuntimeError("Apple SDK builds require a Mac with Xcode")
    if a.target == "linux-x86_64" and platform.machine() not in ("x86_64", "AMD64"):
        raise RuntimeError("Use an x86_64 host for this native target")

    out.mkdir(parents=True, exist_ok=a.rebuild)
    receipt["status"] = "BUILDING"
    receipt_file = out / "ENGINE_BUILD_RECEIPT.json"
    receipt_file.write_text(json.dumps(receipt, indent=2) + "\n")
    try:
        for command in commands:
            subprocess.run(command, check=True)
        runtime_contract = {
            "schema": "ortts-prebuilt-runtime-v1",
            "abi_version": 1,
            "engine_feature_version": 2,
            "speech_abi_version": 0,
            "asr_stream_abi_version": 0,
            "parallel_inference_version": 0,
            "target": a.target,
            "cpu_profile": a.profile,
            "backend": "CPU",
            "engine_mode": receipt["engine_mode"],
            "engine_commit": receipt["engine_commit"],
            "liquidcodec": True,
            "speech": False,
            "sherpa_asr": False,
            "p3_four_round": True,
            "per_request_speaker": True,
            "supported_families": {"tts": ["ortts_qwen3_lfm"], "asr": []},
            "recommended_bilingual_asr": None,
            "capabilities": {
                "tts": {
                    "ortts_qwen3_lfm": {
                        "api": "ortts_engine_*",
                        "streaming": True,
                        "per_request_speaker": True,
                        "speaker_vector_clone": False,
                        "reference_audio_clone": True,
                        "speed_control": False,
                        "sample_rate": 24000,
                        "channels": 1,
                        "languages": ["zh", "en"],
                    }
                },
                "asr": {},
            },
        }
        (out / "install/runtime.json").write_text(json.dumps(runtime_contract, indent=2) + "\n")
        receipt["artifacts"] = [
            {"path": str(f.relative_to(out)), "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
            for f in sorted((out / "install").rglob("*"))
            if f.is_file() and not f.is_symlink()
        ]
        receipt["cmake_cache_sha256"] = hashlib.sha256((out / "CMakeCache.txt").read_bytes()).hexdigest()
        receipt["status"] = "BUILT_NOT_TARGET_TESTED"
    except Exception as e:
        receipt.update(status="FAILED", error=str(e))
        raise
    finally:
        receipt_file.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
