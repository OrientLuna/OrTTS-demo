//! One worker-owned TTS engine. Call `evict_expired` from a host idle timer;
//! no background thread is created and this cache is neither Send nor Sync.
use super::{Audio, Config, Request, Tts};
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

/// Bounded to one model. Voices are request fields, not separate cached engines.
/// Identity must describe verified assets (including external voices), not just a
/// filename. This helper does not download, hash, or authorize model packages.
pub struct TtsCache {
    entry: Option<Entry>,
    idle_ttl: Duration,
}
impl TtsCache {
    pub fn new(idle_ttl: Duration) -> Self {
        Self {
            entry: None,
            idle_ttl,
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
    fn use_engine<R>(
        &mut self,
        config: &Config<'_>,
        identity: &str,
        call: impl FnOnce(&mut Tts) -> Result<R, String>,
    ) -> Result<(R, bool), String> {
        if identity.is_empty() {
            return Err("Verified asset identity is required".into());
        }
        self.evict_expired();
        let key = Key::new(config, identity);
        let reused = self.entry.as_ref().is_some_and(|e| e.key == key);
        if !reused {
            // Drop before loading: never hold old and new model weights together.
            self.clear();
            self.entry = Some(Entry {
                key,
                engine: Tts::new(config)?,
                last_used: Instant::now(),
            });
        }
        let entry = self.entry.as_mut().expect("created above");
        let result = call(&mut entry.engine);
        entry.last_used = Instant::now();
        match result {
            Ok(value) => Ok((value, reused)),
            Err(error) => {
                self.clear();
                Err(error)
            }
        }
    }
    pub fn synthesize(
        &mut self,
        config: &Config<'_>,
        identity: &str,
        request: &Request<'_>,
    ) -> Result<(Audio, bool), String> {
        self.use_engine(config, identity, |engine| engine.synthesize(request))
    }
    pub fn stream<F: FnMut(&[f32], i32, i32) -> bool>(
        &mut self,
        config: &Config<'_>,
        identity: &str,
        request: &Request<'_>,
        sink: F,
    ) -> Result<(Audio, bool), String> {
        self.use_engine(config, identity, |engine| engine.stream(request, sink))
    }
}
