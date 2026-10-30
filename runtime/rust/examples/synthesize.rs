use ortts_engine::Engine;
use std::{env, fs::File, io::Write};
fn main() -> Result<(),Box<dyn std::error::Error>> {
    let args:Vec<_>=env::args().collect();
    if args.len()!=7 { return Err("usage: synthesize ASSET_ROOT P3|P5 MANIFEST_SHA TEXT OUTPUT.f32 stream|offline".into()); }
    let stream=match args[6].as_str() { "stream"=>true, "offline"=>false, _=>return Err("mode must be stream or offline".into()) };
    let mut engine=Engine::new(&args[1],&args[2],None,&args[3],4,stream)?;
    let mut chunks=0;let mut collected=Vec::new();
    let audio=if stream { engine.stream(&args[4],20261023,128,|pcm,rate|{
        assert_eq!(rate,24000);chunks+=1;collected.extend_from_slice(pcm);true
    })? }else { engine.synthesize(&args[4],20261023,128)? };
    if stream && collected!=audio.pcm { return Err("chunk/final PCM mismatch".into()); }
    let mut out=File::create(&args[5])?;
    for sample in &audio.pcm {out.write_all(&sample.to_le_bytes())?;}
    let duration=audio.pcm.len() as f64 / audio.sample_rate as f64;
    println!("samples={} audio_s={:.3} chunks={} API_ms={:.3} generation_RTF={:.4} first_PCM_ms={:.3}",audio.pcm.len(),duration,chunks,audio.metrics.api_ms,audio.metrics.generation_ms/1000.0/duration,audio.metrics.first_pcm_ms);
    Ok(())
}
