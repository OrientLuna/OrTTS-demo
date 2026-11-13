//! Real-model acceptance. Shared with the isolated iOS probe; no downloads/UI changes.
use ortts_engine::{
    cancellation::{capabilities, CancelMode, CancelOutcome, Task},
    Engine, Error,
};
use std::{
    fmt::Write,
    time::{Duration, Instant},
};

pub fn acceptance(root: &str, manifest: &str) -> Result<String, String> {
    let mut receipt = String::new();
    let mut samples = Vec::new();
    let caps = capabilities();
    let mut load = Task::new().map_err(|e| e.to_string())?;
    let stale_load = load.cancel_handle();
    let thread_handle = stale_load.clone();
    let thread = std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(10));
        let at = Instant::now();
        (thread_handle.cancel(), at)
    });
    let cancelled = Engine::new_cancellable(root, "P3", None, manifest, 4, false, &mut load);
    let (outcome, at) = thread.join().map_err(|_| "cancel thread panicked")?;
    if outcome != CancelOutcome::Requested || !matches!(cancelled, Err(Error::Cancelled)) {
        return Err("loading did not return structured Cancelled".into());
    }
    let load_cancel_ms = at.elapsed().as_secs_f64() * 1000.0;
    if stale_load.cancel() != CancelOutcome::Inactive {
        return Err("load handle still active".into());
    }
    for streaming in [false, true] {
        let mut task = Task::new().map_err(|e| e.to_string())?;
        let mut engine =
            Engine::new_cancellable(root, "P3", None, manifest, 4, streaming, &mut task)
                .map_err(|e| e.to_string())?;
        let short = "你好，欢迎使用本地语音合成。";
        let long =
            "今天我们测试本地语音合成的安全取消。取消后模型保持驻留，可以继续合成下一段文字。"
                .repeat(3);
        let baseline = engine.synthesize(short, 42, 513)?;
        for delay in [5, 30, 150] {
            let mut task = Task::new().map_err(|e| e.to_string())?;
            let old = task.cancel_handle();
            let current = old.clone();
            let thread = std::thread::spawn(move || {
                std::thread::sleep(Duration::from_millis(delay));
                let at = Instant::now();
                (current.cancel(), at)
            });
            let result = engine.synthesize_cancellable(&long, 42, 513, &mut task);
            let (outcome, at) = thread.join().map_err(|_| "cancel thread panicked")?;
            let latency = at.elapsed().as_secs_f64() * 1000.0;
            if outcome != CancelOutcome::Requested || !matches!(result, Err(Error::Cancelled)) {
                return Err("synthesis cancellation failed".into());
            }
            let mut next = Task::new().map_err(|e| e.to_string())?;
            let stale_thread = std::thread::spawn(move || {
                // Request during the NEXT generation, including after engine drop.
                for _ in 0..50 {
                    if old.cancel() != CancelOutcome::Inactive {
                        return false;
                    }
                    std::thread::sleep(Duration::from_millis(2));
                }
                true
            });
            let recovery = engine
                .synthesize_cancellable(short, 42, 513, &mut next)
                .map_err(|e| e.to_string())?;
            if !stale_thread.join().map_err(|_| "stale thread panicked")?
                || recovery.pcm != baseline.pcm
            {
                return Err(
                    "stale cancellation affected next generation or request state leaked".into(),
                );
            }
            samples.push(format!("{{\"streaming\":{streaming},\"delay_ms\":{delay},\"cancel_latency_ms\":{latency:.3},\"recovery_pcm_equal\":true}}"));
        }
        let mut task = Task::new().map_err(|e| e.to_string())?;
        let dropped_engine_handle = task.cancel_handle();
        let result = engine
            .synthesize_cancellable(short, 42, 513, &mut task)
            .map_err(|e| e.to_string())?;
        if result.pcm != baseline.pcm {
            return Err("last recovery failed".into());
        }
        if streaming {
            let (entered_tx, entered_rx) = std::sync::mpsc::channel();
            let (release_tx, release_rx) = std::sync::mpsc::channel();
            let root = root.to_owned();
            let manifest = manifest.to_owned();
            let competitor = std::thread::spawn(move || {
                entered_rx.recv_timeout(Duration::from_secs(30)).unwrap();
                let mut task = Task::new().unwrap();
                let result =
                    Engine::new_cancellable(&root, "P3", None, &manifest, 4, false, &mut task);
                let busy = matches!(result, Err(Error::Native { status: 3, .. }));
                release_tx.send(busy).unwrap();
                busy
            });
            let mut task = Task::new().map_err(|e| e.to_string())?;
            let mut gate_ok = false;
            let result = engine.stream_cancellable(
                short,
                42,
                513,
                |_, _| {
                    entered_tx.send(()).unwrap();
                    gate_ok = release_rx.recv_timeout(Duration::from_secs(30)).unwrap();
                    false
                },
                &mut task,
            );
            if !matches!(result, Err(Error::Cancelled)) || !gate_ok || !competitor.join().unwrap() {
                return Err("native execution gate no longer rejects competing load".into());
            }
            let mut task = Task::new().map_err(|e| e.to_string())?;
            if !matches!(
                engine.stream_cancellable(short, 42, 513, |_, _| false, &mut task),
                Err(Error::Cancelled)
            ) {
                return Err("callback cancellation is not structured".into());
            }
            let mut task = Task::new().map_err(|e| e.to_string())?;
            if !matches!(
                engine.stream_cancellable(
                    short,
                    42,
                    513,
                    |_, _| panic!("acceptance callback panic"),
                    &mut task
                ),
                Err(Error::CallbackPanicked)
            ) {
                return Err("callback panic escaped boundary".into());
            }
            if engine.synthesize(short, 42, 513)?.pcm != baseline.pcm {
                return Err("callback panic recovery failed".into());
            }
        }
        let barrier = std::sync::Arc::new(std::sync::Barrier::new(2));
        let other_barrier = barrier.clone();
        let during_drop = std::thread::spawn(move || {
            other_barrier.wait();
            for _ in 0..100 {
                if dropped_engine_handle.cancel() != CancelOutcome::Inactive {
                    return false;
                }
                std::thread::sleep(Duration::from_millis(1));
            }
            true
        });
        barrier.wait();
        drop(engine);
        if !during_drop.join().unwrap() {
            return Err("handle remained active after engine drop".into());
        }
    }
    write!(&mut receipt, "{{\"status\":\"passed\",\"loading_mode\":\"{:?}\",\"synthesis_mode\":\"{:?}\",\"load_cancel_latency_ms\":{load_cancel_ms:.3},\"samples\":[{}],\"stale_handle_is_inert\":true,\"drop_safe\":true,\"execution_gate_busy\":true,\"callback_cancel_and_panic_recovery\":true,\"cooperative\":{}}}", caps.loading, caps.synthesis, samples.join(","), caps.synthesis == CancelMode::Cooperative).unwrap();
    Ok(receipt)
}

#[allow(dead_code)]
fn main() {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 4 {
        eprintln!("usage: cancellation MODEL BRIDGE_SHA REPORT.json");
        std::process::exit(2);
    }
    let result = acceptance(&args[1], &args[2]);
    match result {
        Ok(report) => {
            std::fs::write(&args[3], &report).unwrap();
            println!("{report}");
        }
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}
