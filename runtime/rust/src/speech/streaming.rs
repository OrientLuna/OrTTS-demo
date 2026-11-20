//! Incremental streaming ASR (16kHz mono F32, worker-local). Supports
//! `moonshine_asr` (English, revisable partials) and, on Sherpa-enabled builds,
//! `streaming_paraformer` and `zipformer_bilingual` (bilingual/Chinese with
//! `silence_ms` automatic utterance segmentation).
use super::{Config, RawConfig};
use crate::check;
use std::{
    ffi::{c_char, c_void, CStr},
    marker::PhantomData,
    ptr,
    rc::Rc,
    sync::{Arc, Mutex},
};

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct Settings {
    size: u32,
    pub update_ms: u32,
    pub min_partial_ms: u32,
    pub max_segment_ms: u32,
    /// Zero disables the energy endpoint; explicit flush and limit still apply.
    pub silence_ms: u32,
    /// RMS amplitude. This gate is not neural VAD.
    pub energy_threshold: f32,
}
impl Default for Settings {
    fn default() -> Self {
        Self {
            size: std::mem::size_of::<Self>() as u32,
            update_ms: 400,
            min_partial_ms: 1000,
            max_segment_ms: 15000,
            silence_ms: 800,
            energy_threshold: 0.003,
        }
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Partial,
    Flush,
    Silence,
    Limit,
}
#[derive(Clone, Debug)]
pub struct Event {
    pub kind: Kind,
    pub segment_id: u64,
    pub start_frame: u64,
    pub end_frame: u64,
    pub revision: u64,
    pub text: String,
    pub language: String,
}
#[repr(C)]
struct RawEvent {
    size: u32,
    endpoint: i32,
    segment: u64,
    start: u64,
    end: u64,
    revision: u64,
    text: *const c_char,
    language: *const c_char,
}
#[repr(C)]
#[derive(Default, Clone, Debug)]
pub struct Stats {
    size: u32,
    pub received_frames: u64,
    pub processed_frames: u64,
    pub encoded_samples: u64,
    pub updates: u64,
    pub buffered_pcm_frames: u64,
    pub cached_encoder_frames: u64,
    pub segment_frames: u64,
    pub peak_buffered_pcm_frames: u64,
    pub peak_cached_encoder_frames: u64,
    pub encoder_ms: f64,
    pub decoder_ms: f64,
}
impl Stats {
    /// Converts C runtime sentinel counts (`u64::MAX`, used when a backend does
    /// not expose a counter) into `None` so callers do not mistake them for real usage.
    pub const fn count_opt(value: u64) -> Option<u64> {
        if value == u64::MAX {
            None
        } else {
            Some(value)
        }
    }
    /// Converts non-finite C timing fields (`NaN` when unavailable) into `None`.
    pub fn ms_opt(value: f64) -> Option<f64> {
        value.is_finite().then_some(value)
    }
    pub const fn received_frames_opt(&self) -> Option<u64> {
        Self::count_opt(self.received_frames)
    }
    pub const fn processed_frames_opt(&self) -> Option<u64> {
        Self::count_opt(self.processed_frames)
    }
    pub const fn encoded_samples_opt(&self) -> Option<u64> {
        Self::count_opt(self.encoded_samples)
    }
    pub const fn updates_opt(&self) -> Option<u64> {
        Self::count_opt(self.updates)
    }
    pub const fn buffered_pcm_frames_opt(&self) -> Option<u64> {
        Self::count_opt(self.buffered_pcm_frames)
    }
    pub const fn cached_encoder_frames_opt(&self) -> Option<u64> {
        Self::count_opt(self.cached_encoder_frames)
    }
    pub const fn segment_frames_opt(&self) -> Option<u64> {
        Self::count_opt(self.segment_frames)
    }
    pub const fn peak_buffered_pcm_frames_opt(&self) -> Option<u64> {
        Self::count_opt(self.peak_buffered_pcm_frames)
    }
    pub const fn peak_cached_encoder_frames_opt(&self) -> Option<u64> {
        Self::count_opt(self.peak_cached_encoder_frames)
    }
    pub fn encoder_ms_opt(&self) -> Option<f64> {
        Self::ms_opt(self.encoder_ms)
    }
    pub fn decoder_ms_opt(&self) -> Option<f64> {
        Self::ms_opt(self.decoder_ms)
    }
}
/// Parses `speech::catalog()` and returns the incremental streaming ASR
/// families enabled in the current native build (e.g. `moonshine_asr`, and on
/// Sherpa-enabled builds `zipformer_bilingual` / `streaming_paraformer`).
pub fn families() -> Vec<String> {
    parse_catalog_families(&super::catalog())
}
/// Pure catalog JSON parser returning enabled `ortts_asr_stream_*` family IDs.
pub fn parse_catalog_families(catalog_json: &str) -> Vec<String> {
    fn skip_ws(b: &[u8], i: &mut usize) {
        while let Some(&c) = b.get(*i) {
            if c.is_ascii_whitespace() {
                *i += 1;
            } else {
                break;
            }
        }
    }
    fn parse_hex4(b: &[u8], i: &mut usize) -> Option<u32> {
        let slice = b.get(*i..*i + 4)?;
        let s = std::str::from_utf8(slice).ok()?;
        let v = u32::from_str_radix(s, 16).ok()?;
        *i += 4;
        Some(v)
    }
    fn parse_string(b: &[u8], i: &mut usize) -> Option<String> {
        skip_ws(b, i);
        if *b.get(*i)? != b'"' {
            return None;
        }
        *i += 1;
        let mut out = String::new();
        while let Some(&c) = b.get(*i) {
            *i += 1;
            match c {
                b'"' => return Some(out),
                b'\\' => {
                    let esc = *b.get(*i)?;
                    *i += 1;
                    match esc {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\u{0008}'),
                        b'f' => out.push('\u{000C}'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            let code = parse_hex4(b, i)?;
                            if (0xD800..=0xDBFF).contains(&code)
                                && b.get(*i..*i + 2) == Some(b"\\u")
                            {
                                *i += 2;
                                let low = parse_hex4(b, i)?;
                                if (0xDC00..=0xDFFF).contains(&low) {
                                    let cp = 0x10000 + (((code - 0xD800) << 10) | (low - 0xDC00));
                                    out.push(char::from_u32(cp)?);
                                    continue;
                                }
                            }
                            out.push(char::from_u32(code)?);
                        }
                        _ => return None,
                    }
                }
                _ => {
                    let start = *i - 1;
                    while *i < b.len() && b[*i] != b'"' && b[*i] != b'\\' {
                        *i += 1;
                    }
                    let chunk = std::str::from_utf8(&b[start..*i]).ok()?;
                    out.push_str(chunk);
                }
            }
        }
        None
    }
    fn skip_value(b: &[u8], i: &mut usize) -> Option<()> {
        skip_ws(b, i);
        match *b.get(*i)? {
            b'"' => {
                parse_string(b, i)?;
                Some(())
            }
            b'{' => {
                *i += 1;
                skip_ws(b, i);
                if b.get(*i) == Some(&b'}') {
                    *i += 1;
                    return Some(());
                }
                loop {
                    parse_string(b, i)?;
                    skip_ws(b, i);
                    if *b.get(*i)? != b':' {
                        return None;
                    }
                    *i += 1;
                    skip_value(b, i)?;
                    skip_ws(b, i);
                    match *b.get(*i)? {
                        b',' => *i += 1,
                        b'}' => {
                            *i += 1;
                            return Some(());
                        }
                        _ => return None,
                    }
                }
            }
            b'[' => {
                *i += 1;
                skip_ws(b, i);
                if b.get(*i) == Some(&b']') {
                    *i += 1;
                    return Some(());
                }
                loop {
                    skip_value(b, i)?;
                    skip_ws(b, i);
                    match *b.get(*i)? {
                        b',' => *i += 1,
                        b']' => {
                            *i += 1;
                            return Some(());
                        }
                        _ => return None,
                    }
                }
            }
            _ => {
                let start = *i;
                while let Some(&c) = b.get(*i) {
                    if c.is_ascii_alphanumeric() || matches!(c, b'-' | b'+' | b'.') {
                        *i += 1;
                    } else {
                        break;
                    }
                }
                (*i > start).then_some(())
            }
        }
    }
    fn parse_string_array(b: &[u8], i: &mut usize) -> Option<Vec<String>> {
        skip_ws(b, i);
        if *b.get(*i)? != b'[' {
            return None;
        }
        *i += 1;
        skip_ws(b, i);
        let mut items = Vec::new();
        if b.get(*i) == Some(&b']') {
            *i += 1;
            return Some(items);
        }
        loop {
            items.push(parse_string(b, i)?);
            skip_ws(b, i);
            match *b.get(*i)? {
                b',' => *i += 1,
                b']' => {
                    *i += 1;
                    return Some(items);
                }
                _ => return None,
            }
        }
    }
    fn parse_section(b: &[u8], i: &mut usize) -> Option<(Option<String>, Vec<String>)> {
        skip_ws(b, i);
        if *b.get(*i)? != b'{' {
            skip_value(b, i)?;
            return Some((None, Vec::new()));
        }
        *i += 1;
        skip_ws(b, i);
        let mut api = None;
        let mut fams = Vec::new();
        if b.get(*i) == Some(&b'}') {
            *i += 1;
            return Some((api, fams));
        }
        loop {
            let key = parse_string(b, i)?;
            skip_ws(b, i);
            if *b.get(*i)? != b':' {
                return None;
            }
            *i += 1;
            skip_ws(b, i);
            if key == "api" && b.get(*i) == Some(&b'"') {
                api = Some(parse_string(b, i)?);
            } else if key == "families" && b.get(*i) == Some(&b'[') {
                fams = parse_string_array(b, i)?;
            } else {
                skip_value(b, i)?;
            }
            skip_ws(b, i);
            match *b.get(*i)? {
                b',' => *i += 1,
                b'}' => {
                    *i += 1;
                    return Some((api, fams));
                }
                _ => return None,
            }
        }
    }

    let b = catalog_json.as_bytes();
    let mut i = 0;
    skip_ws(b, &mut i);
    if b.get(i) != Some(&b'{') {
        return Vec::new();
    }
    i += 1;
    skip_ws(b, &mut i);
    if b.get(i) == Some(&b'}') {
        return Vec::new();
    }
    let mut incremental = Vec::new();
    let mut compat = Vec::new();
    loop {
        let Some(key) = parse_string(b, &mut i) else {
            return Vec::new();
        };
        skip_ws(b, &mut i);
        if b.get(i) != Some(&b':') {
            return Vec::new();
        }
        i += 1;
        if key == "incremental_asr" {
            let Some((api, fams)) = parse_section(b, &mut i) else {
                return Vec::new();
            };
            if api.as_deref().is_none_or(|v| v == "ortts_asr_stream_*") {
                incremental = fams;
            }
        } else if key == "compatibility_asr" {
            let Some((api, fams)) = parse_section(b, &mut i) else {
                return Vec::new();
            };
            if api.as_deref() == Some("ortts_asr_stream_*") {
                compat = fams;
            }
        } else if skip_value(b, &mut i).is_none() {
            return Vec::new();
        }
        skip_ws(b, &mut i);
        match b.get(i) {
            Some(&b',') => i += 1,
            Some(&b'}') => break,
            _ => return Vec::new(),
        }
    }
    let mut out = Vec::new();
    for name in incremental.into_iter().chain(compat) {
        if !out.contains(&name) {
            out.push(name);
        }
    }
    out
}
type Callback = unsafe extern "C" fn(*mut c_void, *const RawEvent) -> i32;
extern "C" {
    fn ortts_asr_stream_abi_version() -> u32;
    fn ortts_asr_stream_create(
        c: *const RawConfig,
        s: *const Settings,
        out: *mut *mut c_void,
    ) -> i32;
    fn ortts_asr_stream_accept(
        e: *mut c_void,
        p: *const f32,
        n: usize,
        cb: Callback,
        u: *mut c_void,
    ) -> i32;
    fn ortts_asr_stream_finish(e: *mut c_void, cb: Callback, u: *mut c_void) -> i32;
    fn ortts_asr_stream_reset(e: *mut c_void) -> i32;
    fn ortts_asr_stream_cancel(e: *mut c_void);
    fn ortts_asr_stream_get_stats(e: *mut c_void, s: *mut Stats) -> i32;
    fn ortts_asr_stream_free(e: *mut c_void);
}
pub fn available() -> bool {
    unsafe { ortts_asr_stream_abi_version() == 1 }
}
pub struct Stream {
    raw: *mut c_void,
    _local: PhantomData<Rc<()>>,
    cancellation: Cancellation,
}
struct CancelState {
    raw: *mut c_void,
}
// SAFETY: the pointer is only used for the C API's atomic cancellation call,
// while holding the mutex. Stream::drop invalidates it under the same mutex
// before freeing the engine on its owner worker. This never transfers inference
// or destruction to another thread.
unsafe impl Send for CancelState {}
/// A UI/thread-safe cancellation token. Does not retain model weights; cancel
/// after the worker drops Stream is a no-op. Reset clears the native cancel flag.
#[derive(Clone)]
pub struct Cancellation {
    state: Arc<Mutex<CancelState>>,
}
impl Cancellation {
    pub fn cancel(&self) {
        let state = self.state.lock().unwrap_or_else(|e| e.into_inner());
        if !state.raw.is_null() {
            unsafe { ortts_asr_stream_cancel(state.raw) }
        }
    }
}
struct Receiver<'a, F> {
    callback: &'a mut F,
    failed: Option<String>,
}
unsafe extern "C" fn receive<F: FnMut(&Event) -> bool>(
    u: *mut c_void,
    raw: *const RawEvent,
) -> i32 {
    let state = &mut *(u as *mut Receiver<'_, F>);
    let result =
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| -> Result<bool, String> {
            let r = raw.as_ref().ok_or("Missing ASR event")?;
            if r.size != std::mem::size_of::<RawEvent>() as u32
                || r.text.is_null()
                || r.language.is_null()
            {
                return Err("Invalid ASR event".into());
            }
            let kind = match r.endpoint {
                0 => Kind::Partial,
                1 => Kind::Flush,
                2 => Kind::Silence,
                3 => Kind::Limit,
                _ => return Err("Unknown ASR endpoint".into()),
            };
            let event = Event {
                kind,
                segment_id: r.segment,
                start_frame: r.start,
                end_frame: r.end,
                revision: r.revision,
                text: CStr::from_ptr(r.text).to_string_lossy().into_owned(),
                language: CStr::from_ptr(r.language).to_string_lossy().into_owned(),
            };
            Ok((state.callback)(&event))
        }));
    match result {
        Ok(Ok(true)) => 0,
        Ok(Ok(false)) => 1,
        Ok(Err(e)) => {
            state.failed = Some(e);
            1
        }
        Err(_) => {
            state.failed = Some("ASR callback panicked".into());
            1
        }
    }
}
impl Stream {
    /// Config should select an enabled streaming ASR family from `families()`
    /// (such as `moonshine_asr`, `streaming_paraformer`, or `zipformer_bilingual`)
    /// with `streaming = true` and offline-only fields cleared (`Config::new_streaming_asr`).
    /// `Settings` configures partial cadence, `silence_ms` endpointing, and segment limits.
    pub fn new(c: &Config<'_>, settings: Settings) -> Result<Self, String> {
        if !available() {
            return Err("Incremental ASR feature disabled or unsupported ABI".into());
        }
        let prepared = c.prepare().map_err(|e| e.to_string())?;
        let mut out = ptr::null_mut();
        check(unsafe { ortts_asr_stream_create(&prepared.raw, &settings, &mut out) })?;
        Ok(Self {
            raw: out,
            _local: PhantomData,
            cancellation: Cancellation {
                state: Arc::new(Mutex::new(CancelState { raw: out })),
            },
        })
    }
    /// Callback true continues; false cancels until reset. Never reenter the SDK.
    pub fn accept_with<F: FnMut(&Event) -> bool>(
        &mut self,
        pcm: &[f32],
        mut callback: F,
    ) -> Result<(), String> {
        let mut receiver = Receiver {
            callback: &mut callback,
            failed: None,
        };
        let status = unsafe {
            ortts_asr_stream_accept(
                self.raw,
                pcm.as_ptr(),
                pcm.len(),
                receive::<F>,
                &mut receiver as *mut _ as *mut c_void,
            )
        };
        if let Some(e) = receiver.failed {
            return Err(e);
        }
        check(status)
    }
    pub fn finish_with<F: FnMut(&Event) -> bool>(&mut self, mut callback: F) -> Result<(), String> {
        let mut receiver = Receiver {
            callback: &mut callback,
            failed: None,
        };
        let status = unsafe {
            ortts_asr_stream_finish(
                self.raw,
                receive::<F>,
                &mut receiver as *mut _ as *mut c_void,
            )
        };
        if let Some(e) = receiver.failed {
            return Err(e);
        }
        check(status)
    }
    pub fn accept(&mut self, pcm: &[f32]) -> Result<Vec<Event>, String> {
        let mut events = Vec::new();
        self.accept_with(pcm, |e| {
            events.push(e.clone());
            true
        })?;
        Ok(events)
    }
    pub fn finish(&mut self) -> Result<Vec<Event>, String> {
        let mut events = Vec::new();
        self.finish_with(|e| {
            events.push(e.clone());
            true
        })?;
        Ok(events)
    }
    pub fn reset(&mut self) -> Result<(), String> {
        check(unsafe { ortts_asr_stream_reset(self.raw) })
    }
    pub fn cancel(&self) {
        self.cancellation.cancel()
    }
    pub fn cancellation(&self) -> Cancellation {
        self.cancellation.clone()
    }
    pub fn stats(&self) -> Result<Stats, String> {
        let mut stats = Stats {
            size: std::mem::size_of::<Stats>() as u32,
            ..Stats::default()
        };
        check(unsafe { ortts_asr_stream_get_stats(self.raw, &mut stats) })?;
        Ok(stats)
    }
}
impl Drop for Stream {
    fn drop(&mut self) {
        {
            let mut state = self
                .cancellation
                .state
                .lock()
                .unwrap_or_else(|e| e.into_inner());
            state.raw = ptr::null_mut();
        }
        unsafe { ortts_asr_stream_free(self.raw) }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_streaming_asr_sets_clean_contract_fields() {
        let cfg = Config::new_streaming_asr("streaming_paraformer", "/models/paraformer", 2);
        assert_eq!(cfg.family, "streaming_paraformer");
        assert_eq!(cfg.model_path, "/models/paraformer");
        assert_eq!(cfg.threads, 2);
        assert!(cfg.streaming);
        assert!(cfg.session_options.is_empty());
        assert!(cfg.espeak_library.is_none());
        assert!(cfg.espeak_data.is_none());
        assert_eq!(cfg.max_input_frames, 0);
    }

    #[test]
    fn stats_opt_converts_sentinels_to_none() {
        let sherpa_like = Stats {
            size: std::mem::size_of::<Stats>() as u32,
            received_frames: 16_000,
            processed_frames: u64::MAX,
            encoded_samples: u64::MAX,
            updates: 4,
            buffered_pcm_frames: u64::MAX,
            cached_encoder_frames: u64::MAX,
            segment_frames: 8_000,
            peak_buffered_pcm_frames: u64::MAX,
            peak_cached_encoder_frames: u64::MAX,
            encoder_ms: f64::NAN,
            decoder_ms: f64::INFINITY,
        };
        assert_eq!(sherpa_like.received_frames_opt(), Some(16_000));
        assert_eq!(sherpa_like.processed_frames_opt(), None);
        assert_eq!(sherpa_like.encoded_samples_opt(), None);
        assert_eq!(sherpa_like.updates_opt(), Some(4));
        assert_eq!(sherpa_like.buffered_pcm_frames_opt(), None);
        assert_eq!(sherpa_like.cached_encoder_frames_opt(), None);
        assert_eq!(sherpa_like.segment_frames_opt(), Some(8_000));
        assert_eq!(sherpa_like.peak_buffered_pcm_frames_opt(), None);
        assert_eq!(sherpa_like.peak_cached_encoder_frames_opt(), None);
        assert_eq!(sherpa_like.encoder_ms_opt(), None);
        assert_eq!(sherpa_like.decoder_ms_opt(), None);

        let moonshine_like = Stats {
            buffered_pcm_frames: 320,
            cached_encoder_frames: 64,
            peak_buffered_pcm_frames: 640,
            peak_cached_encoder_frames: 128,
            encoder_ms: 12.5,
            decoder_ms: 3.25,
            ..sherpa_like
        };
        assert_eq!(moonshine_like.buffered_pcm_frames_opt(), Some(320));
        assert_eq!(moonshine_like.cached_encoder_frames_opt(), Some(64));
        assert_eq!(moonshine_like.peak_buffered_pcm_frames_opt(), Some(640));
        assert_eq!(moonshine_like.peak_cached_encoder_frames_opt(), Some(128));
        assert_eq!(moonshine_like.encoder_ms_opt(), Some(12.5));
        assert_eq!(moonshine_like.decoder_ms_opt(), Some(3.25));
    }

    #[test]
    fn parse_catalog_families_extracts_incremental_and_compat_stream_families() {
        let disabled = r#"{"schema":1,"tts":[],"asr":[],"disabled":true}"#;
        assert!(parse_catalog_families(disabled).is_empty());

        let moonshine_only = r#"{
            "schema": 1,
            "tts": ["kokoro_tts"],
            "incremental_asr": {
                "abi": 1,
                "api": "ortts_asr_stream_*",
                "families": ["moonshine_asr"]
            },
            "ignored": { "families": ["not_streaming"] }
        }"#;
        assert_eq!(
            parse_catalog_families(moonshine_only),
            vec!["moonshine_asr".to_string()]
        );

        let with_sherpa = r#"{
            "schema": 1,
            "incremental_asr": {
                "abi": 1,
                "api": "ortts_asr_stream_*",
                "families": ["moonshine_asr"]
            },
            "compatibility_asr": {
                "families": ["zipformer_bilingual", "streaming_paraformer"],
                "executor": "sherpa-onnx-1.13.8/onnxruntime-cpu",
                "api": "ortts_asr_stream_*"
            }
        }"#;
        assert_eq!(
            parse_catalog_families(with_sherpa),
            vec![
                "moonshine_asr".to_string(),
                "zipformer_bilingual".to_string(),
                "streaming_paraformer".to_string(),
            ]
        );

        let other_compat_api = r#"{
            "incremental_asr": { "families": ["moonshine_asr"], "api": "ortts_asr_stream_*" },
            "compatibility_asr": { "families": ["offline_only"], "api": "ortts_asr_*" }
        }"#;
        assert_eq!(
            parse_catalog_families(other_compat_api),
            vec!["moonshine_asr".to_string()]
        );
        assert!(parse_catalog_families("not json").is_empty());
    }
}
