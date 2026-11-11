# OrTTS Linux 桌面 Demo

本地 CPU 语音合成，沿用 macOS Demo 的界面与原生 C ABI。Python 仅负责界面、校验、下载与音频队列，不执行模型推理。包内不含模型。

## 启动

文件夹包：运行 `./ortts`。需要 Python 3.10+、Tk 8.6+、`alsa-utils`（`aplay`）、支持中文的字体及原生库所需的 glibc/libstdc++/libgomp。Debian/Ubuntu 对应组件通常为 `python3-tk alsa-utils fonts-noto-cjk`。本程序不会自动安装或升级系统组件。

源码运行（仓库根目录）：

```sh
python3 -m linux.app --library /path/to/libortts.so
```

构建机提供的本地验收包使用 x86_64-baseline 引擎，但依赖 **GLIBC_2.43、GLIBCXX_3.4.32、CXXABI_1.3.15** 等符号；不能直接视为 Ubuntu 22.04/24.04 通用包。在旧发行版分发前，须用对应兼容工具链重建原生库。

可选 `--state-dir /path/to/settings` 隔离设置与输出；默认使用 `$XDG_DATA_HOME/ortts-desktop` 或 `~/.local/share/ortts-desktop`。可选 `--audio-device DEVICE` 指定 ALSA 设备。`--audio-device null` **只供无声自动化检查**，不代表扬声器发声。

## 使用

1. 选择与模型包一致的版本。默认 0.6B Q4（仅轻量 P3）；Q8/历史版提供 P3/P5。菜单与 macOS 当前清单一致，尚未加入 1.7B 或第三方 TTS/ASR。
2. **本地导入**：选择完整目录，所有文件的大小与 SHA256 验证通过后才允许合成。模型不复制、不修改。音色仅列出包内已验证的条目。
3. **下载**：选择 ModelScope 或 Hugging Face，点击“下载 / 继续…”，明确确认联网后选择存放位置。按固定 revision 建子目录；进度条显示实际字节百分比，详情显示平均网络速率、文件与校验阶段，可随时“取消下载”。网络读取最多等待当前 20 秒超时，不自动换通道或无限重试。Linux/macOS 共用下载界面与核心，下载不依赖流式播放后端。
4. 输入文字，点击合成。默认边合成边播放：原生 PCM 回调复制至有界队列，专用线程送入 ALSA。首 PCM 就绪时间**不是**真实扬声器发声时间。无声卡/设备报错不影响导出完整 WAV。
5. “停止”取消生成并清空播放队列；重播和保存使用完整 24 kHz 单声道 PCM16 WAV。“释放模型”保留已校验目录，下次合成重载；空闲五分钟也会释放。

### 下载安全与离线复用

- 使用与 macOS 相同的固定清单 SHA256；不信任清单提供的任意下载主机。校验清单身份、相对路径、文件长度、SHA256；拒绝路径越界和下载目标软链接。
- 逐文件写入同目录 `.part`，验证后原子安装，**不覆盖已存在文件**。已有文件损坏时保留原样并报错，请另选新的存放位置。
- 再次选择同一目录时，已验证完整文件直接复用；最近八个已导入目录中的相同文件也可按 SHA 重新校验后本地复制复用（支持跨版本、跨重启）。不会扫描全盘、修改原模型或重复联网获取已有完整文件。
- 取消/断网保留已验证文件及稳定 SHA 命名的 `.part`。选择相同位置继续时先读取断点，再请求 HTTP Range；只接受起止位置/总长度匹配的 206 响应，最后验证完整 SHA 后才安装。服务器返回 200 时保留旧断点，安全重下当前文件，不错误追加。错误 SHA 文件改名隔离保留，下一次用户手动继续会重新下载该文件。
- 同一目标目录通过进程锁限制单写者，第二个实例会明确报错；退出后自动释放锁，残留锁文件无需删除。不要用外部程序同时修改下载目录。
- 配额上限 16 GiB，逐文件检查可用空间（额外保留 64 MiB）。下载前确认网络费用，遵守模型包内许可。
- 部分版本在 Hugging Face 可能未公开或返回 401；不绕过权限，请改用 ModelScope。通道失败会明确报错，不自动重复下载。

## 本地组装与测试

原生引擎按仓库 `tools/build_engine.py` 及其锁构建；也可传入已验证的同 ABI Linux 库。组装脚本不下载模型、不构建引擎、不打包 Python：

```sh
python3 -m linux.build --library /path/to/libortts.so --output /new/path/OrTTS-Linux
python3 -m unittest discover -s tests -p 'test_*desktop.py' -v
```

组装目录必须不存在，包含启动脚本、源码、品牌图与 `native/libortts.so`。`BUILD.json` 记录平台、依赖、源码基座/未提交状态和各文件 SHA256。这是依赖系统 Python/Tk/ALSA 的文件夹包，不是 AppImage，也不保证兼容任意 Linux 发行版；glibc/ISA 兼容性继承传入的原生库。

显式对现有 Q4 包执行 GUI/真实原生流式检查（需要 X 显示；无显示环境可使用 `xvfb-run -a`）：

```sh
python3 -m linux.smoke --library /path/to/libortts.so --model /path/to/q4-package --output /new/path/report
```

该检查用 ALSA null 验证男女音色、短/长句、流式回调、停止、重载、保存和 UI 退出；截图需要 Pillow。不得把 null/Xvfb 结果标注为人工试听或真实显示器验收。Q8/P5、历史版和实体声卡需另行验收。
