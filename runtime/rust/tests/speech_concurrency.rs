//! Integration tests for speech cancellation, parallel capability, ExecPolicy, and streaming helpers.
use ortts_engine::{
    cancellation::{CancelMode, CancelOutcome, Task},
    speech::{
        self,
        cache::TtsCache,
        streaming::{self, Settings, Stream},
        Asr, Config, ExecPolicy, Request, Tts,
    },
    Error,
};
use std::{
    path::Path,
    sync::mpsc,
    time::{Duration, Instant},
};

fn downsample_24k_to_16k(pcm24k: &[f32]) -> Vec<f32> {
    let mut out = Vec::with_capacity((pcm24k.len() * 2) / 3 + 1);
    let mut i = 0;
    while i + 2 < pcm24k.len() {
        out.push(pcm24k[i]);
        out.push(0.5 * (pcm24k[i + 1] + pcm24k[i + 2]));
        i += 3;
    }
    out
}

#[test]
fn speech_capabilities_and_catalog_match_runtime() {
    let caps = speech::cancellation_capabilities();
    let parallel = speech::parallel_inference_version();
    let families = speech::streaming::families();
    assert_eq!(families, speech::streaming_asr_families());

    if let Ok(expected) = std::env::var("ORTTS_EXPECT_CANCEL_MODE") {
        match expected.as_str() {
            "cooperative" => {
                assert_eq!(caps.loading, CancelMode::Cooperative);
                assert_eq!(caps.synthesis, CancelMode::Cooperative);
                if speech::available() {
                    assert_eq!(parallel, 2);
                    assert!(speech::supports_parallel_tts_asr());
                    assert!(families.iter().any(|f| f == "moonshine_asr"));
                }
            }
            "v1" => {
                assert_eq!(caps.loading, CancelMode::Cooperative);
                assert_eq!(caps.synthesis, CancelMode::DiscardAfterReturn);
            }
            "legacy" => {
                assert_eq!(caps.loading, CancelMode::DiscardAfterReturn);
                assert_eq!(caps.synthesis, CancelMode::DiscardAfterReturn);
            }
            _ => panic!("unknown ORTTS_EXPECT_CANCEL_MODE: {expected}"),
        }
    }

    eprintln!(
        "Speech caps={caps:?}, parallel_version={parallel}, streaming_families={families:?}"
    );
}

#[test]
fn speech_precancel_on_two_workers_without_models() {
    let barrier = std::sync::Arc::new(std::sync::Barrier::new(2));
    let b1 = barrier.clone();

    let tts_worker = std::thread::spawn(move || {
        let mut task = Task::new().unwrap();
        let handle = task.cancel_handle();
        assert_eq!(handle.cancel(), CancelOutcome::Requested);
        b1.wait();
        let res = Tts::new_cancellable(&Config::new("pocket_tts", "/does/not/exist"), &mut task);
        assert!(matches!(res, Err(Error::Cancelled)));
        assert_eq!(handle.cancel(), CancelOutcome::Inactive);
        assert!(matches!(
            Tts::new_cancellable(&Config::new("pocket_tts", "/unused"), &mut task),
            Err(Error::TaskConsumed)
        ));
    });

    let asr_worker = std::thread::spawn(move || {
        let mut task = Task::new().unwrap();
        let handle = task.cancel_handle();
        assert_eq!(handle.cancel(), CancelOutcome::Requested);
        barrier.wait();
        let res = Asr::new_cancellable(&Config::new("sense_asr", "/does/not/exist"), &mut task);
        assert!(matches!(res, Err(Error::Cancelled)));
        assert_eq!(handle.cancel(), CancelOutcome::Inactive);
        assert!(matches!(
            Asr::new_cancellable(&Config::new("sense_asr", "/unused"), &mut task),
            Err(Error::TaskConsumed)
        ));
    });

    tts_worker.join().unwrap();
    asr_worker.join().unwrap();
}

