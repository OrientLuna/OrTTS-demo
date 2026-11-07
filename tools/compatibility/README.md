# 独立多模型兼容性探针

只在现有 audio.cpp 准备树上验证；不修改 OrTTS ABI1 或 OrTavern，不代表完成 SDK 迁移。macOS Apple Silicon，Python3.12+、NumPy、soundfile、CMake/Ninja、eSpeak-ng。权重显式下载入口：

```sh
python3.12 tools/compatibility/fetch_assets.py --out local/compat/assets
```

`assets.json` 固定维护者仓库revision、尺寸与SHA256，模型总约506MB（十进制）。模型许可证与资源依赖仍须各自核对；不随源码提交权重。

构建（source需先按项目说明准备）：

```sh
cmake -S _work/runtime-apple -B build/compat-cpu -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_DEPLOYMENT_TARGET=13.3 \
  -DAUDIOCPP_MODEL_SET=custom \
  '-DAUDIOCPP_MODELS=kokoro_tts,piper_tts,sense_asr,qwen3_tts' \
  -DAUDIOCPP_BUILD_C_API=ON \
  -DENGINE_ENABLE_NATIVE_CPU=OFF -DGGML_NATIVE=OFF \
  -DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+i8mm+fp16 \
  -DENGINE_ENABLE_METAL=OFF -DENGINE_ENABLE_CUDA=OFF \
  -DENGINE_ENABLE_VULKAN=OFF -DENGINE_ENABLE_OPENMP=OFF \
  -DGGML_OPENMP=OFF -DFETCHCONTENT_FULLY_DISCONNECTED=ON
cmake --build build/compat-cpu --target audiocpp audiocpp_cli -j4
export AUDIOCPP_ESPEAK_LIBRARY=/opt/homebrew/lib/libespeak-ng.dylib
export AUDIOCPP_ESPEAK_DATA=/opt/homebrew/share/espeak-ng-data
python3.12 tools/compatibility/run_smoke.py \
  --binary build/compat-cpu/bin/audiocpp_cli --assets local/compat/assets \
  --out outputs/compatibility-2026-11-07
```

需目标CPU确实支持I8MM，其他设备修改档位；本切片未验证Intel/iOS/Android。不启用上游全模型集。eSpeak库/字典是独立依赖，`otool -L`只显示直接链接，不能漏算dlopen加载的库。

C ABI探针：

```sh
xcrun clang++ -std=c++17 -I _work/runtime-apple/include \
  tools/compatibility/probe.cpp -L build/compat-cpu/bin -laudiocpp \
  -Wl,-rpath,"$PWD/build/compat-cpu/bin" -o build/compat-cpu/bin/compat-probe
xcrun clang++ -std=c++17 -I _work/runtime-apple/include \
  tools/compatibility/stream_probe.cpp -L build/compat-cpu/bin -laudiocpp \
  -Wl,-rpath,"$PWD/build/compat-cpu/bin" -o build/compat-cpu/bin/compat-stream-probe
build/compat-cpu/bin/compat-stream-probe local/compat/assets/Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf
```

`probe.cpp` 还需输出目录中的 `reference-zh.f32`（16kHz mono float32小端原始PCM），传入该目录与可选CYCLES（1..10）。参考音频可取模型作者公开样本：`https://huggingface.co/FunAudioLLM/SenseVoiceSmall/resolve/3847d57b6bdf2dd8875cb1508d2af43d80a16bf7/example/zh.mp3`，转为16k mono WAV存为输出目录 `reference-zh.wav` 后，使用soundfile以float32读取、NumPy `tofile`导出。`run_smoke.py` 缺少该文件会跳过公开音频识别，不会冒充已测。

探针只认证结构、错误处理与本机执行。ASR纯静音产生文本目前为已发现问题，smoke返回0只表示命令状态符合预期，并非ASR质量通过。完整结果与限制见 `docs/research/multi-model-local-validation-2026-11-07.md`。

## 内存定位与额外模型

`instrument_memory.py --source SOURCE --out NEW_SOURCE` 创建独立副本并加入分配日志；默认原源树不改动。用原来的selected-family构建命令指向新源树即可。`alloc_profile.h`记录图buffer、最大节点及采样RSS，CPU helper记录工作区增长；诊断日志和已标记的峰值footprint不是同一指标。

