# 手机 G2P 构建与许可

Kokoro、Kitten、Piper 在 iOS ARM64、iOS ARM64 模拟器和 Android ARM64 共用 eSpeak NG 1.52.0 动态库及字典。神经网络仍共用原有 ggml；没有增加 ONNX Runtime。

源码固定为 [eSpeak NG 1.52.0](https://github.com/espeak-ng/espeak-ng/tree/4870adfa25b1a32b4361592f1be8a40337c58d6c)。源码和字典需调用者准备，脚本不下载。字典必须是匹配 1.52.0 的编译数据（本机使用已有 Homebrew 1.52.0 数据）；自行生成参见上游 [构建说明](https://github.com/espeak-ng/espeak-ng/blob/1.52.0/docs/building.md)，在本机 native build 执行 `data` 目标，再将生成的 `espeak-ng-data` 目录传入。模型仍从共享 catalog 按固定版本下载，不随应用打包。

```sh
python3.12 tools/build_mobile_g2p.py --source /path/to/espeak-ng-1.52.0 \
  --data /path/to/espeak-ng-data --target android --out build/g2p-android \
  --ndk /path/to/android-ndk
```

iOS 分别使用 `--target ios --out build/g2p-ios` 和 `--target sim --out build/g2p-sim`。得到的 `mobile/` 含动态库/框架、字典、许可证和逐文件字典摘要。构建修改包括禁用不需要的 Sonic 下载、Apple 字节序兼容定义和 `N_PATH_HOME=4096`（默认160字节不足以容纳 iOS 沙盒路径）。不修改模型权重。

Android 在 `tools/build_android.py --speech` 构建参数后增加 `--g2p-install build/g2p-android/mobile`。底层 G2P 库保留16KiB链接页对齐，应用提取 native 库，以便通过真实绝对路径加载；字典首次使用时原子复制到应用数据目录。其他语音后端仍在同一 libaudiocpp.so 中。

Apple 应用 CMake 参数增加 `-DORTTS_G2P_INSTALL="$PWD/build/g2p-ios/mobile"`，模拟器换成对应目录。安装真机前除 OrTTS.framework 外，还需签名 `espeak-ng.framework`，最后签名应用。Kitten 构图需要超过 GCD 默认工作栈，Demo 用8MiB栈专用合成线程，并在原串行队列等待其完成；不在 UI 或音频 render 线程推理。播放器按原生采样率建立音频图，Piper 是22.05kHz。

## 发行义务

eSpeak NG 为 GPL-3.0-or-later，组合手机应用发行不能仅标 Apache-2.0。保留所有依赖许可、提供对应源码和构建修改；`build_mobile_g2p.py` 在构建目录生成 `espeak-ng-corresponding-source.tar.gz`。该归档不是整个应用的全部对应源码，发行时还需提供匹配版本的 OrTTS 源码、锁定上游和构建说明。签名密钥不属于归档内容。没有擅自重新许可第三方模型。

Piper 所测 Lessac medium 权重有独立语料/用途限制，菜单明确标记 restricted terms；开源发行不会解除这些限制。`distribution_cleared` 仍为 false，权重仅独立下载/导入。ZipVoice 仍为 SDK 可选入口，未接手机参考音频流程。

本轮真实执行结果保存在 `benchmarks/mobile-tts-expansion-20261108.json`；模拟器通过不是物理设备性能或听感认证。

`tools/test_mobile_speech_demo.py` 会导出成功合成的音频并核对原生采样率；`tools/check_mobile_demo_audio.py --input OUTPUT_DIRECTORY --out CHECK_DIRECTORY` 检查有限 PCM、非空信号及 Kitten 两音色波形不同（CAF 检查需 macOS 的 afconvert）。长句 `piper-long` 约18.8秒，覆盖超过原 Android12秒播放缓冲的场景。它们不替代试听或语音质量数据集。