#[test]
fn real_parallel_tts_and_asr_with_cache_residency_and_streaming() {
    let require_models = std::env::var("ORTTS_REQUIRE_SPEECH_MODELS").ok().as_deref() == Some("1");
    let Some(models_root) = std::env::var_os("ORTTS_TEST_SPEECH_MODELS") else {
        if require_models {
            panic!("ORTTS_REQUIRE_SPEECH_MODELS=1 set, but ORTTS_TEST_SPEECH_MODELS is unset");
        }
        return;
    };

    assert!(speech::available(), "Speech ABI must be enabled");
    assert!(
        speech::supports_parallel_tts_asr(),
        "Expected parallel_inference_version >= 2, got {}",
        speech::parallel_inference_version()
    );

    let root = Path::new(&models_root);
    let pocket_path = root.join("PocketTTS-GGUF/english/pocket-tts-english-q8_0.gguf");
    let sense_path = root.join("sensevoice-small-q8-audiocpp-v1.gguf");
    assert!(pocket_path.is_file(), "Missing {}", pocket_path.display());
    assert!(sense_path.is_file(), "Missing {}", sense_path.display());

    let pocket_str = pocket_path.to_str().unwrap().to_owned();
    let sense_str = sense_path.to_str().unwrap().to_owned();

    // Prepare 16kHz test audio using PocketTTS so no separate audio fixture path is needed.
    let mut seed_cfg = Config::new("pocket_tts", &pocket_str);
    seed_cfg.streaming = false;
    seed_cfg.threads = 2;
    let mut seed_task = Task::new().unwrap();
    let mut seed_tts = Tts::new_cancellable(&seed_cfg, &mut seed_task).unwrap();
    let mut seed_req = Request::new("Hello, please test concurrent synthesis and recognition.");
    seed_req.voice = Some("alba");
    seed_req.language = Some("en");
    seed_req.seed = Some(42);
    let baseline = seed_tts
        .synthesize_ex(&seed_req, &ExecPolicy::new(2000, true), None)
        .unwrap();
    assert!(!baseline.pcm.is_empty());
    let pcm16k = downsample_24k_to_16k(&baseline.pcm);
    drop(seed_tts);

    // 1 Tts + 1 Asr concurrent overlap: TTS holds its stream lock while Asr runs full inference.
    let (tts_entered_tx, tts_entered_rx) = mpsc::channel();
    let (asr_done_tx, asr_done_rx) = mpsc::channel::<bool>();
    let pocket_for_worker = pocket_str.clone();
    let sense_for_worker = sense_str.clone();

    let tts_worker = std::thread::spawn(move || {
        let mut cfg = Config::new("pocket_tts", &pocket_for_worker);
        cfg.streaming = true;
        cfg.threads = 2;
        let mut tts = Tts::new(&cfg).unwrap();
        let mut req = Request::new(
            "Concurrent speech generation running while local recognition runs in parallel.",
        );
        req.voice = Some("alba");
        req.language = Some("en");
        req.seed = Some(7);
        let mut task = Task::new().unwrap();
        let mut signaled = false;
        let audio = tts
            .stream_cancellable(
                &req,
                |chunk, rate, ch| {
                    assert_eq!((rate, ch), (24_000, 1));
                    assert!(!chunk.is_empty());
                    if !signaled {
                        signaled = true;
                        tts_entered_tx.send(()).unwrap();
                        let ok = asr_done_rx.recv_timeout(Duration::from_secs(30)).unwrap();
                        assert!(ok, "concurrent ASR must succeed without Busy");
                    }
                    true
                },
                &mut task,
            )
            .unwrap();
        assert!(!audio.pcm.is_empty());
        assert!(signaled, "streaming TTS must invoke PCM callback");
    });

    let asr_worker = std::thread::spawn(move || {
        let mut cfg = Config::new("sense_asr", &sense_for_worker);
        cfg.threads = 2;
        let mut asr = Asr::new(&cfg).unwrap();
        tts_entered_rx.recv_timeout(Duration::from_secs(30)).unwrap();
        let mut task = Task::new().unwrap();
        let result = asr.run_cancellable(&pcm16k, Some("en"), &mut task);
        let ok = match &result {
            Ok(transcript) => {
                assert!(!transcript.text.trim().is_empty());
                true
            }
            Err(err) => {
                assert!(!err.is_busy(), "parallel ASR unexpectedly returned Busy: {err}");
                false
            }
        };
        asr_done_tx.send(ok).unwrap();
        result.unwrap();
    });

    tts_worker.join().unwrap();
    asr_worker.join().unwrap();

    // Verify real TtsCache cooperative cancel retains loaded model while sink=false clears it.
    let mut cache_cfg = Config::new("pocket_tts", &pocket_str);
    cache_cfg.streaming = true;
    cache_cfg.threads = 2;
    let mut cache = TtsCache::new(Duration::from_secs(30));

    let mut req = Request::new("First cached phrase for residency check.");
    req.voice = Some("alba");
    req.language = Some("en");
    req.seed = Some(11);
    let mut t_warm = Task::new().unwrap();
    let (_, reused) = cache
        .synthesize_cancellable(&cache_cfg, "pocket-en-q8-test", &req, &mut t_warm)
        .unwrap();
    assert!(!reused);
    assert!(cache.is_loaded());

    // Cooperative cancel via CancelHandle keeps TtsCache warm.
    let long_text = "This synthesis will be cancelled cooperatively while weights stay warm. ".repeat(3);
    let mut long_req = Request::new(&long_text);
    long_req.voice = Some("alba");
    long_req.language = Some("en");
    long_req.seed = Some(12);
    let mut t_cancel = Task::new().unwrap();
    let cancel_handle = t_cancel.cancel_handle();
    let trigger_thread = std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(15));
        let start = Instant::now();
        let outcome = cancel_handle.cancel();
        (outcome, start)
    });
    let res = cache.stream_cancellable(
        &cache_cfg,
        "pocket-en-q8-test",
        &long_req,
        |_, _, _| true,
        &mut t_cancel,
    );
    let (outcome, cancel_at) = trigger_thread.join().unwrap();
    assert_eq!(outcome, CancelOutcome::Requested);
    assert!(matches!(res.as_ref().err(), Some(Error::Cancelled)), "got {:?}", res.err());
    let elapsed_ms = cancel_at.elapsed().as_secs_f64() * 1000.0;
    assert!(
        cache.is_loaded(),
        "TtsCache evicted model on cooperative Error::Cancelled"
    );
    eprintln!("Real TtsCache cooperative cancel stopped in {elapsed_ms:.2} ms (model retained)");

    // Next call must reuse the cached handle without reloading weights.
    let mut t_recover = Task::new().unwrap();
    let (recovered, reused) = cache
        .synthesize_cancellable(&cache_cfg, "pocket-en-q8-test", &req, &mut t_recover)
        .unwrap();
    assert!(reused, "expected warm reuse after cooperative cancellation");
    assert!(!recovered.pcm.is_empty());

    // Sink returning false must still evict the cached handle cleanly.
    let mut t_sink = Task::new().unwrap();
    let sink_res = cache.stream_cancellable(
        &cache_cfg,
        "pocket-en-q8-test",
        &long_req,
        |_, _, _| false,
        &mut t_sink,
    );
    assert!(sink_res.is_err());
    assert!(
        !cache.is_loaded(),
        "TtsCache must clear when sink returns false"
    );

    // If Sherpa paraformer is enabled & present locally, verify Config::new_streaming_asr + Stats sentinels.
    let paraformer_dir = root.join("paraformer-streaming-zh-en-int8");
    if streaming::families().iter().any(|f| f == "streaming_paraformer")
        && paraformer_dir.is_dir()
    {
        let cfg = Config::new_streaming_asr(
            "streaming_paraformer",
            paraformer_dir.to_str().unwrap(),
            2,
        );
        let mut stream = Stream::new(&cfg, Settings::default()).unwrap();
        let _events = stream.accept(&vec![0.0_f32; 1600]).unwrap();
        let stats = stream.stats().unwrap();
        assert_eq!(stats.received_frames_opt(), Some(1600));
        assert_eq!(stats.buffered_pcm_frames_opt(), None);
        assert_eq!(stats.cached_encoder_frames_opt(), None);
        assert_eq!(stats.peak_buffered_pcm_frames_opt(), None);
        assert_eq!(stats.peak_cached_encoder_frames_opt(), None);
        assert_eq!(stats.encoder_ms_opt(), None);
        assert_eq!(stats.decoder_ms_opt(), None);
    }
}
