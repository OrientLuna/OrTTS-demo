//! Additive speech ABI. Matched --speech library required. No playback/downloads.
//! Handles stay on a worker (neither Send nor Sync). ASR is buffered-final only.
use crate::{check, cstring, Metrics};
use std::{
    ffi::{c_char, c_void, CStr, CString},
    marker::PhantomData,
    ptr,
    rc::Rc,
};
#[repr(C)]
struct Pair {
    key: *const c_char,
    value: *const c_char,
}
#[repr(C)]
struct RawConfig {
    size: u32,
    family: *const c_char,
    path: *const c_char,
    threads: i32,
    streaming: i32,
    options: *const Pair,
    count: usize,
    library: *const c_char,
    data: *const c_char,
    limit: usize,
}
#[repr(C)]
struct RawRequest {
    size: u32,
    text: *const c_char,
    language: *const c_char,
    voice: *const c_char,
    seed_set: i32,
    seed: u64,
    options: *const Pair,
    count: usize,
    reference: *const f32,
    frames: usize,
    rate: i32,
    channels: i32,
    reference_text: *const c_char,
}
type Callback = Option<unsafe extern "C" fn(*mut c_void, *const f32, usize, i32, i32) -> i32>;
extern "C" {
    fn ortts_speech_abi_version() -> u32;
    fn ortts_speech_catalog_json() -> *const c_char;
    fn ortts_tts_create(c: *const RawConfig, out: *mut *mut c_void) -> i32;
    fn ortts_tts_synthesize(
        e: *mut c_void,
        r: *const RawRequest,
        cb: Callback,
        user: *mut c_void,
        out: *mut *mut c_void,
    ) -> i32;
    fn ortts_tts_free(e: *mut c_void);
    fn ortts_speech_audio_samples(a: *const c_void) -> *const f32;
    fn ortts_speech_audio_frames(a: *const c_void) -> usize;
    fn ortts_speech_audio_sample_rate(a: *const c_void) -> i32;
    fn ortts_speech_audio_channels(a: *const c_void) -> i32;
    fn ortts_speech_audio_metrics(a: *const c_void, m: *mut Metrics) -> i32;
    fn ortts_speech_audio_free(a: *mut c_void);
    fn ortts_asr_create(c: *const RawConfig, out: *mut *mut c_void) -> i32;
    fn ortts_asr_run(
        e: *mut c_void,
        p: *const f32,
        n: usize,
        lang: *const c_char,
        out: *mut *mut c_void,
    ) -> i32;
    fn ortts_asr_accept(e: *mut c_void, p: *const f32, n: usize) -> i32;
    fn ortts_asr_finish(e: *mut c_void, lang: *const c_char, out: *mut *mut c_void) -> i32;
    fn ortts_asr_reset(e: *mut c_void) -> i32;
    fn ortts_asr_free(e: *mut c_void);
    fn ortts_transcript_text(t: *const c_void) -> *const c_char;
    fn ortts_transcript_language(t: *const c_void) -> *const c_char;
    fn ortts_transcript_api_ms(t: *const c_void) -> f64;
    fn ortts_transcript_free(t: *mut c_void);
}
fn cp(s: &Option<CString>) -> *const c_char {
    s.as_ref().map_or(ptr::null(), |s| s.as_ptr())
}
fn pairs(v: &[(&str, &str)]) -> Result<(Vec<(CString, CString)>, Vec<Pair>), String> {
    let owned = v
        .iter()
        .map(|(k, v)| Ok((cstring(k)?, cstring(v)?)))
        .collect::<Result<Vec<_>, String>>()?;
    let raw = owned
        .iter()
        .map(|(k, v)| Pair {
            key: k.as_ptr(),
            value: v.as_ptr(),
        })
        .collect();
    Ok((owned, raw))
}
pub fn available() -> bool {
    unsafe { ortts_speech_abi_version() == 1 }
}
pub fn catalog() -> String {
    unsafe {
        CStr::from_ptr(ortts_speech_catalog_json())
            .to_string_lossy()
            .into_owned()
    }
}
pub struct Config<'a> {
    pub family: &'a str,
    pub model_path: &'a str,
    pub threads: i32,
    pub streaming: bool,
    pub session_options: &'a [(&'a str, &'a str)],
    pub espeak_library: Option<&'a str>,
    pub espeak_data: Option<&'a str>,
    pub max_input_frames: usize,
}
impl<'a> Config<'a> {
    pub fn new(family: &'a str, model_path: &'a str) -> Self {
        Self {
            family,
            model_path,
            threads: 4,
            streaming: false,
            session_options: &[],
            espeak_library: None,
            espeak_data: None,
            max_input_frames: 0,
        }
    }
    fn open(&self, asr: bool) -> Result<*mut c_void, String> {
        if !available() {
            return Err("Speech feature disabled or unsupported ABI".into());
        }
        let family = cstring(self.family)?;
        let path = cstring(self.model_path)?;
        let library = self.espeak_library.map(cstring).transpose()?;
        let data = self.espeak_data.map(cstring).transpose()?;
        let (_owned, options) = pairs(self.session_options)?;
        let c = RawConfig {
            size: std::mem::size_of::<RawConfig>() as u32,
            family: family.as_ptr(),
            path: path.as_ptr(),
            threads: self.threads,
            streaming: self.streaming as i32,
            options: options.as_ptr(),
            count: options.len(),
            library: cp(&library),
            data: cp(&data),
            limit: self.max_input_frames,
        };
        let mut out = ptr::null_mut();
        check(unsafe {
            if asr {
                ortts_asr_create(&c, &mut out)
            } else {
                ortts_tts_create(&c, &mut out)
            }
        })?;
        Ok(out)
    }
}
pub struct Reference<'a> {
    pub pcm: &'a [f32],
    pub sample_rate: i32,
    pub channels: i32,
    pub text: &'a str,
}
pub struct Request<'a> {
    pub text: &'a str,
    pub language: Option<&'a str>,
    pub voice: Option<&'a str>,
    pub seed: Option<u64>,
    pub options: &'a [(&'a str, &'a str)],
    pub reference: Option<Reference<'a>>,
}
impl<'a> Request<'a> {
    pub fn new(text: &'a str) -> Self {
        Self {
            text,
            language: None,
            voice: None,
            seed: None,
            options: &[],
            reference: None,
        }
    }
}
pub struct Audio {
    pub pcm: Vec<f32>,
    pub sample_rate: i32,
    pub channels: i32,
    pub metrics: Metrics,
}
pub struct Tts {
    raw: *mut c_void,
    _local: PhantomData<Rc<()>>,
}
impl Tts {
    pub fn new(c: &Config<'_>) -> Result<Self, String> {
        Ok(Self {
            raw: c.open(false)?,
            _local: PhantomData,
        })
    }
    pub fn synthesize(&mut self, r: &Request<'_>) -> Result<Audio, String> {
        self.run(r, None, ptr::null_mut())
    }
    /// Chunk PCM is borrowed and interleaved. Return false to cancel; panic is contained.
    pub fn stream<F: FnMut(&[f32], i32, i32) -> bool>(
        &mut self,
        r: &Request<'_>,
        sink: F,
    ) -> Result<Audio, String> {
        struct State<F> {
            f: F,
            panicked: bool,
        }
        unsafe extern "C" fn invoke<F: FnMut(&[f32], i32, i32) -> bool>(
            u: *mut c_void,
            p: *const f32,
            n: usize,
            rate: i32,
            ch: i32,
        ) -> i32 {
            let s = &mut *(u as *mut State<F>);
            if ch < 1 || ch > 2 || n.checked_mul(ch as usize).is_none() {
                return 1;
            }
            match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                (s.f)(std::slice::from_raw_parts(p, n * ch as usize), rate, ch)
            })) {
                Ok(keep) => (!keep) as i32,
                Err(_) => {
                    s.panicked = true;
                    1
                }
            }
        }
        let mut s = State {
            f: sink,
            panicked: false,
        };
        let out = self.run(r, Some(invoke::<F>), &mut s as *mut _ as *mut c_void);
        if s.panicked {
            Err("PCM callback panicked (cancelled)".into())
        } else {
            out
        }
    }
    fn run(&mut self, r: &Request<'_>, cb: Callback, user: *mut c_void) -> Result<Audio, String> {
        let text = cstring(r.text)?;
        let lang = r.language.map(cstring).transpose()?;
        let voice = r.voice.map(cstring).transpose()?;
        let ref_text = r.reference.as_ref().map(|v| cstring(v.text)).transpose()?;
        let (_owned, options) = pairs(r.options)?;
        let (reference, frames, rate, channels) = if let Some(v) = &r.reference {
            if v.channels < 1 || v.channels > 2 || v.pcm.len() % v.channels as usize != 0 {
                return Err("Invalid reference channels/frames".into());
            }
            (
                v.pcm.as_ptr(),
                v.pcm.len() / v.channels as usize,
                v.sample_rate,
                v.channels,
            )
        } else {
            (ptr::null(), 0, 0, 0)
        };
        let req = RawRequest {
            size: std::mem::size_of::<RawRequest>() as u32,
            text: text.as_ptr(),
            language: cp(&lang),
            voice: cp(&voice),
            seed_set: r.seed.is_some() as i32,
            seed: r.seed.unwrap_or(0),
            options: options.as_ptr(),
            count: options.len(),
            reference,
            frames,
            rate,
            channels,
            reference_text: cp(&ref_text),
        };
        let mut out = ptr::null_mut();
        check(unsafe { ortts_tts_synthesize(self.raw, &req, cb, user, &mut out) })?;
        struct Owned(*mut c_void);
        impl Drop for Owned {
            fn drop(&mut self) {
                unsafe { ortts_speech_audio_free(self.0) }
            }
        }
        let a = Owned(out);
        let (frames, ch, rate, p) = unsafe {
            (
                ortts_speech_audio_frames(a.0),
                ortts_speech_audio_channels(a.0),
                ortts_speech_audio_sample_rate(a.0),
                ortts_speech_audio_samples(a.0),
            )
        };
        if ch < 1 || ch > 2 || p.is_null() || frames == 0 {
            return Err("Invalid native PCM".into());
        }
        let n = frames.checked_mul(ch as usize).ok_or("PCM size overflow")?;
        let mut metrics = Metrics::default();
        check(unsafe { ortts_speech_audio_metrics(a.0, &mut metrics) })?;
        Ok(Audio {
            pcm: unsafe { std::slice::from_raw_parts(p, n).to_vec() },
            sample_rate: rate,
            channels: ch,
            metrics,
        })
    }
}
impl Drop for Tts {
    fn drop(&mut self) {
        unsafe { ortts_tts_free(self.raw) }
    }
}
pub struct Transcript {
    pub text: String,
    pub language: String,
    pub api_ms: f64,
}
fn transcript(p: *mut c_void) -> Transcript {
    unsafe {
        let t = Transcript {
            text: CStr::from_ptr(ortts_transcript_text(p))
                .to_string_lossy()
                .into_owned(),
            language: CStr::from_ptr(ortts_transcript_language(p))
                .to_string_lossy()
                .into_owned(),
            api_ms: ortts_transcript_api_ms(p),
        };
        ortts_transcript_free(p);
        t
    }
}
pub struct Asr {
    raw: *mut c_void,
    _local: PhantomData<Rc<()>>,
}
impl Asr {
    pub fn new(c: &Config<'_>) -> Result<Self, String> {
        Ok(Self {
            raw: c.open(true)?,
            _local: PhantomData,
        })
    }
    pub fn run(&mut self, pcm16k: &[f32], language: Option<&str>) -> Result<Transcript, String> {
        let l = language.map(cstring).transpose()?;
        let mut out = ptr::null_mut();
        check(unsafe { ortts_asr_run(self.raw, pcm16k.as_ptr(), pcm16k.len(), cp(&l), &mut out) })?;
        Ok(transcript(out))
    }
    pub fn accept(&mut self, pcm16k: &[f32]) -> Result<(), String> {
        check(unsafe { ortts_asr_accept(self.raw, pcm16k.as_ptr(), pcm16k.len()) })
    }
    pub fn finish(&mut self, language: Option<&str>) -> Result<Transcript, String> {
        let l = language.map(cstring).transpose()?;
        let mut out = ptr::null_mut();
        check(unsafe { ortts_asr_finish(self.raw, cp(&l), &mut out) })?;
        Ok(transcript(out))
    }
    pub fn reset(&mut self) -> Result<(), String> {
        check(unsafe { ortts_asr_reset(self.raw) })
    }
}
impl Drop for Asr {
    fn drop(&mut self) {
        unsafe { ortts_asr_free(self.raw) }
    }
}
