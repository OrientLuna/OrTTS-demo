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

## Apple

- [CPU 平台、编译档位与实测限制](CPU_PROFILES.md)
- [iOS Demo / macOS CLI 构建与使用](../apple/README.md)


先完成上面的运行时准备。Apple 需要完整 Xcode，以下使用 CPU baseline；优化版将引擎 `--profile` 与应用 `ORTTS_APP_CPU_PROFILE` 同时改为匹配档位，见 [CPU 参数](CPU_PROFILES.md)。

### macOS

```sh
python3.12 tools/build_engine.py --target macos-arm64 --profile arm64-baseline \
  --source _work/runtime --out build/engine-macos
cmake -S apple -B build/apple-mac -G Ninja \
  -DORTTS_ENGINE_INSTALL="$PWD/build/engine-macos/install"
cmake --build build/apple-mac
```

Intel Mac 将引擎目标改为 `macos-x86_64`、profile 改为 `x86_64-baseline`。本轮实测覆盖 Apple Silicon。

### iOS 真机

```sh
python3.12 tools/build_engine.py --target ios-arm64 --profile arm64-baseline \
  --source _work/runtime --out build/engine-iphone
cmake -S apple -B build/apple-iphone -G Ninja \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=16.3 \
  -DORTTS_ENGINE_INSTALL="$PWD/build/engine-iphone/install" \
  -DORTTS_APP_CPU_PROFILE=arm64-baseline
cmake --build build/apple-iphone
```

产物为 `build/apple-iphone/ortts-apple.app`，默认未签名。安装到真机前须自行使用匹配 Bundle ID 和设备的开发描述文件，签名嵌入的 `OrTTS.framework` 和应用。仓库不提供个人证书、描述文件或可通用安装的 IPA。最低 iOS 16.3、macOS 13.3；实际验证设备见 [基准](BENCHMARKS.md)。

### iOS 模拟器

引擎 target 改为 `ios-simulator-arm64`，输出改为 `build/engine-simulator`。应用用独立目录 `build/apple-sim`，sysroot 改为 `iphonesimulator`，`ORTTS_ENGINE_INSTALL` 指向模拟器框架，其他参数不变。

```sh
xcrun simctl install booted build/apple-sim/ortts-apple.app
xcrun simctl launch booted com.orient.ortts.prototype
```

需先在 Xcode 安装匹配 runtime 并启动模拟器；模拟器速度不代表 iPhone。独立引擎的 XCFramework 打包见 [运行时](../runtime/README.md#build)。
