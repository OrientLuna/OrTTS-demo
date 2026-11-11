# 桌面客户端：开发与代理说明

此文面向维护者和编码代理。用户操作见 [README](README.md)；Linux 专属构建/验收见
[linux/AGENT_README.md](../linux/AGENT_README.md)。修改时保持用户说明简短，不把一次性日志堆回 README。

## 代码与平台边界

- `app.py` / `theme.py`：共享 Tk 界面和品牌资源；macOS 保留 Aqua 控件，Linux 使用 Clam。
- `models.py`：固定发布身份、清单 SHA、完整模型导入；当前桌面菜单为 0.6B Q4/Q8/历史版。
- `download.py`：共享 HTTPS 下载、断点、校验与文件复用；不依赖播放后端。
- `engine.py`：ctypes 显式声明 C ABI，自研模型使用 `runtime/include/ortts_engine.h`；不猜结构体。
- `worker.py`：单一任务队列与固定推理线程。创建、推理、读取线程本地错误及释放均在 worker。
- `audio.py`：有限 F32 校验、限幅转 PCM16 WAV、macOS `afplay` 合成后播放。
- `../linux/`：独立启动器和 PCM 回调队列 / `aplay` 流式播放。
- macOS 包为 arm64 CPU baseline；当前没有第三方 TTS/ASR 页面。不能因 speech 符号存在声称 UI 已接入。
- Windows 的 DLL、播放和打包未完成；不能把 macOS 产物改名当跨平台包。

## 生命周期与文件约定

1. 同模型、变体、音色、线程数与 streaming 配置复用句柄，配置变化先释放；默认空闲五分钟释放。
2. Tk 主线程通过 queue / after 更新 UI。cancel 是唯一允许跨线程的原生操作，不得并发 free。
3. 离线取消可能等本次计算返回；退出先取消并等待 worker，不强杀活跃句柄。
4. 音频复制后释放 C 对象；自研输出为 24kHz mono F32。保存时拒绝 NaN/Inf，限幅为 PCM16。
5. 导入只引用目录，不复制权重。再次导入完整 SHA 校验；合成前检查 inode/大小/纳秒时间等身份，变化后重验。这不是对恶意保留元数据篡改的持续扫描。
6. macOS 用户目录：`~/Library/Application Support/OrTTS Desktop/`；Linux 遵循 XDG。
   `settings.json` 保存版本、通道、下载位置和最近八个校验目录；`outputs/` 保存 WAV；`desktop-errors.log` 记异常。
   不自动删除输出，不写安装目录，不把个人模型路径带进发布包。

## 下载不变量

- 只在用户确认后联网；固定 revision 与清单 SHA 见 `models.py`，Q4 只支持 P3。
- 同时验证清单身份、路径、大小和逐文件 SHA；`bridge_manifest_sha256` 必须取自已验证清单中的 bridge/dequant 条目，不能自造信任根。
- HTTPS 重定向不能降级，不执行清单内容，不推测任意模型主机。
- 目标目录及其路径不能含软链接。macOS `/var` 是系统别名，自动化 fixture 使用规范化真实路径，不要为测试放宽生产保护。
- 同目录进程锁限单写者，退出自动释放；残留锁文件无需删除。
- `.part` 同目录写入，完整 SHA 通过后原子且不覆盖地安装。已有坏文件保留并报错。
- 续传仅接受匹配起止和总长的 206 / Content-Range；服务器返回 200 时保留旧断点并重下，不拼接完整响应。
- 坏 SHA 断点隔离保留；取消/断网保留完整文件及断点。再次选择同目录继续，不无限重试或绕过 401/403。
- 最近八个导入目录可逐文件按 SHA 本地复制复用，不扫描全盘或改动原目录。
- 包预算 16 GiB，逐文件检查磁盘余量并额外保留 64 MiB。进度用实际字节；网络均速不把本地复用算网络下载。

## macOS 构建

在仓库根目录运行，需 Python 3.12、可用 Tkinter、Xcode / CMake / Ninja。
先按 [BUILD](../docs/BUILD.md) 和 [PTQ 约定](../docs/APPLE_PTQ_HANDOFF.md) 准备源码：
`prepare_runtime.py → prepare_unified_runtime.py --release-compat → prepare_speech_runtime.py`。
最终 source 必须带有效 receipt，不得直接用上游树或复用另一功能组合的构建目录。

```sh
export ORTTS_RUNTIME_SOURCE="/path/to/prepared/audio.cpp"
python3.12 tools/build_engine.py --target macos-arm64 --profile arm64-baseline \
  --source "$ORTTS_RUNTIME_SOURCE" --liquidcodec --speech --out build/pc-engine-macos
python3.12 -m venv local/desktop-venv
local/desktop-venv/bin/python -m pip install -r desktop/packaging/requirements-macos.txt
local/desktop-venv/bin/python -m desktop.app
local/desktop-venv/bin/python desktop/packaging/build_macos.py
local/desktop-venv/bin/python desktop/packaging/build_dmg.py
```

引擎初次构建使用新目录；匹配 receipt 的重建按工具 `--rebuild` 处理。
默认 baseline，不假设所有 M 系列支持 I8MM。Linux / Windows 必须在目标 OS/架构环境构建依赖与验证。

### 打包、许可与元数据

