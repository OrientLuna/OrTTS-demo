# OrTTS 运行时/SDK 侧增量优化需求与实现记录（2026-11-27）

**分支**: `feat/sdk-runtime-incremental-v1`（基于 `6615117`）  
**状态**: 已落地实现，并在本机 Linux x86_64 与单台 Android 真机（`Qualcomm SM8475` / `AXVVUT3630003497`）完成端到端验证通过。

## 需求清单与优先级

### 1. 【P0】单次合成级热切换说话人（Per-Request Speaker Switching）

- **当前限制**: `ortts_engine_create(Config)` 绑定固定 `speaker_f32`，`ortts_engine_synthesize(Request)` 不接收说话人，导致宿主在音色试听或群聊多角色轮替时被迫销毁并冷重启整个引擎权重。
- **增量方案（两者同时支持，保持 ABI v1 向后兼容）**:
  - 在 `ortts_request` 尾部按 `struct_size` 增量扩展可选字段：
    - `const char *speaker_f32`：单次请求的 `.f32` 说话人向量路径（`NULL` 沿用引擎当前激活说话人）。
    - `const float *speaker_vector` + `size_t speaker_dim`：直接传入内存 `F32` 说话人向量（`1024`/`2048` 维，与 `speaker_f32` 互斥）。
  - 新增轻量 C ABI（复用原有 `e->execution` `ExecPolicy` 锁与校验）：
    - `ortts_engine_feature_version()`
    - `ortts_engine_set_speaker(engine, speaker_f32)` / `ortts_engine_set_speaker_ex(...)`
    - `ortts_engine_set_speaker_vector(engine, vector, dim)` / `ortts_engine_set_speaker_vector_ex(...)`
  - 底层通过锁定可选补丁 `vendor/speaker-switch/audio.patch`（配合 `tools/prepare_speaker_switch.py` 与 `tools/source_identity.py`）在 `Qwen3TTSSession::synthesize()` 中解析 `qwen3_tts.fixed_speaker_hex` / `qwen3_tts.fixed_speaker_f32`，只切换单次请求的 `fixed_voice_prompt` 而不卸载任何 Talker/Codebook/LiquidCodec 常驻权重。
  - Rust SDK (`ortts_engine::Engine`) 同步新增 `engine_feature_version()`、`set_speaker` / `set_speaker_ex` / `set_speaker_vector` / `set_speaker_vector_ex` 与 `synthesize_with_options` / `stream_with_options`（`SpeakerOverride::{Path, Vector}` + `SynthesizeOptions`）。

### 2. 【P1】合成请求支持基础语速参数（`speed`）

- **当前限制**: `ortts_request` 与 `ortts_tts_request` 仅接收固定字段，宿主 UI 的语速调节（`0.5x–2.0x`）无法透传。
- **增量方案**:
  - `ortts_request` 与 `ortts_tts_request` 均保留 `ortts_request_v1` / `ortts_tts_request_v1` 前缀布局并通过 `struct_size` 兼容扩展 `float speed` 字段（`0.0f` 或历史 v1 `struct_size` 等价于 `1.0f`；传入非零值须有限且在 `0.5..=2.0` 区间，否则返回 `ORTTS_INVALID`）。
  - Speech TTS 家族中原生支持语速控制的家族（`kokoro_tts`、`piper_tts`、`kitten_tts`、`zipvoice`）自动将 `speed` 写入请求参数生效；暂不支持的家族（自研 `ortts_qwen3_lfm`、`pocket_tts`、`moss_tts_nano`）对合法 `speed` 安全忽略，并在能力清单中明确声明 `speed_control: false`。
  - Rust SDK (`speech::Request`) 增加 `pub speed: Option<f32>` 与 `.with_speed(f32)`，自研 `SynthesizeOptions` 增加 `.with_speed(f32)`。

### 3. 【P1】音色目录与运行时能力自描述

