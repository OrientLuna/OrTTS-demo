# OrTTS 桌面 Demo（macOS / Linux）

Python + Tkinter/ttk + ctypes 客户端，直接使用同平台的原生 OrTTS 库。
不启用浏览器服务、不引入第二套推理后端，不捆绑模型，默认不自动联网。
Linux 启动与打包见 [Linux README](../linux/README.md)；下文构建命令针对 macOS。
模型菜单、导入/下载界面、后台下载及校验均在 `desktop/` 共用，和播放后端无关。
当前新增下载界面/续传已在 Linux 验证，macOS 新版打包与 Aqua/真实音频尚需在 Mac 复验。

## 使用

构建后的程序：`dist/macos-arm64/OrTTS.app`，可双击或执行：

```sh
open dist/macos-arm64/OrTTS.app
```

1. 选择与本地模型一致的版本，默认是 **Q4（精简）/ P3**。
2. 点击“导入本地模型…”，选完整目录（包含 `DOWNLOAD_MANIFEST.json` 或
   `download-manifest.json`、`native/`、`voices/`，P3 还需 `P3/`）。
3. 清单固定 SHA256、每个文件大小和 SHA256 全部通过后，选择实际存在的音色。
4. 输入文字、合成；默认自动播放，也可手动播放、停止、另存为 PCM16 WAV。

也可选择 ModelScope / Hugging Face，点击“下载 / 继续…”；确认联网与费用未知后，
选择存放位置。进度条显示真实字节百分比，详情显示平均网络速率、文件名与校验阶段。
“取消下载”保留完整文件和断点；选择相同位置可继续。

下载时验证固定清单 SHA256、身份、文件长度、SHA 与路径，不覆盖已有文件；
HTTP Range 续传只接受匹配的 206/Content-Range，最后仍检查完整 SHA。服务器忽略
Range 时保留旧断点并安全重下当前文件；坏 SHA 文件隔离保留，不提升为可用模型。
401/403/404/网络错误显示可执行提示，不自动无限重试或绕过权限。
同一下载目录通过进程锁限制单写者，退出后锁自动释放。模型目录中的锁文件无需删除。

本地导入请选择包根目录而不是单个 GGUF。支持内置固定清单对应的
0.6B Q4（`v0.3.1-ptq-q4`）、标准 Q8（`v0.3.1-preview`）和历史版（`v0.2.0-preview`）；
Q4 只支持 P3，Q8 / 历史版可选 P3/P5。清单 SHA256 固定在 `models.py`，
选择的版本必须与本地包一致。目录可以位于任意用户可读位置，只引用原位置，
不复制权重。安装包不携带个人模型路径，不自动导入、不自动联网。

合成在线程队列中进行。相同模型、变体、音色和线程数复用句柄；切换配置时
释放重载；空闲 5 分钟释放。模型重新导入会完整校验，连续合成前检查文件身份、
大小和时间戳变化，变化后重新 SHA 校验。外部程序不应在运行时修改模型文件。

“停止”同时停止播放、请求取消推理。**离线取消可能等待当前计算返回**；
关闭窗口也会先请求取消，等待 worker 完成并释放，不强杀正在使用的句柄。

用户目录为 `~/Library/Application Support/OrTTS Desktop/`：

- `settings.json`：记住上次选择的版本、通道、下载位置和最近八个已校验目录（下次仍需重新校验）。
- `outputs/`：合成 WAV；不会自动清理，以免误删用户语音。
- `desktop-errors.log`：运行时或模型导入异常。

## 构建

在仓库根目录运行。先按 [构建说明](../docs/BUILD.md) 与
[PTQ 源码准备约定](../docs/APPLE_PTQ_HANDOFF.md) 完成
`prepare_runtime.py → prepare_unified_runtime.py --release-compat → prepare_speech_runtime.py`。
下例 `ORTTS_RUNTIME_SOURCE` 应指向最终已准备、receipt 验证通过的 `audio.cpp` 目录，
不是未经准备的上游树；输出目录需为新目录（已有匹配构建按引擎工具的 `--rebuild` 约定处理）：

```sh
export ORTTS_RUNTIME_SOURCE="/path/to/prepared/audio.cpp"
python3.12 tools/build_engine.py --target macos-arm64 --profile arm64-baseline \
  --source "$ORTTS_RUNTIME_SOURCE" \
  --liquidcodec --speech --out build/pc-engine-macos
python3.12 -m venv local/desktop-venv
local/desktop-venv/bin/python -m pip install -r desktop/packaging/requirements-macos.txt
local/desktop-venv/bin/python desktop/packaging/build_macos.py
```

源码运行（Python 需可用的 Tkinter）：

```sh
local/desktop-venv/bin/python -m desktop.app
```

打包为 onedir `.app`，带 Python/Tcl/Tk 与同一份原生运行时，无需目标机安装 Python。
使用 `assets/brand/ortts.icns`。构建脚本检查所有随包 Mach-O 的依赖，拒绝开发机
Homebrew/Conda 等非系统绝对依赖；记录源文件 SHA、原生构建 receipt 与包内库 SHA。
输出元数据：`dist/macos-arm64/BUILD_INFO.json`。

