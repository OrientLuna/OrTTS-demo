use ortts_engine::speech::{Asr, Config, Request, Tts};
fn main() -> Result<(), String> {
    let root = std::env::args().nth(1).ok_or("speech ASSET_ROOT")?;
    println!("{}", ortts_engine::speech::catalog());
    let path = format!("{root}/Piper-TTS-GGUF/piper-en-us-lessac-medium-orig.gguf");
    let mut cfg = Config::new("piper_tts", &path);
    // Keep owned environment strings alive during config creation.
    let library = std::env::var("AUDIOCPP_ESPEAK_LIBRARY").ok();
    let data = std::env::var("AUDIOCPP_ESPEAK_DATA").ok();
    cfg.espeak_library = library.as_deref();
    cfg.espeak_data = data.as_deref();
    let mut tts = Tts::new(&cfg)?;
    let mut req =
        Request::new("At nine thirty, please check the train ticket and call the station.");
    req.language = Some("en");
    req.seed = Some(42);
    let audio = tts.synthesize(&req)?;
    assert_eq!(audio.sample_rate, 22050);
    assert_eq!(audio.channels, 1);
    drop(tts);
    let pcm: Vec<f32> = (0..(audio.pcm.len() * 16000 / audio.sample_rate as usize))
        .map(|i| {
            let t = i as f64 * audio.sample_rate as f64 / 16000.;
            let j = t as usize;
            let k = (j + 1).min(audio.pcm.len() - 1);
            audio.pcm[j] * (1. - (t - j as f64) as f32) + audio.pcm[k] * (t - j as f64) as f32
        })
        .collect();
    let path = format!("{root}/sensevoice-small-q8-audiocpp-v1.gguf");
    let cfg = Config::new("sense_asr", &path);
    let mut asr = Asr::new(&cfg)?;
    let offline = asr.run(&pcm, Some("en"))?;
    for chunk in pcm.chunks(1000) {
        asr.accept(chunk)?;
    }
    let final_text = asr.finish(Some("en"))?;
    assert_eq!(offline.text, final_text.text);
    assert!(final_text.text.contains("station"));
    asr.reset()?;
    println!("ASR: {}", final_text.text);
    drop(asr);
    let path = format!("{root}/PocketTTS-GGUF/english/pocket-tts-english-q8_0.gguf");
    let mut cfg = Config::new("pocket_tts", &path);
    cfg.streaming = true;
    let mut tts = Tts::new(&cfg)?;
    req.voice = Some("alba");
    assert!(tts.stream(&req, |_, _, _| false).is_err());
    let mut total = 0;
    let audio = tts.stream(&req, |pcm, rate, ch| {
        assert_eq!(rate, 24000);
        assert_eq!(ch, 1);
        total += pcm.len();
        true
    })?;
    assert_eq!(total, audio.pcm.len());
    assert!(total > 0);
    println!("Pocket streaming cancel/reuse: {} samples", total);
    Ok(())
}
