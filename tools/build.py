#!/usr/bin/env python3
"""Configure/build OrTTS runtime & CLI binaries using submodule or prebuilt ortts-engine."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID_CPU_PROFILES = {
    "armv8-a": "arm64-baseline",
    "armv8.2-a+dotprod+fp16": "arm64-dotprod",
    "armv8.2-a+dotprod+i8mm+fp16": "arm64-i8mm",
}


def git_head(path: Path):
    if not (path / ".git").exists() and not (path / ".git").is_file():
        return None
    r = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def commands(a):
    auto = getattr(a, "cpu_auto", False)
    if auto and a.platform != "android-arm64":
        raise ValueError("--cpu-auto requires android-arm64")
    engine_dir = getattr(a, "engine_dir", None)
    engine_src = getattr(a, "engine_source", ROOT / "third_party/ortts-engine").resolve()
    if not engine_dir and not (engine_src / "CMakeLists.txt").is_file():
        raise ValueError(f"Missing ortts-engine source at {engine_src}; init submodule or pass --engine-dir")

    out = a.out.resolve() if a.out else ROOT / "build" / a.platform
    cmd = [
        a.cmake,
        "-S", str(ROOT),
        "-B", str(out),
        "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DORTTS_ENGINE_SOURCE=" + str(engine_src),
        "-DORTTS_ANDROID_CPU_AUTO=" + ("ON" if auto else "OFF"),
    ]
    if engine_dir:
        cmd.append("-DORTTS_ENGINE_PREFIX=" + str(engine_dir.resolve()))
    else:
        cmd.append("-DORTTS_ENGINE_PREFIX=")

    if a.platform == "android-arm64":
        cmd.append("-DORTTS_BUILD_ANDROID_JNI=" + ("ON" if getattr(a, "android_jni", False) else "OFF"))
        if not a.ndk:
            raise ValueError("--ndk is required; no SDK is downloaded")
        cmd += [
            "-DCMAKE_TOOLCHAIN_FILE=" + str(a.ndk.resolve() / "build/cmake/android.toolchain.cmake"),
            "-DANDROID_ABI=arm64-v8a",
            "-DANDROID_PLATFORM=android-28",
            "-DANDROID_STL=c++_shared",
            "-DORTTS_CPU_PROFILE=" + ("arm64-auto" if auto else ANDROID_CPU_PROFILES[a.android_isa]),
        ]
    else:
        if getattr(a, "android_jni", False):
            cmd.append("-DORTTS_BUILD_ANDROID_JNI=ON")
        if a.platform == "linux-x86_64":
            cmd.append("-DORTTS_CPU_PROFILE=" + getattr(a, "profile", "x86_64-avx2"))
        elif a.platform == "linux-aarch64":
            cmd += [
                "-DCMAKE_TOOLCHAIN_FILE=" + str(ROOT / "platforms/linux-aarch64/toolchain.cmake"),
                "-DORTTS_C_COMPILER=" + a.cc,
                "-DORTTS_CXX_COMPILER=" + a.cxx,
                "-DORTTS_CPU_PROFILE=" + a.arm_profile,
            ]
            if a.sysroot:
                cmd.append("-DORTTS_TARGET_SYSROOT=" + str(a.sysroot.resolve()))

    if a.ninja:
        cmd.append("-DCMAKE_MAKE_PROGRAM=" + str(a.ninja.resolve()))

    targets = ["ortts_jni", "ortts_device"] if getattr(a, "android_jni", False) else ["ortts-tts"]
    if auto and not engine_dir:
        targets += ["ggml-cpu-android_armv8.0_1", "ggml-cpu-android_armv8.2_2", "ggml-cpu-android_armv8.6_1"]
    return out, [cmd, [a.cmake, "--build", str(out), "--target", *targets, "--parallel", str(a.jobs)]]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cmake", default="cmake")
    p.add_argument("--ninja", type=Path)
    p.add_argument("--platform", choices=["android-arm64", "linux-aarch64", "linux-x86_64"], required=True)
    p.add_argument("--engine-dir", type=Path, help="Prebuilt ortts-engine build or install directory to inherit")
    p.add_argument("--engine-source", type=Path, default=ROOT / "third_party/ortts-engine")
    p.add_argument("--out", type=Path)
    p.add_argument("--ndk", type=Path)
    p.add_argument("--profile", default="x86_64-avx2", choices=["x86_64-baseline", "x86_64-avx2"])
    p.add_argument("--android-isa", default="armv8.2-a+dotprod+i8mm+fp16", choices=ANDROID_CPU_PROFILES)
    p.add_argument("--arm-profile", default="arm64-dotprod", choices=["arm64-baseline", "arm64-dotprod", "arm64-i8mm"])
    p.add_argument("--sysroot", type=Path)
    p.add_argument("--cc", default="aarch64-linux-gnu-gcc")
    p.add_argument("--cxx", default="aarch64-linux-gnu-g++")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--configure-only", action="store_true")
    p.add_argument("--android-jni", action="store_true")
    p.add_argument("--cpu-auto", action="store_true")
    a = p.parse_args()
    if not 1 <= a.jobs <= 16:
        p.error("jobs must be 1..16")

    out, cmds = commands(a)
    meta = {
        "platform": a.platform,
        "engine_mode": "prebuilt" if a.engine_dir else "submodule",
        "engine_dir": str(a.engine_dir.resolve()) if a.engine_dir else None,
        "engine_source": str(a.engine_source.resolve()),
        "engine_commit": git_head(a.engine_source.resolve()),
        "argv": cmds,
    }
    print(json.dumps(meta, indent=2))
    if not a.dry_run:
        out.mkdir(parents=True, exist_ok=True)
        for cmd in cmds[:1] if a.configure_only else cmds:
            subprocess.run(cmd, check=True)
        (out / "ORTTS_BUILD_RECEIPT.json").write_text(json.dumps({**meta, "configure_only": a.configure_only}, indent=2) + "\n")
