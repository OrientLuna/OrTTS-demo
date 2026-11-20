//! One worker-owned TTS engine. Call `evict_expired` from a host idle timer;
//! no background thread is created and this cache is neither Send nor Sync.
use super::{speech_api, Audio, Config, ExecPolicy, Request, SpeechApi, Tts};
use crate::{
    cancellation::{CancelMode, Operation, Task},
    Error,
};
use std::time::{Duration, Instant};

#[derive(PartialEq, Eq)]
struct Key {
    asset_identity: String,
    family: String,
    path: String,
    threads: i32,
    streaming: bool,
    options: Vec<(String, String)>,
    library: Option<String>,
    data: Option<String>,
    input_limit: usize,
}
impl Key {
    fn new(config: &Config<'_>, identity: &str) -> Self {
        Self {
            asset_identity: identity.into(),
            family: config.family.into(),
            path: config.model_path.into(),
            threads: config.threads,
            streaming: config.streaming,
            options: config
                .session_options
                .iter()
                .map(|(k, v)| (k.to_string(), v.to_string()))
                .collect(),
            library: config.espeak_library.map(str::to_owned),
            data: config.espeak_data.map(str::to_owned),
            input_limit: config.max_input_frames,
        }
    }
}
struct Entry {
    key: Key,
    engine: Tts,
    last_used: Instant,
}
struct PolicyAndTask<'a> {
    policy: &'a ExecPolicy,
    task: Option<&'a mut Task>,
}

