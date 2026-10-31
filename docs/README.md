# 文档索引

从 [项目首页](../README.md) 了解平台状态，再按任务选择文档。

| 任务 | 文档 | 范围 |
|---|---|---|
| Android 安装和使用 | [首页 Android](../README.md#android) | APK、设备要求、下载及导入 |
| iOS / macOS 使用 | [Apple Demo](../apple/README.md) | 应用功能、产物、安装边界及验证范围 |
| 从源码构建 | [BUILD](BUILD.md) | 环境、准备源码、平台构建命令 |
| 选择 CPU 优化参数 | [CPU_PROFILES](CPU_PROFILES.md) | 指令集、兼容性、优化构建示例 |
| 准备模型 | [MODEL_ASSETS](MODEL_ASSETS.md) | 清单、目录、平台导入方式 |
| 查看性能证据 | [BENCHMARKS](BENCHMARKS.md) | RTF、测试条件、原始数据及局限 |
| 嵌入其他应用 | [运行时](../runtime/README.md) | C ABI、Rust、PCM及取消、并发约束 |
| 许可与历史发行 | [NOTICE](../NOTICE.md)、[发行记录](../releases/RELEASE_NOTES.md) | 依赖许可、已有 Android 发行历史 |

`benchmarks/` 保存原始数据，`models/` 保存模型示例配置；模型权重和本机构建目录不纳入源码。各目录 README 解释相应模块；通用构建、模型和优化规则统一放在本目录。
