# P3 新旧 codec 的隔离对照（2026-11-08）

不要将手机新旧模型包的 RTF 差异全部归因于 codec。两个包的 `female` 向量不同、P3 预测器存储不同，主模型 text embedding 从 F16 改成 Q8_0；历史低于0.5的 iPhone 记录还使用过 I8MM 编译档位。手机长时间矩阵达到 serious 温度，不能与冷却后的短句混算。

## 固定生成端，只换 codec

Apple M5、CPU4线程、同一 unified ggml 构建。固定旧包的 talker、P3 safetensors、female 向量、文本和 seed20261029，解码分支分别用旧 LFM B260K 与 LiquidCodec base100k MIXED_Q8_0。顺序 A/B/B/A/A/B，每个新进程两次调用，取第二次，得到每分支三个热观察值。

**六个会话、每会话两次输出的 generated codes SHA256 全部相同**：`bd9c6db53c1817e44b6a2057e0b63cc4fc844c6f53f5ab08c0f244f031978a3e`，70帧，输出均5.6秒。两个 codec 的 PCM 不同，不能把它们当作听感等效。

| 中位数 | 旧 LFM | LiquidCodec |
|---|---:|---:|
| 热 API RTF | 0.284 | 0.280 |
| 生成阶段 | 1381ms | 1404ms |
| 解码阶段 | 207ms | 164ms |

这组结果接近，没有 LC 导致大幅整体退化的证据。codec 只占总耗时一小部分。启用了现有 timing trace，不能当作无日志的 kernel 排名，也不能外推手机倍数。该实验刻意保留完整旧生成资产，RSS 不能代表当前精简 LiquidCodec 分发包。历史 probe 将 `ru_maxrss` 字段误标为 KiB，runner 已按 Darwin 的实际字节单位规范成 `peak_rss_bytes`。[结构化记录](../../benchmarks/codec-isolation-macos-20261108.json)。

当前完整新版生成包另有一次 Mac 诊断，保留相同旧女声向量和 LC，但主模型/P3来源改为新版：输出6.24s、热RTF0.278，codes已改变。因此它不是固定codes的codec隔离，只说明不能把输出长度变化当成纯执行开销。

## 真机线索

iPhone 17 baseline，LC 男声英语正常播放：总 API约2.27s，LC所有块 inclusive wall 合计约235.5ms，其中 codec约210.3ms。LC耗时占约一成，无法单独解释整段大幅变慢。CPU阶段串行、日志开启，阶段累计不是功耗。

冷却后、历史同文本、4线程、seed、P3、baseline，新版女声三次热RTF为0.452/0.492/0.502，温度均 fair。历史旧包女声在另一版本 I8MM 单次0.446、baseline单次0.573；音色、权重、版本及测量次数不同，不能按它们计算 codec 加速比。温度 fair/serious 是系统粗粒度状态，也不能据此计算热降频百分比。完整手机对照见[缓存与矩阵记录](../../docs/development/tts-warm-cache-2026-11-08.md)。

## 复现

使用已经通过校验的固定版本资产，不下载。已有 prepare/build unified 产物包含 probe：

```sh
cmake --build build/demo-unified-macos --target ortts-unified-probe -j 3
python3 experiments/codec-ab/run.py \
  --legacy-pack local/models --liquid-pack local/models-liquid \
  --probe build/demo-unified-macos/bin/ortts-unified-probe \
  --out outputs/codec-isolation-repeat
python3 experiments/codec-ab/inspect_gguf.py \
  local/models/native/model.gguf local/models-liquid/native/model.gguf
```

runner 在输出目录创建硬链接及一个 tokenizer 路径别名，不改输入资产；需同一文件系统。它调用已有 probe 的受校验流水线，拒绝 codes 不一致的结果。GGUF 检查器只读元数据并 seek 跳过词表，不 mmap 或展开所有权重。
