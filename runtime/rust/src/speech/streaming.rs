//! Incremental Moonshine ASR. English, 16kHz mono F32. Partials are revisable.
//! CPU bounded-overlap encoder; decoder recomputes hypotheses. Worker-local.
use super::{cp, Config, RawConfig};
use crate::{check, cstring};
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
    /// Config must select moonshine_asr and streaming=true. Typed Settings
    /// replaces offline options. English is the only language in this version.
    pub fn new(c: &Config<'_>, settings: Settings) -> Result<Self, String> {
        if !available() {
            return Err("Incremental ASR feature disabled or unsupported ABI".into());
        }
        let family = cstring(c.family)?;
        let path = cstring(c.model_path)?;
        let library = c.espeak_library.map(cstring).transpose()?;
        let data = c.espeak_data.map(cstring).transpose()?;
        let (_owned, options) = super::pairs(c.session_options)?;
        let raw = RawConfig {
            size: std::mem::size_of::<RawConfig>() as u32,
            family: family.as_ptr(),
            path: path.as_ptr(),
            threads: c.threads,
            streaming: c.streaming as i32,
            options: options.as_ptr(),
            count: options.len(),
            library: cp(&library),
            data: cp(&data),
            limit: c.max_input_frames,
        };
        let mut out = ptr::null_mut();
        check(unsafe { ortts_asr_stream_create(&raw, &settings, &mut out) })?;
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
