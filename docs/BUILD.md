# 构建

需要已有的 Python（3.12+）、CMake、Ninja；Android 另需 JDK17、Android SDK、NDK27 和 Gradle（本机离线构建使用 8.9）。

OrTTS 运行时核心已独立为 [ortts-engine](../third_party/ortts-engine)（内置 `ggml`、精简 `LiquidCodec`、`P3 four_round`、热切说话人与 `cpu-opt v3`），**不再需要多层级 `vendor/` 补丁或本地 `audio.cpp` / `llama.cpp` 子模块**。将 OrTTS 作为应用模块使用，见 [CPU 引擎与 Rust 接口](../runtime/README.md)。

## 两种构建模式

1. **子模块源码直编（默认）**：直接编译 `third_party/ortts-engine`（可通过 `--engine-source` 指定外部 `ortts-engine` 仓库路径）。
2. **继承预编译运行时（`--engine-dir`）**：在外部 `ortts-engine` 编译或 `--install` 后，通过 `--engine-dir /path/to/ortts-engine/build/<target>` 直接继承现成的 `libortts.so`（与 `--cpu-auto` 下的 `libggml*.so`），`OrTTS-demo` 仅编 `ortts_jni` / `ortts_device` / `ortts-tts`。

## Linux

### 从子模块直接构建

```bash
# 构建 CLI（ortts-tts）
python3 tools/build.py --platform linux-x86_64 --profile x86_64-avx2 --out build/linux-cli --jobs 8

# 构建与安装独立共享库插件（libortts.so）
python3 tools/build_engine.py --target linux-x86_64 --profile x86_64-avx2 --out build/linux-engine --jobs 8
```

### 直接继承外部 `ortts-engine` 产物

```bash
python3 tools/build_engine.py --target linux-x86_64 --profile x86_64-avx2 \
  --engine-dir /path/to/ortts-engine/build/linux-x86_64-x86_64-avx2 \
  --out build/linux-engine --jobs 8
```

运行 Linux 桌面前端：

```bash
python3 -m linux.app --library build/linux-engine/install/lib/libortts.so
# 或组装可移动文件夹包：
python3 -m linux.build --library build/linux-engine/install/lib/libortts.so --output /path/to/OrTTS-Linux
```

## Android APK

```bash
# 方式 A：从 submodule 源码全量构建（--cpu-auto 打包 baseline/dotprod/i8mm 三模块）
python3 tools/build_android.py --cpu-auto \
  --ndk /path/to/android-ndk --ninja /path/to/ninja \
  --gradle /path/to/gradle --sdk /path/to/android-sdk --java /path/to/jdk17 --jobs 8

# 方式 B：直接继承外部 ortts-engine 预编译产物构建 APK
python3 tools/build_android.py --cpu-auto \
  --engine-dir /path/to/ortts-engine/build/android-arm64-auto \
  --ndk /path/to/android-ndk --ninja /path/to/ninja \
  --gradle /path/to/gradle --sdk /path/to/android-sdk --java /path/to/jdk17 --jobs 8
```

如需单 ISA 构建，将 `--cpu-auto` 替换为 `--android-isa armv8.2-a+dotprod+i8mm+fp16`、`armv8.2-a+dotprod+fp16`（`arm64-dotprod`）或 `armv8-a`（`arm64-baseline`）。加 `--release` 可生成未签名 release APK，调试时可通过 `--model-assets` 在 APK 内携带权重；加 `--p3-four-preview-id` 可使用 `com.orient.ortts.p3fourfeature` 并装包名。

## Apple（macOS / iOS）

```bash
python3.12 tools/build_engine.py --target ios-arm64 --profile arm64-i8mm --out build/engine-iphone-i8mm --jobs 8
```

`OrTTS-demo` 与 `ortts-engine` 使用一致的纯 `ggml` + CPU 后端配置；macOS / iOS 构建步骤详见 [CPU 档位说明](CPU_PROFILES.md) 与 [Apple 说明](../apple/README.md)。
