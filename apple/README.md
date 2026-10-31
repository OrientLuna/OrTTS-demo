# Apple CPU Demo

macOS 提供命令行原型，iOS 提供 UIKit Demo。CPU 编译档位、兼容要求及性能口径见 [平台优化参数](../docs/CPU_PROFILES.md)。

## iOS 使用

选择 P3/P5、女声/男声，点击“下载 / 检查所选模型”。首次约2GB，请保持前台。使用固定 v0.2.0-preview 清单并验证内置清单SHA256、文件大小和SHA256；进度按文件计数，已校验文件跳过，未完成的大文件重新下载。

可导入包含 `native/`、`voices/`、可选 `P3/` 的原生模型文件夹，再检查补齐；不支持ZIP，不覆盖已有同名子目录。输入后点击“合成并播放”，先缓冲约480ms音频，再边生成边播放。停止清空播放队列并在生成块边界取消。成功结果保存到应用 `Documents/ortts-output.caf`，可重播及通过文件共享获取。键盘工具栏“完成”、点击外部、滑动页面均可收起键盘。

## 构建

先按 [运行时说明](../runtime/README.md) 准备锁定源码和 Apple 引擎。iOS baseline：

```sh
cmake -S apple -B build/apple-iphone -G Ninja \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=16.3 \
  -DORTTS_ENGINE_INSTALL="$PWD/build/engine-iphone/install" \
  -DORTTS_APP_CPU_PROFILE=arm64-baseline
cmake --build build/apple-iphone
```

模拟器将 sysroot 改为 `iphonesimulator`，引擎改为模拟器安装目录，用新的应用构建目录。真机需要自己配置匹配 Bundle ID 和设备的开发签名、描述文件，并签名嵌入框架；仓库不包含个人证书或描述文件。当前不提供 TestFlight、App Store 或任意手机直接安装的IPA。

macOS CLI：

```sh
cmake -S apple -B build/apple-mac -G Ninja \
  -DORTTS_ENGINE_INSTALL="$PWD/build/engine-macos/install"
cmake --build build/apple-mac
build/apple-mac/ortts-apple /path/to/native-model-pack P3 TRUSTED_BRIDGE_SHA '你好。'
afplay ~/Documents/ortts-output.caf
```

macOS 为离线CLI，没有图形界面、签名公证DMG或自动下载模型。

## 验证

iOS 真机和模拟器均编译通过。iOS Scene 生命周期、键盘收起功能已接入；模拟器验证了真实P3合成、音频文件、流播放启动/排空、播放中取消、缺失小文件下载补齐及全量校验。iPhone 17 实测见 [基准数据](../benchmarks/iphone17-cpu.json)。未验证全部文件选择器交互、真机音频中断、所有设备、长文EOS或音质。

显式开发启动参数：`--synthesis-smoke`、`--download-smoke`、`--cancel-stream-smoke`；文本与选择可用 `--benchmark-text TEXT`、`--benchmark-p5`、`--benchmark-male`。普通启动不自动下载或合成。性能日志不代表真实声学起播延迟。
