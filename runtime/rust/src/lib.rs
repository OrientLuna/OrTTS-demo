use std::{ffi::{CStr, CString, c_char, c_void}, marker::PhantomData, ptr, rc::Rc};

#[repr(C)]
struct Config {
    struct_size: u32, root: *const c_char, variant: *const c_char,
    speaker: *const c_char, manifest: *const c_char, threads: i32, streaming: i32,
}
#[repr(C)]
struct Request { struct_size: u32, text: *const c_char, seed: u64, max_tokens: i32 }
#[derive(Clone, Copy, Debug, Default)]
#[repr(C)]
pub struct Metrics {
    pub api_ms: f64, pub callback_ms: f64, pub generation_ms: f64,
    pub first_pcm_ms: f64, pub chunks: usize,
}
type Callback = Option<unsafe extern "C" fn(*mut c_void, *const f32, usize, i32) -> i32>;
extern "C" {
    fn ortts_abi_version() -> u32;
    fn ortts_last_error() -> *const c_char;
    fn ortts_engine_create(cfg: *const Config, out: *mut *mut c_void) -> i32;
    fn ortts_engine_synthesize(engine: *mut c_void, req: *const Request, cb: Callback, user: *mut c_void, out: *mut *mut c_void) -> i32;
    fn ortts_engine_free(engine: *mut c_void);
    fn ortts_audio_samples(audio: *const c_void) -> *const f32;
    fn ortts_audio_sample_count(audio: *const c_void) -> usize;
    fn ortts_audio_sample_rate(audio: *const c_void) -> i32;
    fn ortts_audio_metrics(audio: *const c_void, metrics: *mut Metrics) -> i32;
    fn ortts_audio_free(audio: *mut c_void);
}
fn cstring(s: &str) -> Result<CString, String> { CString::new(s).map_err(|_| "Interior NUL in input".into()) }
fn check(status: i32) -> Result<(), String> {
    if status == 0 { Ok(()) } else {
        Err(format!("OrTTS status {status}: {}", unsafe { CStr::from_ptr(ortts_last_error()).to_string_lossy() }))
    }
}
pub struct Audio { pub pcm: Vec<f32>, pub sample_rate: i32, pub metrics: Metrics }
/// Own on a dedicated worker. Deliberately neither Send nor Sync; handles are
/// serialized by this prototype and must never be freed from a PCM callback.
pub struct Engine { raw: *mut c_void, _local: PhantomData<Rc<()>> }
impl Engine {
    pub fn new(root: &str, variant: &str, speaker: Option<&str>, manifest_sha: &str, threads: i32, streaming: bool) -> Result<Self, String> {
        if unsafe { ortts_abi_version() } != 1 { return Err("Unsupported OrTTS ABI".into()); }
        let root = cstring(root)?; let variant = cstring(variant)?;
        let speaker = speaker.map(cstring).transpose()?; let manifest = cstring(manifest_sha)?;
        let cfg = Config { struct_size: std::mem::size_of::<Config>() as u32,
            root: root.as_ptr(), variant: variant.as_ptr(), speaker: speaker.as_ref().map_or(ptr::null(), |s| s.as_ptr()),
            manifest: manifest.as_ptr(), threads, streaming: streaming as i32 };
        let mut raw = ptr::null_mut();
        check(unsafe { ortts_engine_create(&cfg, &mut raw) })?;
        Ok(Self { raw, _local: PhantomData })
    }
    pub fn synthesize(&mut self, text: &str, seed: u64, max_tokens: i32) -> Result<Audio, String> {
        self.run(text, seed, max_tokens, None, ptr::null_mut())
    }
    /// Return false from the callback to cancel. PCM is borrowed for the callback
    /// only. Panic is caught at this boundary, converted to cancellation/error.
    pub fn stream<F: FnMut(&[f32], i32) -> bool>(&mut self, text: &str, seed: u64, max_tokens: i32, sink: F) -> Result<Audio, String> {
        struct State<F> { f: F, panicked: bool }
        unsafe extern "C" fn invoke<F: FnMut(&[f32], i32) -> bool>(p: *mut c_void, pcm: *const f32, n: usize, rate: i32) -> i32 {
            let s = &mut *(p as *mut State<F>);
            match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| (s.f)(std::slice::from_raw_parts(pcm,n),rate))) {
                Ok(keep) => (!keep) as i32,
                Err(_) => { s.panicked=true; 1 }
            }
        }
        let mut state = State { f: sink, panicked: false };
        let result=self.run(text,seed,max_tokens,Some(invoke::<F>), &mut state as *mut _ as *mut c_void);
        if state.panicked { Err("PCM callback panicked (generation cancelled)".into()) } else { result }
    }
    fn run(&mut self, text: &str, seed: u64, max_tokens: i32, cb: Callback, user: *mut c_void) -> Result<Audio, String> {
        let text = cstring(text)?;
        let req = Request { struct_size: std::mem::size_of::<Request>() as u32, text: text.as_ptr(), seed, max_tokens };
        let mut out = ptr::null_mut();
        check(unsafe { ortts_engine_synthesize(self.raw,&req,cb,user,&mut out) })?;
        struct Owned(*mut c_void); impl Drop for Owned { fn drop(&mut self) { unsafe { ortts_audio_free(self.0) } } }
        let out=Owned(out); let mut metrics=Metrics::default();
        check(unsafe { ortts_audio_metrics(out.0,&mut metrics) })?;
        let pcm=unsafe { std::slice::from_raw_parts(ortts_audio_samples(out.0), ortts_audio_sample_count(out.0)).to_vec() };
        Ok(Audio { pcm, sample_rate: unsafe { ortts_audio_sample_rate(out.0) }, metrics })
    }
}
impl Drop for Engine { fn drop(&mut self) { unsafe { ortts_engine_free(self.raw) } } }
