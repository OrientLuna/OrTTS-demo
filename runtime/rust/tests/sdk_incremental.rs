//! Integration tests for incremental OrTTS SDK features:
//! - engine_feature_version() & runtime_capabilities()
//! - Per-request speaker hot-switching (file path + in-memory vector + set_speaker*)
//! - Speed parameter validation & legacy ignoring on own model
//! - Segmented bilingual streaming ASR discovery
use ortts_engine::{
    engine_feature_version, speech, Engine, Error, ExecPolicy, SynthesizeOptions,
};
use std::path::Path;

#[test]
fn runtime_reports_incremental_capabilities() {
    assert_eq!(
        engine_feature_version(),
        2,
        "Expected ORTTS_AUDIOCPP_PER_REQUEST_SPEAKER=1 (v1.2)"
    );
    let caps = speech::runtime_capabilities();
    assert_eq!(caps.abi_version, 1);
    assert_eq!(caps.engine_feature_version, 2);
    let own = caps
        .tts
        .iter()
        .find(|t| t.family == "ortts_qwen3_lfm")
        .expect("ortts_qwen3_lfm entry present");
    assert!(own.per_request_speaker);
    assert!(!own.speed_control);
    let sense = caps
        .asr
        .iter()
        .find(|a| a.family == "sense_asr")
        .expect("sense_asr entry present");
    assert!(sense.streaming);
    assert!(!sense.true_streaming);
    assert_eq!(sense.streaming_kind, "segmented-energy");
    let stream_fams = speech::streaming_asr_families();
    assert!(stream_fams.iter().any(|f| f == "sense_asr"));
    assert!(stream_fams.iter().any(|f| f == "moonshine_asr"));
}

#[test]
fn real_own_model_hot_speaker_switch_and_speed() {
    let Some(root_os) = std::env::var_os("ORTTS_TEST_OWN_MODEL") else {
        return;
    };
    let root = Path::new(&root_os);
    let manifest_sha = std::env::var("ORTTS_TEST_OWN_MANIFEST_SHA")
        .unwrap_or_else(|_| "78954b071cabd84e126a9a5e27ad5903cd10e574ae0509da5d7254e5023e2fd4".into());
    let root_str = root.to_str().unwrap();
    let male_path = root.join("voices/male.f32");
    let female_path = root.join("voices/female.f32");
    let male_bytes = std::fs::read(&male_path).unwrap();
    let female_bytes = std::fs::read(&female_path).unwrap();
    let to_f32 = |bytes: &[u8]| -> Vec<f32> {
        bytes
            .chunks_exact(4)
            .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
            .collect()
    };
    let male_vec = to_f32(&male_bytes);
    let female_vec = to_f32(&female_bytes);

    let mut engine = Engine::new(root_str, "P3", None, &manifest_sha, 4, true).unwrap();
    let policy = ExecPolicy::default();

    // 1. Default female speaker
    let a_female = engine
        .synthesize_with_options(
            "你好。",
            42,
            128,
            &SynthesizeOptions::new(),
            &policy,
            None,
        )
        .unwrap();
    assert!(!a_female.pcm.is_empty());

    // 2. Per-request male path hot switch on the SAME engine instance
    let a_male_path = engine
        .synthesize_with_options(
            "你好。",
            42,
            128,
            &SynthesizeOptions::new().with_speaker_path(male_path.to_str().unwrap()),
            &policy,
            None,
        )
        .unwrap();
    assert_ne!(
        a_female.pcm, a_male_path.pcm,
        "Per-request male.f32 must produce different PCM than default female.f32"
    );

    // 3. Per-request in-memory male vector hot switch must match file-path output bit-for-bit
    let a_male_vec = engine
        .synthesize_with_options(
            "你好。",
            42,
            128,
            &SynthesizeOptions::new().with_speaker_vector(&male_vec),
            &policy,
            None,
        )
        .unwrap();
    assert_eq!(
        a_male_vec.pcm, a_male_path.pcm,
        "In-memory speaker_vector must match .f32 path synthesis identically"
    );

    // 4. Per-request override did not mutate engine default
    let a_default_again = engine.synthesize("你好。", 42, 128).unwrap();
    assert_eq!(a_default_again.pcm, a_female.pcm);

    // 5. Engine-level set_speaker / set_speaker_vector + valid speed safely ignored + invalid speed rejected
    engine.set_speaker(Some(male_path.to_str().unwrap())).unwrap();
    let a_set_male = engine
        .synthesize_with_options(
            "你好。",
            42,
            128,
            &SynthesizeOptions::new().with_speed(1.25),
            &policy,
            None,
        )
        .unwrap();
    assert_eq!(a_set_male.pcm, a_male_path.pcm);

    assert!(matches!(
        engine.synthesize_with_options(
            "你好。",
            42,
            128,
            &SynthesizeOptions::new().with_speed(3.0),
            &policy,
            None,
        ),
        Err(Error::InvalidInput(_))
    ));

    engine.set_speaker_vector(&female_vec).unwrap();
    let a_set_female = engine.synthesize("你好。", 42, 128).unwrap();
    assert_eq!(a_set_female.pcm, a_female.pcm);
}
