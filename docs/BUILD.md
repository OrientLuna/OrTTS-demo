# 构建

需要已有的 Python（准备源码建议3.12+）、CMake、Ninja；Android 另需 JDK17、Android SDK、NDK27 和 Gradle。

将 OrTTS 作为应用模块使用，见[CPU 引擎与 Rust 接口](../runtime/README.md)，提供 Linux、Android、macOS 与 iOS 构建入口。

## 准备运行时

```bash
python3 tools/prepare_runtime.py --source-repo /path/to/audio.cpp --out _work/runtime
```

该脚本使用本地已有的上游源码和本仓库补丁，不修改源仓库。

## Android

```bash
python3 tools/build_android.py --source _work/runtime \
  --ndk /path/to/android-ndk --ninja /path/to/ninja \
  --gradle /path/to/gradle --sdk /path/to/android-sdk --java /path/to/jdk17
```

默认构建不含权重的 APK。调试时可将包含 `bundled/model.json` 及清单模型文件（或 `model.zip`）的目录传入 `--model-assets`，在 APK 内携带权重。

## 原生命令行

```bash
python3 tools/build.py --platform android-arm64 --source _work/runtime --ndk /path/to/android-ndk
python3 tools/build.py --platform linux-aarch64 --source _work/runtime \
  --cc aarch64-linux-gnu-gcc --cxx aarch64-linux-gnu-g++
```

工具链与目标系统须匹配；Android NDK 不能替代 Linux GNU 工具链。模型不随源码构建自动下载。

加 `--release` 可构建未签名 release APK，再使用自己的签名密钥签名。

## Apple 与平台优化

- [CPU 平台、编译档位与实测限制](CPU_PROFILES.md)
- [iOS Demo / macOS CLI 构建与使用](../apple/README.md)
