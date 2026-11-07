use ortts_engine::speech::{
    streaming::{Kind, Settings, Stream},
    Config,
};
fn main() -> Result<(), String> {
    let mut args = std::env::args().skip(1);
    let model = args.next().ok_or("asr_stream MODEL INPUT_16K_MONO_F32")?;
    let input = args.next().ok_or("asr_stream MODEL INPUT_16K_MONO_F32")?;
    let bytes = std::fs::read(input).map_err(|e| e.to_string())?;
    if bytes.len() % 4 != 0 {
        return Err("F32 byte alignment".into());
    }
    let pcm: Vec<f32> = bytes
        .chunks_exact(4)
        .map(|v| f32::from_le_bytes(v.try_into().unwrap()))
        .collect();
    let mut config = Config::new("moonshine_asr", &model);
    config.streaming = true;
    let mut settings = Settings::default();
    settings.silence_ms = 0;
    let mut stream = Stream::new(&config, settings)?;
    let mut partials = 0;
    let mut final_text = String::new();
    for block in pcm.chunks(777) {
        for event in stream.accept(block)? {
            assert_eq!(event.kind, Kind::Partial);
            partials += 1;
            println!("partial {}: {}", event.revision, event.text);
        }
    }
    for event in stream.finish()? {
        assert_eq!(event.kind, Kind::Flush);
        final_text = event.text;
    }
    assert!(partials > 0 && final_text.contains("station"));
    assert!(stream.finish()?.is_empty());
    stream.cancel();
    assert!(stream.accept(&pcm[..80]).is_err());
    stream.reset()?;
    let mut cancelled = false;
    for block in pcm.chunks(6400) {
        if stream.accept_with(block, |_| false).is_err() {
            cancelled = true;
            break;
        }
    }
    assert!(cancelled);
    stream.reset()?;
    let token = stream.cancellation();
    let mut thread_cancelled = false;
    for block in pcm.chunks(6400) {
        if stream
            .accept_with(block, |_| {
                let token = token.clone();
                std::thread::spawn(move || token.cancel()).join().unwrap();
                true
            })
            .is_err()
        {
            thread_cancelled = true;
            break;
        }
    }
    assert!(thread_cancelled);
    stream.reset()?;
    // Catch callback panics before they cross the C ABI; reset restores reuse.
    let mut panic_caught = false;
    for block in pcm.chunks(6400) {
        if let Err(e) = stream.accept_with(block, |_| panic!("intentional ASR callback test")) {
            assert!(e.contains("panicked"));
            panic_caught = true;
            break;
        }
    }
    assert!(panic_caught);
    stream.reset()?;
    let mut reused = String::new();
    for block in pcm.chunks(1600) {
        stream.accept(block)?;
    }
    for event in stream.finish()? {
        reused = event.text;
    }
    assert_eq!(reused, final_text);
    let stats = stream.stats()?;
    assert_eq!(stats.buffered_pcm_frames, 0);
    let survivor = stream.cancellation();
    drop(stream);
    survivor.cancel();
    println!("PASS partials={partials} final={final_text} stats={stats:?}");
    Ok(())
}
