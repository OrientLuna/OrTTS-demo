use ortts_engine::speech::{cache::TtsCache, Config, Request};
use std::time::Duration;
fn main() -> Result<(), String> {
    let root = std::env::args()
        .nth(1)
        .ok_or("existing asset root required")?;
    let model = format!("{root}/PocketTTS-GGUF/english/pocket-tts-english-q8_0.gguf");
    let mut config = Config::new("pocket_tts", &model);
    config.streaming = true;
    let mut request = Request::new("Hello, welcome to local speech synthesis.");
    request.voice = Some("alba");
    request.language = Some("en");
    request.seed = Some(42);
    let mut cache = TtsCache::new(Duration::from_secs(30));
    let (first, reused) = cache.synthesize(&config, "verified-test-pack-v1", &request)?;
    assert!(!reused && !first.pcm.is_empty());
    let (second, reused) = cache.synthesize(&config, "verified-test-pack-v1", &request)?;
    assert!(reused && !second.pcm.is_empty());
    assert_eq!(
        first.pcm, second.pcm,
        "same seed/text must survive engine reuse"
    );
    request.voice = Some("anna");
    let (_, reused) = cache.synthesize(&config, "verified-test-pack-v1", &request)?;
    assert!(reused);
    config.threads = 1;
    let (_, reused) = cache.synthesize(&config, "verified-test-pack-v1", &request)?;
    assert!(!reused);
    let (_, reused) = cache.synthesize(&config, "verified-test-pack-v2", &request)?;
    assert!(!reused);
    assert!(cache
        .stream(&config, "verified-test-pack-v2", &request, |_, _, _| false)
        .is_err());
    assert!(!cache.is_loaded());
    let (_, reused) = cache.synthesize(&config, "verified-test-pack-v2", &request)?;
    assert!(!reused);
    cache.clear();
    assert!(!cache.is_loaded());
    let mut expired = TtsCache::new(Duration::ZERO);
    expired.synthesize(&config, "verified-test-pack-v1", &request)?;
    assert!(expired.evict_expired() && !expired.is_loaded());
    println!(
        "PASS: warm reuse, voice/config/identity changes, cancellation, explicit/idle eviction"
    );
    Ok(())
}