- **当前限制**: `voices.json` 缺少风格描述、适用语种与试听样本路径；宿主被迫按 `family` 名称硬编码推断流式、克隆、语种和语速能力。
- **增量方案**:
  - 模型音色清单 `models/qwen3-lfm-0.6b/voices.json` 与 `tools/make_asset_manifest.py` 增加可选音色元数据：`description`、`persona`、`languages`、`preview_audio`（包内相对路径，便于零冷启动直接试听样本）。
  - 运行时能力接口 `ortts_speech_catalog_json()` 与 `runtime/models/catalog.example.json` 增补统一结构化字段 `"capabilities": {"tts": {...}, "asr": {...}}` 与 `"recommended_bilingual_asr"`：
    - TTS 统一字段：`api`、`streaming`、`per_request_speaker`、`speaker_vector_clone`、`reference_audio_clone`、`speed_control`、`sample_rate`、`channels`、`languages`。
    - ASR 统一字段：`api`、`streaming`、`true_streaming`、`streaming_kind`、`languages`、`sample_rate`、`recommended_bilingual`。
  - Rust SDK (`ortts_engine::speech`) 提供无外部依赖的 `runtime_capabilities()` / `parse_runtime_capabilities()` 解析结构体。

### 4. 【P2】离线 ASR 中英流式能力统一

- **当前限制**: `sense_asr` 仅整段离线；`moonshine_asr` 仅英文增量；中英流式需开启 `ORTTS_ENABLE_SHERPA_ASR`。
- **增量方案**:
  - 在 `runtime/src/sense_asr_stream.h` + `ortts_speech.cpp` 中为 `sense_asr` 提供内置按能量门限/静音切段与周期性假流式（`segmented-vad`）适配器，通过现有 `ortts_asr_stream_*` ABI 回调输出 `ORTTS_ASR_PARTIAL`、`ORTTS_ASR_SILENCE`、`ORTTS_ASR_LIMIT`、`ORTTS_ASR_FLUSH`，**所有 `--speech` 构建默认可用（无需 Sherpa/ORT 依赖）**。
  - 在 `ortts_speech_catalog_json()` 与 `runtime.json` 中显式通过 `recommended_bilingual_asr` 标注默认推荐中英包：启用 `ORTTS_ENABLE_SHERPA_ASR` 时优先推荐真流式 `zipformer_bilingual`（否则回退推荐内建分段流式 `sense_asr`），并明晰区分 `true_streaming` 与 `streaming_kind`（`true-streaming` vs `segmented-energy`）。

### 5. 【P2】开发/测试期 `rpath` 与预编译 `runtime.json` 版本契约

- **当前限制**: 开发机运行 Rust 测试时需手动注入环境变量指定动态库搜索路径；预编译产物缺少自描述兼容契约文件。
- **增量方案**:
  - `runtime/rust/build.rs` 新增显式开发开关 `ORTTS_EMBED_DEV_RPATH=1`（默认关闭，Release 打包保持不写入）：开启时且设置了 `ORTTS_LIB_DIR`，自动输出 `cargo:rustc-link-arg=-Wl,-rpath,<ORTTS_LIB_DIR>`（覆盖 macOS/Linux）。
  - `tools/build_engine.py` 在 `cmake --install` 时生成经过 Receipt SHA 封存的 `<install>/runtime.json`（`schema: "ortts-prebuilt-runtime-v1"`），固定包含 `abi_version`、`engine_feature_version`、`speech_abi_version`、`asr_stream_abi_version`、`parallel_inference_version`、`supported_families`（`tts` / `asr`）、`recommended_bilingual_asr` 与 `capabilities`；`tools/package_rust_apple_sdk.py` 同步将对应摘要写入 `DELIVERY.json`。

## 验证记录（2026-11-27 实测通过）

### 1. 构建产物与契约校验
- **源码准备**: `python3 tools/prepare_speaker_switch.py --source _work/local-runtime-6615117/four/audio.cpp --out _work/sdk-inc-20261127`（通过 `tools/source_identity.py` 锁定校验）。
- **Linux x86_64 (`x86_64-avx2` + LiquidCodec + Speech + Sherpa)**: `build/sdk-inc-linux-x86_64/install/{lib/libortts.so,runtime.json}`，`nm -D` 确认导出 `ortts_engine_feature_version`、`ortts_engine_set_speaker`、`ortts_engine_set_speaker_ex` 等符号；`runtime.json`（`schema: "ortts-prebuilt-runtime-v1"`, `abi_version: 1`, `engine_feature_version: 1`, `per_request_speaker: true`, `recommended_bilingual_asr: "zipformer_bilingual"`）已写入 `ENGINE_BUILD_RECEIPT.json` 产物校验清单。
- **Android arm64 (`arm64-i8mm` + LiquidCodec + Speech + Sherpa)**: `build/sdk-inc-android-arm64-i8mm/install/{lib/libortts.so,runtime.json}`，产物 SHA 已封存。

