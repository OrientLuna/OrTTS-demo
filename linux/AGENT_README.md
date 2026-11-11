# Linux 桌面：开发与代理说明

用户操作见 [README](README.md)。共享 UI、模型导入/下载安全规则、worker 生命周期及
macOS 构建见 [desktop/AGENT_README.md](../desktop/AGENT_README.md)，不要在两处维护重复规则。

## 架构

- `app.py` 使用共享 App，并注入 `linux/audio.py` 的 StreamPlayer。
- 原生 PCM 回调仅复制至有界队列，专用线程送入 `aplay`；Python 不执行模型推理。
- 首 PCM 就绪不等于扬声器发声；停止清空播放队列并请求取消；最终音频可重播/保存。
- 仅 0.6B Q4/Q8/历史包菜单，没有 1.7B、第三方 TTS/ASR；Q4 必须限制 P3。
- 用户目录遵循 XDG，启动器不自动安装或升级系统组件。

## 构建与兼容

原生引擎按仓库 `tools/build_engine.py` 和 source receipt 构建。组装脚本只接收已验证的同 ABI
Linux 库，不编译引擎、不下载模型、不打包 Python。

```sh
python3 -m linux.build --library /path/to/libortts.so --output /new/path/OrTTS-Linux
python3 -m unittest discover -s tests -p 'test_*desktop.py' -v
```

输出目录必须不存在；包含启动器、源码、品牌图及 `native/libortts.so`。
`BUILD.json` 记录平台、依赖、源码基座/未提交状态和文件 SHA。依赖系统 Python 3.10+、Tk 8.6+、
alsa-utils、中文字体以及 glibc/libstdc++/libgomp。不是通用 AppImage，也不是 `.deb`。

已有构建机本地验收包为 x86_64-baseline，但需 **GLIBC_2.43、GLIBCXX_3.4.32、CXXABI_1.3.15**
等符号，不能声称兼容 Ubuntu 22.04/24.04。对旧发行版分发须在相应兼容工具链重建，审计实际库依赖。
ARM64 与 x86_64 分开构建，不能复用 Android `.so` 或 macOS dylib。

## 自动化验收

真实原生 Q4 流式/GUI 检查需要 X 显示，无显示时可用 `xvfb-run -a`：

```sh
python3 -m linux.smoke --library /path/to/libortts.so \
  --model /path/to/q4-package --output /new/path/report
```

覆盖男女音色、短/长句、PCM 回调、停止、重载、WAV 保存及 UI 退出；截图需要 Pillow。
当前验收使用 ALSA null，**不能标为实体声卡播放或人工听感通过**。Q8/P5、历史包、实体声卡需另验。

共享网络小文件测试（会显式联网，但不下载权重）：

```sh
python3 -m linux.download_smoke --output /new/path/network-report
```

对每通道获取 pin 清单和 LICENSE，校验大小/SHA并尝试真实断点请求。
查看逐通道结果；脚本只要一通道成功即可返回 0，不能以退出码声称所有通道成功。
完整大包下载、弱网、真实设备播放要独立记录，不用 mock 或 null 结果替代。