- PyInstaller onedir `.app` 携带 Python/Tcl/Tk 与同一份原生库，不含权重。图标用 `assets/brand/ortts.icns`，窗口图用 `ortts-icon.png`。
- Conda 从本地包 receipt 收集依赖许可证；其他发行版用 `ORTTS_HOST_LICENSES` 指向准备好的 Python/Tcl/Tk/原生依赖许可证目录。不能只带 OrTTS 许可证。
- 逐个审计随包 Mach-O，不带 Homebrew/Conda 非系统绝对依赖。许可位于 `Contents/Resources/licenses/`。
- `dist/macos-arm64/BUILD_INFO.json` 记录打包开始时的 HEAD、仓库 dirty 与已暂存/未暂存/未跟踪计数（不含 ignored 文件）、时间、工具版本、源码 SHA、原生 receipt 和包内库 SHA。
- dirty 是整个仓库范围，其他遗留改动也会触发。Git 提交不会更新旧包元数据，需重新打包。
- `build_dmg.py` 包含 app、Applications 快捷方式和安装说明，拒绝覆盖已有 DMG；可用 `--out` 换文件名，生成 `.dmg.json` 并校验映像。
- 默认脚本只做 ad-hoc 应用签名，DMG 未签名、未公证。公开分发另做 Developer ID 签名、Hardened Runtime、公证与 staple；`codesign --deep --sign -` 不是正式签名流程。
- 不提交 build/dist/local、模型、音频、日志或个人证书私钥，不将本机构建称作正式 Release。

## 验收

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

Q8/历史版换匹配目录和 `--package Q8` / `Legacy`。smoke 覆盖真实中英文、完整播放/停止、WAV、复用、重载换音色、取消后恢复，包支持时测试 P5。
UI smoke 覆盖窗口队列、导入/保存/播放/取消及推理中退出，不等于验证原生文件选择器的全部人工操作。
GUI mock 测试覆盖下载确认、取消/继续、错误恢复；macOS 走 Aqua，Linux 需要 DISPLAY / Xvfb。
测试中先完成窗口初始化再模拟网络阻塞，Tk 对象在主线程回收；不要把 Tk 析构丢给后续 worker。

### 当前验证边界（2026-11-11）

- Apple M5 / macOS 27.2：新版 `.app`、只读 DMG 内应用 Q4/P3 中英文及播放、取消、复用通过；早前 Q8/P3/P5 通过。
- 新共享下载器在 Mac 验证了已有完整 Q4 包离线校验复用，以及 ModelScope 清单/LICENSE 小文件的真实 206 续传；不是重新下载完整大包。
- Hugging Face 该固定版本返回 401，不能声称所有通道通过。Q4 早前完整下载 92 文件已验 SHA。
- Linux 验收范围独立记录；Mac 跳过 ALSA 专属测试不代表 Linux 实体声卡成功。
- 声明最低 macOS 13.3，但其他系统版本、Intel 和其他机器未验证。自动 PCM/EOS 检查不等于听感或字错率合格。
- 性能仅报告匹配设备/供电/模型/线程/计时口径的观察值，不恢复不同条件下的历史排名。

原始报告、下载与 RTF 临时脚本保留在本地 `local/`，不作为运行依赖，不提交。

## 协作式取消构建（Q4/P3 CPU）

常规源码准备后可额外应用锁定取消补丁；不直接修改上游目录或绕过 identity：

```sh
python3.12 tools/prepare_cancellable_runtime.py \
  --source /path/to/prepared/audio.cpp --out _work/cancellable-runtime
python3.12 tools/build_engine.py --target macos-arm64 --profile arm64-baseline \
  --source _work/cancellable-runtime/audio.cpp --liquidcodec --speech --out build/pc-engine-macos-cancel
python3.12 tests/cancellation_integration.py \
  --library build/pc-engine-macos-cancel/install/lib/libortts.dylib \
  --model /path/to/q4-pack --output local/cancellation-report
local/desktop-venv/bin/python desktop/packaging/build_macos.py \
  --engine-build build/pc-engine-macos-cancel --dist-dir dist/macos-arm64-cancel
```

取消补丁的 SHA 与逐文件前后身份由 `vendor/cancellation.lock.json`、source receipt 及 build receipt 记录。
现有 ABI1 不改布局；宿主探测 `ortts_cooperative_cancel_version()`，没有符号或返回 0 时兼容旧行为，不能承诺提前停止。
`ortts_engine_create_cancellable` 使用创建前分配的 sticky token，宿主在 create 返回前保持令牌有效，cancel 与 free 用锁互斥。
单任务取消只清理请求/KV/解码状态，保持 model/session 与权重驻留；不得调用 `ortts_engine_free` 冒充任务清理。
取消中的首次加载没有可用模型，释放半初始化资源；已经完整加载的推理才适用驻留复用。
CPU 生成图与生成步可协作退出，Liquid translator 与 codec CPU 图均接入 abort callback；单个算子、内存分配或阻塞 I/O 不保证立即抢占。
此能力不等于所有 speech 后端都可取消，也不改变原执行互斥；禁止并行加载另一引擎或跨进程共享取消状态。
初版不支持 Android CPU 动态分派模块，准备工具会明确拒绝该组合。

codec 内部中断/状态复位可单独检查（测试目标默认不随发布库构建）：

```sh
cmake --build build/pc-engine-macos-cancel --target ortts-codec-cancel-test
build/pc-engine-macos-cancel/ortts-codec-cancel-test /path/to/q4-pack/native/lc/liquidcodec-MIXED_Q8_0.gguf
```

该测试在第三个图 abort 检查处确定性中断，复用同一 codec 权重并重置状态后，验证频谱与取消前完全相同，不代替扬声器或听感验收。
