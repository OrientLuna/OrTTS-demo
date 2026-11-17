# Android ARM64

可直接从 [Latest Release](https://github.com/OrientLuna/OrTTS-demo/releases/latest) 下载已签名的 ARM64 APK；如需从源码构建：
- 完整三标签页 Android Demo APK：使用 `tools/build_android.py` 构建，详见[构建说明 / Android](../../docs/BUILD.md#android)。
- 独立 ARM64 原生运行库与 CLI：使用 `tools/build.py --platform android-arm64` 搭配本地 Android NDK 构建。

## 运行要求

- 运行时需要可写的私有 `TMPDIR` 与输出目录，并随包携带对应 NDK 版本的 `libc++_shared.so`。
- 可用 CPU 构建档位见 `profile.json` 与[CPU 构建档位](../../docs/CPU_PROFILES.md)。