### 2. 主机 Linux Rust SDK 闭环测试（无 `LD_LIBRARY_PATH`）
- **dev rpath 开关对照**:
  - 未设置 `ORTTS_EMBED_DEV_RPATH` 编译 `cargo test --offline --no-run`：`readelf -d` 确认无 dev runpath（`NO_DEV_RPATH_WHEN_OFF`）。
  - 设置 `ORTTS_LIB_DIR=$PWD/build/sdk-inc-linux-x86_64/install/lib ORTTS_EMBED_DEV_RPATH=1` 且 `unset LD_LIBRARY_PATH` 运行 `cargo test --offline --manifest-path runtime/rust/Cargo.toml -- --nocapture`（注入 `RUNPATH: [.../build/sdk-inc-linux-x86_64/install/lib]`）：
    - `lib.rs / speech.rs` 单元测试：`24 passed; 0 failed`
    - `tests/sdk_incremental.rs`（绑定 `/mnt/hotdata/projects/ortts/runs/qwen-joint-qat-cpu-20261109/attempt-001/ptq/package` 真模型）：`2 passed; 0 failed`（单引擎实例内完成默认女声、`male.f32`、内存 `speaker_vector` 逐比特一致切换、默认不污染验证、`set_speaker` / `set_speaker_vector`、`speed=1.25` 安全忽略与 `speed=3.0` 拒绝）
    - `tests/speech_concurrency.rs`：`3 passed; 0 failed`（流式 ASR 列表返回 `["moonshine_asr", "sense_asr", "zipformer_bilingual", "streaming_paraformer"]`）
    - `tests/task_cancel.rs`：`4 passed; 0 failed`
    - `Doc-tests`: `2 passed; 0 failed`

### 3. 单台 Android 真机端到端验证（`Qualcomm SM8475` / `AXVVUT3630003497`）
使用 `tests/sdk_incremental_device_test.cpp` 交叉编译后推送至 `/data/local/tmp/ortts_sdk_inc_20261127/` 实测全部通过（`ALL_SDK_INCREMENTAL_CHECKS_PASSED`）：
- **ABI 与自描述能力**: `ortts_abi_version=1`、`ortts_engine_feature_version=1`、`ortts_speech_abi_version=1`、`ortts_asr_stream_abi_version=1`、`ortts_parallel_inference_version=2`，`ortts_speech_catalog_json()` 含 `capabilities.tts` / `capabilities.asr` 完整字段。
- **P0 单引擎热切说话人（`serial` P3 + LiquidCodec）**: `[PASS] female=21120 samples, male=40320 samples`（单次加载内覆盖默认女声、请求级 `male.f32`、内存 `male` 向量与路径逐样本一致、`set_speaker`、`set_speaker_vector` 及 `ORTTS_REQUEST_V1_SIZE` 兼容）。
- **P1 语速控制**:
  - `kokoro_tts`（`zf_xiaobei` 中文）单调时长验证：`0.75x=154800 > 1.0x=112800 > 1.5x=70800` frames；
  - `piper_tts`（Lessac 英文）单调时长验证：`0.75x=70144 > 1.0x=58368 > 1.5x=43008` frames；
  - `pocket_tts`：`speed=1.25` 安全忽略，`0.25` 返回 `ORTTS_INVALID`。
- **P2 中英流式 ASR**:
  - 内建分段流式 `sense_asr`（`silence_ms=600`）：`events=7`（触发 `ORTTS_ASR_SILENCE`），识别 `"请把蓝色文件夹送到三楼会议室。"`，`peak_buf=67200`；
  - Sherpa 真流式 `zipformer_bilingual`：`events=9`，识别 `"请把蓝色文件夹送到三楼会议室"`。
