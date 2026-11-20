# OrTTS Rust SDK

无外部 crate 依赖的语音合成绑定，支持离线／流式 PCM、加载取消和推理取消。
先[构建并链接原生库](../README.md#rust)，再在固定 worker 上创建、使用 `Engine`。

## 任务级取消

**每次加载或合成都创建新的 `Task`**，将 `cancel_handle()` 交给控制线程；
控制线程调用 `cancel()` 即可请求停止，不需要接触 engine。

```rust
use ortts_engine::{cancellation::Task, Engine, Error};

fn run(model_root: &str, manifest_sha: &str) -> Result<(), Error> {
    let mut loading = Task::new()?;
    // 需要取消加载时，提前将 loading.cancel_handle() 交给控制线程。
    let mut engine = Engine::new_cancellable(
        model_root, "P3", None, manifest_sha, 4, false, &mut loading,
    )?;

    let mut task = Task::new()?;
    // 将 task.cancel_handle() 交给控制线程，调用 cancel() 可取消本次合成。
    match engine.synthesize_cancellable("你好。", 42, 513, &mut task) {
        Ok(audio) => println!("生成 {} 个采样点", audio.pcm.len()),
        Err(Error::Cancelled) => { /* 模型仍然驻留；创建新 Task 即可再次合成 */ }
        Err(error) => return Err(error),
    }
    Ok(())
}
```

- `CancelHandle` 可跨线程共享；`Engine` 不可跨线程传递或共享。
- 任务完成后旧句柄返回 `Inactive`，不会取消下一轮；复用 `Task` 返回 `TaskConsumed`。
- `stream_cancellable` 提供流式输出，回调返回 `false` 可停止，panic 转为 `CallbackPanicked`。
- 用 `cancellation::capabilities()`（Own-model）与 `speech::cancellation_capabilities()`（Speech 域）分别查询加载和推理取消能力：协作取消、阶段边界取消，
  或旧库的“原生调用返回后丢弃结果”。取消不保证立即打断任意计算或 I/O。

## Speech 并发、策略与流式 ASR

- **Speech `Task` 取消与防误卸**：`speech::Tts` 与 `speech::Asr` 提供 `new_cancellable`、`synthesize_cancellable` / `stream_cancellable`、`run_cancellable` / `finish_cancellable`；`speech::cache::TtsCache` 的 `synthesize_cancellable` / `stream_cancellable` 在协作 `Error::Cancelled` 或 `err.is_busy()` 时保留常驻权重不卸载，仅在 sink 返回 `false`、panic 或后端失败时清理。
- **并发能力探测**：`speech::parallel_inference_version()`（或根导出 `ortts_engine::parallel_inference_version()`）符号缺失时返回 `0`，支持 per-handle 并发时返回 `2`；可用 `speech::supports_parallel_tts_asr()` 判断同进程是否至少支持 1 路 TTS + 1 路 ASR 并发。
- **有界等待 / 抢占策略**：`ExecPolicy { timeout_ms, supersede }` 与 `Engine` / `speech::Tts` / `speech::Asr` / `TtsCache` 的 `*_ex` 接口映射到 C `ortts_exec_policy`（不支持的旧库在非默认策略时返回 `Error::UnsupportedAbi`）；`Error::is_busy()` 精确匹配 `STATUS_BUSY`（状态码 `3`）。
- **流式 ASR 适配**：`Config::new_streaming_asr(family, model_path, threads)` 自动置空离线字段；`speech::streaming::families()` 从 `speech::catalog()` 解析启用的流式家族（如 `moonshine_asr`、`streaming_paraformer`、`zipformer_bilingual`）；`Stats::*_opt()` 将 `u64::MAX` 与非有限耗时安全转换为 `None`。

原有 `new` / `synthesize` / `stream` 仍返回 `Result<_, String>`；任务级接口返回结构化 `Error`。
Android `--cpu-auto` 与协作取消现已支持同开（准备顺序：`prepare_cancellable_runtime.py` → `prepare_explicit_options.py` → `prepare_cpu_dispatch.py`）。

源码准备、验收、产物校验及安全设计见 [AGENT_README](AGENT_README.md)。