/// Bounded to one model. Voices are request fields, not separate cached engines.
/// Identity must describe verified assets (including external voices), not just a
/// filename. This helper does not download, hash, or authorize model packages.
pub struct TtsCache {
    entry: Option<Entry>,
    idle_ttl: Duration,
    api: SpeechApi,
}
impl TtsCache {
    pub fn new(idle_ttl: Duration) -> Self {
        Self {
            entry: None,
            idle_ttl,
            api: speech_api(),
        }
    }
    #[cfg(test)]
    pub(crate) fn with_api(idle_ttl: Duration, api: SpeechApi) -> Self {
        Self {
            entry: None,
            idle_ttl,
            api,
        }
    }
    pub fn is_loaded(&self) -> bool {
        self.entry.is_some()
    }
    pub fn clear(&mut self) {
        self.entry = None;
    }
    /// Invoke on the owning worker, including from the host's idle timer.
    pub fn evict_expired(&mut self) -> bool {
        if self
            .entry
            .as_ref()
            .is_some_and(|e| e.last_used.elapsed() >= self.idle_ttl)
        {
            self.clear();
            true
        } else {
            false
        }
    }
    fn execute<F: FnMut(&[f32], i32, i32) -> bool>(
        &mut self,
        config: &Config<'_>,
        identity: &str,
        request: &Request<'_>,
        sink: Option<F>,
        exec: PolicyAndTask<'_>,
    ) -> Result<(Audio, bool), Error> {
        let op = exec.task.map(Task::begin).transpose()?;
        if identity.is_empty() {
            return Err(Error::InvalidInput(
                "Verified asset identity is required".into(),
            ));
        }
        if op.as_ref().is_some_and(Operation::requested) {
            return Err(Error::Cancelled);
        }
        self.evict_expired();
        let key = Key::new(config, identity);
        let reused = self.entry.as_ref().is_some_and(|e| e.key == key);
        if !reused {
            // Drop before loading: never hold old and new model weights together.
            self.clear();
            self.entry = Some(Entry {
                key,
                engine: Tts::open_with_op(self.api, config, op.as_ref())?,
                last_used: Instant::now(),
            });
        }
        let entry = self.entry.as_mut().expect("created above");
        let result = match sink {
            Some(callback) => entry.engine.run_with_sink(request, callback, exec.policy, op),
            None => entry.engine.run_no_sink(request, exec.policy, op),
        };
        entry.last_used = Instant::now();
        match result {
            Ok(audio) => Ok((audio, reused)),
            Err(failure) => {
                let cooperative_synth =
                    self.api.capabilities().synthesis == CancelMode::Cooperative;
                // Keep resident weights on cooperative Task cancellation or transient ORTTS_BUSY,
                // while evicting when the sink callback actively aborted, panicked, or errored.
                let preserve = !failure.entered_ffi
                    || failure.error.is_busy()
                    || (matches!(failure.error, Error::Cancelled)
                        && !failure.stopped_by_sink
                        && cooperative_synth);
                if !preserve {
                    self.clear();
                }
                Err(failure.error)
            }
        }
    }
    pub fn synthesize(
        &mut self,
        config: &Config<'_>,
        identity: &str,
        request: &Request<'_>,
    ) -> Result<(Audio, bool), String> {
        let policy = ExecPolicy::default();
        self.execute::<fn(&[f32], i32, i32) -> bool>(
            config,
            identity,
            request,
            None,
            PolicyAndTask {
                policy: &policy,
                task: None,
            },
        )
        .map_err(|e| e.to_string())
    }
    /// Synthesize with a single-use cancellation task, keeping resident weights on cooperative cancellation or Busy.
    pub fn synthesize_cancellable(
        &mut self,
        config: &Config<'_>,
        identity: &str,
        request: &Request<'_>,
        task: &mut Task,
    ) -> Result<(Audio, bool), Error> {
        let policy = ExecPolicy::default();
        self.execute::<fn(&[f32], i32, i32) -> bool>(
            config,
            identity,
            request,
            None,
            PolicyAndTask {
                policy: &policy,
                task: Some(task),
            },
        )
    }
    /// Synthesize with an execution lock policy and optional cancellation task.
    pub fn synthesize_ex(
        &mut self,
        config: &Config<'_>,
        identity: &str,
        request: &Request<'_>,
        policy: &ExecPolicy,
        task: Option<&mut Task>,
    ) -> Result<(Audio, bool), Error> {
        self.execute::<fn(&[f32], i32, i32) -> bool>(
            config,
            identity,
            request,
            None,
            PolicyAndTask { policy, task },
        )
    }
    pub fn stream<F: FnMut(&[f32], i32, i32) -> bool>(
        &mut self,
        config: &Config<'_>,
        identity: &str,
        request: &Request<'_>,
        sink: F,
    ) -> Result<(Audio, bool), String> {
        let policy = ExecPolicy::default();
        self.execute(
            config,
            identity,
            request,
            Some(sink),
            PolicyAndTask {
                policy: &policy,
                task: None,
            },
        )
        .map_err(|e| e.to_string())
    }
    /// Stream synthesized audio with a single-use cancellation task, keeping resident weights on cooperative cancellation or Busy.
    pub fn stream_cancellable<F: FnMut(&[f32], i32, i32) -> bool>(
        &mut self,
        config: &Config<'_>,
        identity: &str,
        request: &Request<'_>,
        sink: F,
        task: &mut Task,
    ) -> Result<(Audio, bool), Error> {
        let policy = ExecPolicy::default();
        self.execute(
            config,
            identity,
            request,
            Some(sink),
            PolicyAndTask {
                policy: &policy,
                task: Some(task),
            },
        )
    }
    /// Stream synthesized audio with an execution lock policy and optional cancellation task.
    pub fn stream_ex<F: FnMut(&[f32], i32, i32) -> bool>(
        &mut self,
        config: &Config<'_>,
        identity: &str,
        request: &Request<'_>,
        sink: F,
        policy: &ExecPolicy,
        task: Option<&mut Task>,
    ) -> Result<(Audio, bool), Error> {
        self.execute(config, identity, request, Some(sink), PolicyAndTask { policy, task })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cancellation::CancelOutcome;
    use crate::speech::test_support::{install_thread_state, mock_speech_api, MockState};
    use std::sync::atomic::Ordering;

    #[test]
    fn preserves_resident_model_on_cooperative_cancel_and_busy() {
        let api = mock_speech_api(true, true);
        let cancel_api = api.cancel_api;
        let state = MockState::default();
        install_thread_state(state.clone());

        let mut cache = TtsCache::with_api(Duration::from_secs(30), api);
        let cfg = Config::new("pocket_tts", "ok");

        // 1. Cold load + synthesis shares one Task cleanly without TaskConsumed.
        let mut load_and_synth = Task::with_api(cancel_api).unwrap();
        let handle0 = load_and_synth.cancel_handle();
        let (audio, reused) = cache
            .synthesize_cancellable(&cfg, "pack-v1", &Request::new("ok"), &mut load_and_synth)
            .unwrap();
        assert!(!reused);
        assert_eq!(audio.pcm, vec![0.1, 0.2]);
        assert!(cache.is_loaded());
        assert_eq!(handle0.cancel(), CancelOutcome::Inactive);
        assert_eq!(state.creates.load(Ordering::SeqCst), 1);

        // 2. Cooperative cancellation via CancelHandle preserves resident model.
        let mut cancel_task = Task::with_api(cancel_api).unwrap();
        let handle1 = cancel_task.cancel_handle();
        *state.active_cancel.lock().unwrap() = Some(handle1.clone());
        let err = cache
            .synthesize_cancellable(&cfg, "pack-v1", &Request::new("cancel_op"), &mut cancel_task)
            .err()
            .unwrap();
        assert_eq!(err, Error::Cancelled);
        assert!(cache.is_loaded(), "cooperative cancel must not evict model");
        assert_eq!(state.frees.load(Ordering::SeqCst), 0);
        assert_eq!(handle1.cancel(), CancelOutcome::Inactive);

        // 3. Transient ORTTS_BUSY preserves resident model too (and is_busy() matches).
        let err = cache
            .synthesize_ex(
                &cfg,
                "pack-v1",
                &Request::new("busy"),
                &ExecPolicy::new(50, false),
                None,
            )
            .err()
            .unwrap();
        assert!(err.is_busy());
        assert!(cache.is_loaded(), "BUSY must not evict model");
        assert_eq!(state.frees.load(Ordering::SeqCst), 0);

        // 4. Subsequent request reuses the already loaded engine (reused == true, creates == 1).
        let mut next = Task::with_api(cancel_api).unwrap();
        let (_, reused) = cache
            .synthesize_cancellable(&cfg, "pack-v1", &Request::new("ok"), &mut next)
            .unwrap();
        assert!(reused);
        assert_eq!(state.creates.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn evicts_on_sink_returning_false_or_panic_or_runtime_error() {
        let api = mock_speech_api(true, true);
        let cancel_api = api.cancel_api;
        let cfg = Config::new("pocket_tts", "ok");

        // Warm load
        let s1 = MockState::default();
        install_thread_state(s1.clone());
        let mut cache = TtsCache::with_api(Duration::from_secs(30), api);
        cache.synthesize(&cfg, "pack-v1", &Request::new("ok")).unwrap();
        assert!(cache.is_loaded());

        // Even when native C returns status == 4 (ORTTS_CANCELLED), sink returning false must evict!
        let mut t_sink = Task::with_api(cancel_api).unwrap();
        let res = cache.stream_cancellable(
            &cfg,
            "pack-v1",
            &Request::new("stream_sink_stop_returns_4"),
            |_, _, _| false,
            &mut t_sink,
        );
        assert!(matches!(res, Err(Error::Cancelled)));
        assert!(!cache.is_loaded(), "sink=false must clear cache");
        assert_eq!(s1.frees.load(Ordering::SeqCst), 1);

        // Reload and test callback panic eviction
        let s2 = MockState::default();
        install_thread_state(s2.clone());
        let (_, reused) = cache.synthesize(&cfg, "pack-v1", &Request::new("ok")).unwrap();
        assert!(!reused);
        let res = cache.stream_ex(
            &cfg,
            "pack-v1",
            &Request::new("stream_chunks"),
            |_, _, _| -> bool { panic!("downstream audio queue closed") },
            &ExecPolicy::default(),
            None,
        );
        assert!(matches!(res, Err(Error::CallbackPanicked)));
        assert!(!cache.is_loaded(), "callback panic must clear cache");
        assert_eq!(s2.frees.load(Ordering::SeqCst), 1);

        // Reload, invalid input before FFI preserves; backend runtime error evicts.
        let s3 = MockState::default();
        install_thread_state(s3.clone());
        cache.synthesize(&cfg, "pack-v1", &Request::new("ok")).unwrap();
        let bad_req = Request::new("bad\0text");
        assert!(matches!(
            cache.synthesize_ex(&cfg, "pack-v1", &bad_req, &ExecPolicy::default(), None),
            Err(Error::InvalidInput(_))
        ));
        assert!(cache.is_loaded());
        assert_eq!(s3.frees.load(Ordering::SeqCst), 0);

        let err = cache
            .synthesize_ex(
                &cfg,
                "pack-v1",
                &Request::new("runtime_error"),
                &ExecPolicy::default(),
                None,
            )
            .err()
            .unwrap();
        assert!(!err.is_busy());
        assert!(!cache.is_loaded());
        assert_eq!(s3.frees.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn non_cooperative_runtime_still_evicts_on_in_flight_cancel() {
        let boundary_api = mock_speech_api(false, true);
        let cancel_api = boundary_api.cancel_api;
        let state = MockState::default();
        install_thread_state(state.clone());

        let mut cache = TtsCache::with_api(Duration::from_secs(30), boundary_api);
        let cfg = Config::new("pocket_tts", "ok");
        cache.synthesize(&cfg, "pack-v1", &Request::new("ok")).unwrap();
        assert!(cache.is_loaded());

        // Pre-cancel (FFI not entered) preserves loaded weights even on non-cooperative runtime
        let mut precancel = Task::with_api(cancel_api).unwrap();
        precancel.cancel_handle().cancel();
        assert!(matches!(
            cache.synthesize_cancellable(&cfg, "pack-v1", &Request::new("ok"), &mut precancel),
            Err(Error::Cancelled)
        ));
        assert!(cache.is_loaded());
        assert_eq!(state.frees.load(Ordering::SeqCst), 0);

        // In-flight cancel on non-cooperative runtime must evict dirty handle
        let mut in_flight = Task::with_api(cancel_api).unwrap();
        *state.active_cancel.lock().unwrap() = Some(in_flight.cancel_handle());
        assert!(matches!(
            cache.synthesize_cancellable(&cfg, "pack-v1", &Request::new("cancel_op"), &mut in_flight),
            Err(Error::Cancelled)
        ));
        assert!(!cache.is_loaded());
        assert_eq!(state.frees.load(Ordering::SeqCst), 1);
    }
}
