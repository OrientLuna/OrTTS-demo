# Android ARM64

使用 `tools/build.py` 搭配本地 Android NDK 构建 ARM64 原生运行库与 CLI；Android Demo 应用源码位于 `android/` 目录，提供与 iOS / 桌面端一致的 **OrTTS 合成 / 其他语音合成 / 语音识别** 三标签页界面。

## 运行要求

- 运行时需要可写的私有 `TMPDIR` 与输出目录，并随包携带对应 NDK 版本的 `libc++_shared.so`。
- 可用 CPU 构建档位见 `profile.json` 与[CPU 构建档位](../../docs/CPU_PROFILES.md)。
