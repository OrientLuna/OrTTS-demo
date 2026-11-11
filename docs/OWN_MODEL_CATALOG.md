# 自研模型在线目录

Android / iOS Demo 启动时先读取内置固定版本及应用私有缓存；缓存超过 6 小时后后台刷新，亦可点击“更新可下载模型”。仅获取元数据，选择模型后才下载权重。刷新保留当前选择、已安装模型和历史缓存条目；推理期间延后应用目录更新。离线或服务异常时继续使用原目录。

## 发布端约定

无需为每次发布手动修改客户端：

1. 在 `OrientLuna` 名下发布 `OrTTS-*` 模型仓库。
2. 在默认 `master` 分支根目录或变体子目录发布 `DOWNLOAD_MANIFEST.json`，使用 `ortts-download-manifest-v1`，`model_id` 与仓库一致，提供安全的 `revision`、逐文件 SHA256、字节数、下载地址及 `selection_rules`。
3. 完整原生运行包应包含 `native/model.gguf`、男女音色及所声明的 P3 预测器、声学解码器资源。当前支持 qwen_lfm / LiquidCodec base、expanded，以及已实现的 PTQ 策略。新 schema、解码器或策略仍需客户端实现后才能被接受。

客户端匿名调用 ModelScope owner 模型列表 API（语义只读 PUT `/api/v1/models`）及仓库文件列表。官方接口参考：[ModelScope HubApi v1.32.0](https://github.com/modelscope/modelscope/blob/v1.32.0/modelscope/hub/api.py)。发现当前分支的根清单和嵌套变体，不遍历全部历史 tag；旧版本从缓存和内置条目保留。PTQ 的实际路径为 `variants/ptq-q4/DOWNLOAD_MANIFEST.json`，不能把该 tag 根目录的标准 Q8 清单当作 PTQ。

## 校验和边界

- 仅信任 HTTPS 官方 `OrientLuna/OrTTS-*` 命名空间；不是任意社区模型搜索器。
- 文件列表中的 40 位提交固定清单 URL，下载清单与其 SHA256 一致后才进入目录；权重沿用完整 SHA256 校验，失败不覆盖现有模型。
- 信任起点是 ModelScope HTTPS 和官方仓库控制权，**不等于离线数字签名**；目录 API 被控制时，SHA 自身不能证明发布者身份。
- 合并键为仓库 ID + 清单 SHA；内置条目优先，不自动更换正在使用的模型。下载仍遵循清单内资产地址及原有下载通道。
- 限制元数据响应 2 MiB、最多扫描 8 仓库、每仓库 8 清单、合并 64 条；有请求超时和约一分钟扫描预算。Apple 使用 NSURLSession 资源超时和响应完成后的大小检查，非逐块硬内存上限。
- 当前客户端音色接口只开放 `female`、`female_2`、`male`、`male_2` 中包内实际存在者；PTQ 只开放 P3。发现目录表示清单契约兼容，不代表所有模型已在所有手机完成加载、听感或性能验证。
- 不改变第三方 TTS/ASR 目录，不自动下载模型，不代替模型许可证审查。

## 2026-11-11 验证

Apple Foundation 和 Android Java 的实际网络目录实现均发现 3 个发布清单：0.6B 标准 Q8、0.6B PTQ Q4、1.7B 标准 Q8。两端版本、音色、P3/P5、大小一致。Apple 内置旧 LFM 条目一并保留，因此 UI 共 4 项。测试未下载权重、未运行合成或 RTF 对比。

离线夹具测试覆盖官方命名空间过滤、嵌套 PTQ、SHA 篡改、未知运行时、错误模型身份、越界路径、去重合并。源码见 `tests/apple_own_model_catalog.m`、`tests/OwnModelCatalogTest.java`，夹具只包含公开模型清单元数据。Apple 设备与模拟器 Demo、Android Debug/未签名 Release 构建通过。Android CPU-auto 原生模块完成构建；未在本轮获得 Android 真机 ISA 分派或性能证据。

可复现检查（macOS、JDK 17；使用现有 `org.json` JVM jar，脚本不安装依赖）：

```sh
python3 tools/test_own_model_catalog.py --json-jar /absolute/path/json-20240303.jar
# 可选联网元数据及两端结果对比：
python3 tools/test_own_model_catalog.py --json-jar /absolute/path/json-20240303.jar --live
```

## 简化显示与跨版本复用

模型主菜单使用“0.6B · Q4量化（精简）、0.6B · Q8量化（均衡）、1.7B · Q8量化（增强）、0.6B · LFM解码（历史版）”；模式显示为“轻量版 / 标准版”，音色显示为女声、男声。原始模型 ID、版本号和解码器可通过“查看版本详情”核查。移动端默认选择 Q4 精简包＋轻量版 P3，不自动下载；Android 已保存的明确选择保留。iOS 默认打开中文合成页。P3需额外小预测器，P5用原生预测器，两者共用主模型；Q4包不支持P5。默认选择不代表性能或听感已优于其他配置。

两端下载前检查已安装自研包，按 **字节数 + SHA256** 匹配文件，再读取实际文件校验。内容完全一致即可复制到目标包，文件路径不同也能匹配；缺失、损坏或内容不同才下载。目标文件复制后再次校验，使用临时文件提交，不修改原版本。Android 复用已安装 release 目录，iOS 复用保留的已安装模型目录；尚未完成、没有安装清单的其他目录不作为来源。同一包中已通过校验的文件继续直接跳过。

这保证减少网络下载，**不保证跨版本只占一份磁盘空间**：安装包目录仍独立，采用安全复制，底层是否共享物理数据块取决于文件系统；未引入硬链接或统一资产缓存。完整下载大小仍是完整文件量，实际下载因本地资源而不同。下载进度也包含读取校验/复制时间，不是卡住。

按公开清单计算，标准 0.6B 与精简版的原生资源/音色/预测器约有 **372.6 MB** 完全相同；本地已安装对应完整文件时可省下这部分下载。该数值为清单交集，不是真机下载或存储基准。复用测试覆盖改名后内容匹配、损坏拒绝及两个安装副本相互独立。

## 下载进度与流量保护

自研模型和多模型 TTS/ASR 页面均显示单个文件名、已下载/清单总 MB 及百分比；大文件下载完成后继续进行 SHA256 校验和保存。进度不代表校验已完成。iOS 按下载任务字节计数每约250ms更新；Android按读取字节数节流更新。

默认只允许非计费网络下载权重。移动数据、系统标记的计费网络或无法确认网络时会弹窗，用户可取消等待Wi-Fi，或仅允许本次任务；授权不保存至下次下载。iOS 同时限制系统标记的低数据模式。元数据目录/小清单与模型权重传输分开处理，前者不受大文件提示流程影响。

Android 需要 ACCESS_NETWORK_STATE，未授权移动数据时将下载连接绑定到当前通过检查的非计费网络，并在传输期间重检。iOS 将 URLSession 的 allowsCellularAccess、allowsExpensiveNetworkAccess、allowsConstrainedNetworkAccess 默认设为 false。网络变更可能中断下载，下一次重新操作；不做大文件断点续传。网络分类依据操作系统，无法识别所有 Wi-Fi 上游是否实际使用流量。

官方 API 依据：[Android ConnectivityManager](https://developer.android.com/reference/android/net/ConnectivityManager#isActiveNetworkMetered())、[Apple allowsCellularAccess](https://developer.apple.com/documentation/foundation/urlsessionconfiguration/allowscellularaccess)、[Apple allowsExpensiveNetworkAccess](https://developer.apple.com/documentation/foundation/urlsessionconfiguration/allowsexpensivenetworkaccess)。

新增测试：iOS 模拟器通过本机生成的1MiB分块HTTP响应验证真实任务字节进度、默认禁用/显式允许的系统配置；Android JVM 测试验证未知网络默认拒绝、单任务授权、嵌套和异常后权限恢复。尚未实测物理手机Wi-Fi切蜂窝的计费流量；不将模拟器测试称为蜂窝实测。相关源码为 tests/apple_model_download_progress.m 与 tests/DownloadNetworkPolicyTest.java。