本机验证环境为 Python 3.12 + Tcl/Tk 8.6；解释器须可用 Tkinter。
Conda 环境从已安装组件的本地包 receipt 收集实际依赖许可证；使用其他 Python
发行版时，需通过 `ORTTS_HOST_LICENSES` 指定已准备的 Python、Tcl/Tk 及随包原生依赖
许可证目录。不能用单一运行时许可证替代这些组件的许可。

构建元数据在打包开始时记录实际 `git_head` 与仓库状态：`working_tree.dirty`、
已暂存 / 未暂存 / 未跟踪文件数。范围为整个仓库，忽略模型、日志、构建产物等
Git 已忽略文件；其他功能遗留改动也会使 `dirty=true`，不等于桌面代码自身有问题。
另记录生成时间、Python / PyInstaller 版本及逐文件源码 SHA。提交后需重新打包，
旧包的元数据不会随 Git 提交自动更新；最终 `.app`、DMG、日志和构建 receipt 不提交 Git。

### DMG

已有 `.app` 可直接制作拖入“应用程序”的磁盘映像，不重新构建运行时：

```sh
local/desktop-venv/bin/python desktop/packaging/build_dmg.py
```

输出 `dist/OrTTS-macos-arm64-0.1.0.dmg` 和对应 `.dmg.json` 指纹。
包含应用、`Applications` 快捷方式和安装说明；脚本拒绝覆盖已有 DMG，
并检查应用签名及映像校验和。**DMG 未签名、未公证，应用仍仅 ad-hoc 签名**。
对外分发应先完成应用的 Developer ID 签名，再打包、提交公证并 staple；
仅制作 DMG 不会让 Gatekeeper 自动信任应用。本地构建不需要个人证书。

### 本机开发其他平台的边界

UI/模型校验/绑定代码可以共用，但最终包必须使用目标 OS/架构的 Python、
Tk 和原生库：

- Linux：可在 Mac 的 Linux 虚拟机/容器构建；M 系列默认 ARM64，
  x86_64 构建需相应机器或仿真，并在目标桌面环境测试 GUI、音频和 `.deb`。
- Windows：优先 Windows 虚拟机或 Windows CI，先补齐并验证 `ortts.dll`，
  再打包客户端；Mac 上的 PyInstaller 不是 Windows 交叉打包器。
  Windows ARM64 与 x64 是不同交付目标，不能混用依赖。

macOS 使用 `afplay` 合成后播放，Linux 独立入口使用 PCM 回调队列送入 `aplay` 流式播放。
Windows 播放、DLL 构建/加载和打包仍待实现，不能据此声称已支持 Windows。

默认 `arm64-baseline`：适配 Apple Silicon，不把 I8MM 当所有 M 系列都有。
运行时包含 speech 能力，但此版没有展示未实现的第三方 TTS/ASR 页签。

## 测试

```sh
local/desktop-venv/bin/python -m unittest discover -s tests -p 'test_*desktop.py' -v
export ORTTS_MODEL_DIR="/path/to/complete/q4-model-pack"
dist/macos-arm64/OrTTS.app/Contents/MacOS/OrTTS \
  --smoke "$ORTTS_MODEL_DIR" --package Q4 \
  --state-dir "$PWD/local/desktop-test" --report "$PWD/local/desktop-test/runtime-report.json"
dist/macos-arm64/OrTTS.app/Contents/MacOS/OrTTS \
  --ui-smoke "$ORTTS_MODEL_DIR" --package Q4 \
  --state-dir "$PWD/local/desktop-app-test" --report "$PWD/local/desktop-app-test/gui-report.json"
```

`--smoke` 做真实推理、完整播放/停止、中文/英文 WAV、句柄复用、释放重载、
跨线程取消/恢复及包支持时的 P5 切换。`--ui-smoke` 驱动真实 Tk 窗口、导入队列、
合成/保存/播放/停止、英文复用和推理中退出。自动测试不会证明主观听感。
没有模型的单元测试覆盖错误清单、损坏/缺失文件、路径越界、取消校验、ABI 布局、
PCM 限幅/非有限值拒绝、缺库错误和 worker 安全结束。
另覆盖构建元数据的干净 / 已暂存 / 未暂存 / 未跟踪 / 忽略产物状态。
测试 Q8 / 历史版时，将目录与 `--package` 分别改为对应模型包和 `Q8` / `Legacy`。

## macOS 既有交付记录与边界

- 原 macOS arm64 版本的以下实测记录不代表新增共用界面/下载已经在 Mac 复验。Linux 新交付见 Linux README；未开发 Windows 版本。
- 应用设置最低 macOS 13.3，但旧系统、其他机器和 Intel Mac **未验证**。
- 仅 ad-hoc 本地签名，**未开发者签名、未公证**，不声称可免 Gatekeeper 提示分发。
- Q4 已在本机实际下载 92 个文件并全部校验，打包版的中文/英文、播放、取消/恢复与重载实推通过；仅支持 P3。
- 模型包独立许可不被运行时许可替代。随包许可证位于应用 Resources 的 `licenses/`；
  不打包 eSpeak 和未使用模型，不作性能比较/RTF 承诺。
