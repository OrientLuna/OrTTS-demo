#!/usr/bin/env python3
"""Build native CPU libraries and the Android application using submodule or prebuilt ortts-engine."""
import argparse
import os
import shutil
import subprocess
from pathlib import Path
from build import ANDROID_CPU_PROFILES

ROOT = Path(__file__).resolve().parents[1]


def find_runtime_lib(roots, name: str) -> Path:
    for base in roots:
        for cand in (base / "lib" / name, base / name, base / "bin" / name):
            if cand.is_file():
                return cand
    raise FileNotFoundError(f"Runtime library {name} not found in {[str(r) for r in roots]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine-dir", type=Path, help="Prebuilt ortts-engine build or install directory to inherit")
    p.add_argument("--engine-source", type=Path, default=ROOT / "third_party/ortts-engine")
    p.add_argument("--ndk", required=True, type=Path)
    p.add_argument("--sdk", required=True, type=Path)
    p.add_argument("--java", required=True, type=Path)
    p.add_argument("--gradle", required=True)
    p.add_argument("--ninja", type=Path)
    p.add_argument("--cmake", default="cmake")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--model-assets", type=Path)
    p.add_argument("--release", action="store_true")
    p.add_argument("--cpu-auto", action="store_true", help="Package baseline, DotProd and I8MM CPU modules together")
    p.add_argument("--android-isa", default="armv8.2-a+dotprod+i8mm+fp16", choices=ANDROID_CPU_PROFILES)
    p.add_argument("--qa", action="store_true")
    p.add_argument("--p3-four-preview-id", action="store_true", help="Use suffixed com.orient.ortts.p3fourfeature package id")
    a = p.parse_args()

    out = ROOT / "build/android-app-native"
    libs = ROOT / "build/android-app-libs/arm64-v8a"
    cmd = [
        "python3", str(ROOT / "tools/build.py"),
        "--platform", "android-arm64",
        "--engine-source", str(a.engine_source.resolve()),
        "--out", str(out),
        "--ndk", str(a.ndk.resolve()),
        "--android-jni",
        "--jobs", str(a.jobs),
        "--cmake", a.cmake,
    ]
    if a.engine_dir:
        cmd += ["--engine-dir", str(a.engine_dir.resolve())]
    if a.cpu_auto:
        cmd += ["--cpu-auto"]
    else:
        cmd += ["--android-isa", a.android_isa]
    if a.ninja:
        cmd += ["--ninja", str(a.ninja.resolve())]
    subprocess.run(cmd, check=True)

    libs.mkdir(parents=True, exist_ok=True)
    for stale in ("libaudiocpp.so", "libonnxruntime.so", "libsherpa-onnx-c-api.so", "libespeak-ng.so"):
        (libs / stale).unlink(missing_ok=True)

    for n in ("libortts_jni.so", "libortts_device.so"):
        shutil.copyfile(out / n, libs / n)

    engine_roots = [a.engine_dir.resolve()] if a.engine_dir else [out / "ortts_engine", out]
    shutil.copyfile(find_runtime_lib(engine_roots, "libortts.so"), libs / "libortts.so")

    cpu_libs = [
        "libggml.so",
        "libggml-base.so",
        "libggml-cpu-android_armv8.0_1.so",
        "libggml-cpu-android_armv8.2_2.so",
        "libggml-cpu-android_armv8.6_1.so",
    ]
    for n in cpu_libs:
        if a.cpu_auto:
            shutil.copyfile(find_runtime_lib(engine_roots, n), libs / n)
        else:
            (libs / n).unlink(missing_ok=True)

    prebuilt = next(
        p for p in (a.ndk / "toolchains/llvm/prebuilt").iterdir()
        if (p / "sysroot/usr/lib/aarch64-linux-android/libc++_shared.so").is_file()
    )
    shutil.copyfile(prebuilt / "sysroot/usr/lib/aarch64-linux-android/libc++_shared.so", libs / "libc++_shared.so")

    strip_tool = prebuilt / "bin/llvm-strip"
    to_strip = ["libortts.so", "libortts_jni.so", "libortts_device.so", "libc++_shared.so"] + (cpu_libs if a.cpu_auto else [])
    if strip_tool.is_file():
        subprocess.run([str(strip_tool), "--strip-unneeded", *[str(libs / n) for n in to_strip if (libs / n).is_file()]], check=True)

    gradle = [
        a.gradle, "--offline", "--no-daemon", "-p", str(ROOT / "android"),
        ":app:assembleRelease" if a.release else ":app:assembleDebug",
        "-PnativeLibsDir=" + str(libs.parent),
        "-PnativeCpuProfile=" + ("arm64-auto" if a.cpu_auto else ANDROID_CPU_PROFILES[a.android_isa]),
    ]
    if a.model_assets:
        gradle += ["-PmodelAssetsDir=" + str(a.model_assets.resolve())]
    if a.qa:
        gradle += ["-Pqa"]
    if a.p3_four_preview_id:
        gradle += ["-Pp3FourRoundFeature"]
    subprocess.run(gradle, check=True, env={**os.environ, "JAVA_HOME": str(a.java.resolve()), "ANDROID_HOME": str(a.sdk.resolve())})
    print(ROOT / ("android/app/build/outputs/apk/release/app-release-unsigned.apk" if a.release else "android/app/build/outputs/apk/debug/app-debug.apk"))
