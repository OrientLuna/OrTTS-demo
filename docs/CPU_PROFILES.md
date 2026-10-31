# CPU 平台与优化参数

当前实现为 CPU 后端，未启用 Metal、Core ML 或 QNN。本轮 Apple 优化复用已有内核，通过编译指令集选择启用 DotProd/I8MM/FP16；未修改模型权重或推理算法。

## 引擎构建档位

使用 `tools/build_engine.py --target TARGET --profile PROFILE --source _work/runtime --out build/NEW_DIRECTORY`。输出目录必须是新目录，构建工具不下载源码、模型或 SDK。

| 目标 | 可选 profile | 选择依据 |
|---|---|---|
| `linux-x86_64`、`macos-x86_64` | `x86_64-baseline`、`x86_64-avx2` | AVX2 档位还要求 SSE4.2、FMA、F16C、BMI2 及操作系统 AVX 状态支持 |
| `linux-aarch64`、`android-arm64` | `arm64-baseline`、`arm64-dotprod`、`arm64-i8mm` | 按目标 CPU 支持选择 |
| `macos-arm64`、`ios-arm64` | `arm64-baseline`、`arm64-dotprod`、`arm64-i8mm` | 按实际设备验证；不能将本机结果泛化到所有 Apple 芯片 |
| `ios-simulator-arm64` | `arm64-baseline` | 模拟器用于功能验证，性能不代表 iPhone |

| profile | 指令集 / 特性 |
|---|---|
| `arm64-baseline` | `-march=armv8-a` |
| `arm64-dotprod` | `-march=armv8.2-a+dotprod+fp16` |
| `arm64-i8mm` | `-march=armv8.2-a+dotprod+i8mm+fp16` |
| `x86_64-baseline` | 禁用可选 AVX、AVX2、FMA 等扩展，使用工具链基线 |
| `x86_64-avx2` | 启用 SSE4.2、AVX、AVX2、BMI2、FMA、F16C |

不确定设备能力时使用 baseline。各档位是独立二进制，不自动跨库分派或回退；错误选择可能触发非法指令。iOS Demo 的 I8MM 版本在合成前检查 `hw.optional.arm.FEAT_I8MM`，不支持会拒绝合成，仍不等于通用兼容包。`tools/cpu_profile.py` 对 Apple 保守推荐 baseline。

## Apple 示例

需要完整 Xcode、CMake、Ninja 和 Python 3.12+。最低部署目标 macOS 13.3、iOS 16.3。引擎用 Ninja，避免上游同名对象在 Xcode 生成器下的链接问题。

```sh
python3.12 tools/build_engine.py --target ios-arm64 --profile arm64-i8mm \
  --source _work/runtime --out build/engine-iphone-i8mm
cmake -S apple -B build/apple-iphone-i8mm -G Ninja \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=16.3 \
  -DORTTS_ENGINE_INSTALL="$PWD/build/engine-iphone-i8mm/install" \
  -DORTTS_APP_CPU_PROFILE=arm64-i8mm
cmake --build build/apple-iphone-i8mm
```

应用的 `ORTTS_APP_CPU_PROFILE` 必须与实际链接框架一致；它显示档位并控制能力检查，不会改变框架编译参数。baseline 同时替换这两个配置。macOS 优化构建将引擎 target 改为 `macos-arm64`；CLI 构建见 [Apple Demo](../apple/README.md)。

脚本使用 Release，禁用主机 native 调优、OpenMP、GPU 后端，开启现有 GGML CPU repack。Apple 传入 `GGML_ACCELERATE=OFF`；本机实际 `GGML_BLAS=ON`、BLAS vendor 为 Apple，因此不能将其解释为完全不使用 Accelerate。实际配置以构建目录 CMakeCache 和 ENGINE_BUILD_RECEIPT 为准。

## Android 与 Linux

Android APK 的既有构建入口为 `tools/build_android.py`，原生命令行为 `tools/build.py`。后者的 `--android-isa` 默认 `armv8.2-a+dotprod+i8mm+fp16`，可显式选 `armv8-a`；该入口与上述插件 profile 参数不同，不要混用。现有发布 APK 要求 DotProd/I8MM/FP16，已验证范围见主 README。

Linux ARM64 交叉编译需现有 toolchain，Android 需 NDK。Linux 指令集兼容不代表 glibc/libstdc++ 兼容，应在计划支持的旧系统工具链上构建。Intel、Linux 目标的历史支持不构成本轮 Apple 任务的重新验收。

## 实测与限制

iPhone 17 标准版 8GB/256GB，4线程、女声、CPU，分别启动应用，未锁频：

| 输入 | 模型 | baseline RTF | I8MM RTF |
|---|---|---:|---:|
| 默认短句 | P3 | 0.573 | 0.446 |
| 同一长文本 | P3 | 0.706 | 0.662 |
| 同一长文本 | P5 | 0.991 | 0.939 |

单次观测中短句 RTF 降低约22%，长文约5%～6%；输出长度不同，不能视为等工作量内核加速比。baseline 长文 P3 为40.96秒，疑似触及513 token限制，未验证EOS和朗读完整性。API计时不含校验、模型创建和排队播放结束，包含PCM回调；首PCM不等于听到声音。平均RTF不能保证无播放间隙。未做人工听感评审。

原始输入、时长和测量口径见 [iPhone 数据](../benchmarks/iphone17-cpu.json)；Android 数据见 [Android 数据](../benchmarks/android-cpu.json)，跨设备比较必须统一输入、seed、冷热请求和参数。本轮 M5 验证包括 baseline/I8MM 的构建与实际合成；iPhone 验证包括 I8MM 能力检查、合成和流播放。尚无覆盖所有 Apple 设备的验证或通用自动回退。