`kokoro-plbert-liveness.patch` 是仅PL-BERT图存活区间复用的候选补丁，可在独立干净源副本用 `patch -p1 -d NEW_SOURCE < tools/compatibility/kokoro-plbert-liveness.patch` 试验。它不包含诊断代码，也没有并入vendor锁或App。仅本机CPU通过固定seed波形哈希与3请求batch回归，未认证其他后端。

额外资产使用 `fetch_assets.py --manifest tools/compatibility/extra-assets.json --out local/compat/assets` 显式下载Moonshine Tiny和Kitten Mini，总约363MB。构建family分别为 `moonshine_asr`、`kitten_tts`；Kitten英语可用 `--voice-id Leo`。Moonshine固定adapter的streaming模式只在finalize转录，不能宣称实时partial。

本轮内存与框架结果见 `docs/research/memory-and-framework-support-2026-11-07.md`、`benchmarks/kokoro-memory-and-extra-models-20261107.json`。不应采用未通过波形回归的全predictor复用实验。

## 第二轮同机对照（2026-11-07）

详见 `docs/research/unified-model-comparison-2026-11-07.md`，原始摘要 `benchmarks/unified-models-macos-20261107.json`。`four-assets.json` 固定Pocket/ZipVoice/Whisper资产，`f5-assets.json`固定独立F5包。F5是CrispASR格式，当前audio.cpp直接加载失败的结果需保留，不能标成统一底层成功。

`compare_local.py`按指定名字运行（例如`python3.12 tools/compatibility/compare_local.py piper pocket zipvoice moonshine sensevoice whisper`），每次通过新Python worker记录独立子进程峰值RSS和CPU秒。先准备依赖和参考：

```sh
mkdir -p outputs/unified-2026-11-07
# 使用Piper合成reference.wav，文本必须准确为：
# The northern wind crossed the quiet harbor.
# 将piper-1.wav转成16k单声道，保存asr-input.wav。
ffmpeg -y -i outputs/unified-2026-11-07/reference.wav -ar 24000 -ac 1 -f f32le outputs/unified-2026-11-07/reference-24k.f32
```

F5独立验证源码：CrispASR `34a3f0007b949a0868fc99c3c43d8920ec3e5e64`，ggml子模块`1b972bb754aa5f83e2d872ccf37a335717f6658d`。只需构建`f5-tts`目标，不必构建全模型CLI。Release、CPU4、Metal/OpenMP/Native OFF、ARM架构同上述。用`f5_native_probe.cpp`链接其`libf5-tts.a`、`libcrispasr-core.a`与对应ggml动态库、Apple Accelerate/Foundation；运行`compare_local.py f5-native`。该探针使用发布者默认32步、CFG与sway模型默认值，参考音频24k并按其CLI规则将低于0.1的RMS提升至0.1。输出F32 PCM和计时，无额外下载。独立执行器未链接进OrTTS。

原生F5探针链接命令（在仓库根，已构建上述`f5-tts`目标后）：

```sh
clang++ -O3 -std=c++17 -I_work/crispasr-compat/src \
 tools/compatibility/f5_native_probe.cpp \
 build/crisp-f5-compat/src/libf5-tts.a build/crisp-f5-compat/src/libcrispasr-core.a \
 -Lbuild/crisp-f5-compat/ggml/src -lggml -lggml-base -lggml-cpu \
 -framework Accelerate -framework Foundation \
 -Wl,-rpath,"$PWD/build/crisp-f5-compat/ggml/src" \
 -Wl,-rpath,"$PWD/build/crisp-f5-compat/ggml/src/ggml-blas" \
 -o build/crisp-f5-compat/f5-native-probe
```

完成所有运行后，用 `python3.12 tools/compatibility/summarize_local.py` 重新汇总JSON及终端比较表。Whisper用`total-load`估算推理边界；该差异已在报告明示。

后续SDK已落地于 `runtime/SPEECH.md`。当前PL-BERT补丁含持久位置/类型输入保护；此前仅改gallocr的首版在取消后复用时不安全，不能回填首版。生产源准备使用 `vendor/speech/` 锁文件和 `tools/prepare_speech_runtime.py`，不要将画像/分配日志源树作为SDK源。
