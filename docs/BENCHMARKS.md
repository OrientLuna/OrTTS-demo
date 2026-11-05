# CPU性能参考

## Android

CPU4线程，原生Qwen生成端混合Q8＋LiquidCodec混合Q8。下表为男女声短中长测试中的热请求加权RTF，不含模型加载；越低越快。

| 设备 | 0.6B P3 | 0.6B P5 | 1.7B P3 | 1.7B P5 |
|---|---:|---:|---:|---:|
| 荣耀90 Pro · SM8475 · 16GB · Android 15 | 0.707 | 0.984 | 1.295 | 1.630 |
| OPPO Find N5 · SM8750 · 16GB · Android 16 | 0.693 | 0.898 | 1.095 | 1.216 |

测试使用此前固定参考音色，0.6B文本embedding为F16。新版0.6B文本embedding Q8主要减小权重文件与常驻表；荣耀另测短／长热RTF为P3 0.902／0.974、P5 1.181／1.249，此组为CLI且无AudioTrack，不直接与前台播放API算加速比。

设备未锁频，温度和调度会影响结果。OPPO的1.7B P3 Q8长句有一次7次播放欠载；平均RTF不等于播放连续性。新增中性女声已单独通过试听，未重做完整性能矩阵。

[本组配置数据](../benchmarks/android-liquid-q8.json) · [旧版LFM声学数据](../benchmarks/android-cpu-legacy-v0.2.json)

## Apple

iPhone 17 标准版，8GB/256GB，女声、4线程，同一长文本，分别启动应用、每组一次请求，未锁频：

| 模型 | baseline RTF | I8MM RTF |
|---|---:|---:|
| P3 | 0.706 | 0.662 |
| P5 | 0.991 | 0.939 |

默认短句 P3 的 RTF 分别为0.573、0.446。输出长度不同，不能作为固定工作量加速比。baseline 长文 P3 产生40.96秒音频，疑似触及513 token上限，未确认EOS或全文完整性。未做听感评审及播放欠载统计。

API耗时不含校验、模型加载和最终播放等待，包含PCM回调；首PCM不等于实际听到声音。平均RTF小于1不保证全程无间隙。Apple 口径与 Android 热请求不同，不能直接跨设备排名。原始输入、seed、时长和限制见 [iPhone 数据](../benchmarks/iphone17-cpu.json)。
