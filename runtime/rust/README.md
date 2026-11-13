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
- 用 `cancellation::capabilities()` 分别查询加载和推理能力：协作取消、阶段边界取消，
  或旧库的“原生调用返回后丢弃结果”。取消不保证立即打断任意计算或 I/O。

原有 `new` / `synthesize` / `stream` 仍返回 `Result<_, String>`；任务级接口返回结构化 `Error`。
Android CPU 自动分派暂不能与协作取消同时启用。

源码准备、验收、产物校验及安全设计见 [AGENT_README](AGENT_README.md)。
