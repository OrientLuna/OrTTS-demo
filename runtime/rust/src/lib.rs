use std::{
    ffi::{c_char, c_void, CStr, CString},
    marker::PhantomData,
    ptr,
    rc::Rc,
};

#[repr(C)]
struct Config {
    struct_size: u32,
    root: *const c_char,
    variant: *const c_char,
    speaker: *const c_char,
    manifest: *const c_char,
    threads: i32,
    streaming: i32,
}
#[repr(C)]
struct Request {
    struct_size: u32,
    text: *const c_char,
    seed: u64,
    max_tokens: i32,
}
#[derive(Clone, Copy, Debug, Default)]
#[repr(C)]
pub struct Metrics {
    pub api_ms: f64,
    pub callback_ms: f64,
    pub generation_ms: f64,
    pub first_pcm_ms: f64,
    pub chunks: usize,
}
type Callback = Option<unsafe extern "C" fn(*mut c_void, *const f32, usize, i32) -> i32>;
extern "C" {
    fn ortts_abi_version() -> u32;
    fn ortts_last_error() -> *const c_char;
    fn ortts_engine_create(cfg: *const Config, out: *mut *mut c_void) -> i32;
    fn ortts_engine_synthesize(
        engine: *mut c_void,
        req: *const Request,
        cb: Callback,
        user: *mut c_void,
        out: *mut *mut c_void,
    ) -> i32;
    fn ortts_engine_free(engine: *mut c_void);
    fn ortts_audio_samples(audio: *const c_void) -> *const f32;
    fn ortts_audio_sample_count(audio: *const c_void) -> usize;
    fn ortts_audio_sample_rate(audio: *const c_void) -> i32;
    fn ortts_audio_metrics(audio: *const c_void, metrics: *mut Metrics) -> i32;
    fn ortts_audio_free(audio: *mut c_void);
}
fn cstring(s: &str) -> Result<CString, String> {
    CString::new(s).map_err(|_| "Interior NUL in input".into())
}
fn check(status: i32) -> Result<(), String> {
    if status == 0 {
        Ok(())
    } else {
        Err(format!("OrTTS status {status}: {}", unsafe {
            CStr::from_ptr(ortts_last_error()).to_string_lossy()
        }))
    }
}
/// Structured errors for the task-aware own-model API. Legacy methods retain
/// Result<_, String> for source compatibility with existing SDK callers.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Error {
    Cancelled,
    TaskConsumed,
    InvalidInput(String),
    UnsupportedAbi,
    Native { status: i32, message: String },
    CallbackPanicked,
    InvalidAudio,
}
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Cancelled => write!(f, "OrTTS operation cancelled"),
            Self::TaskConsumed => {
                write!(f, "Cancellation task already consumed; create a fresh Task")
            }
            Self::InvalidInput(message) => write!(f, "{message}"),
            Self::UnsupportedAbi => write!(f, "Unsupported OrTTS ABI"),
            Self::Native { status, message } => write!(f, "OrTTS status {status}: {message}"),
            Self::CallbackPanicked => write!(f, "PCM callback panicked"),
            Self::InvalidAudio => write!(f, "Runtime returned invalid audio"),
        }
    }
}
impl std::error::Error for Error {}
impl Error {
    fn status(status: i32) -> Result<(), Self> {
        if status == 0 {
            return Ok(());
        }
        if status == 4 {
            return Err(Self::Cancelled);
        }
        let message = unsafe {
            let ptr = ortts_last_error();
            if ptr.is_null() {
                "Unknown runtime error".into()
            } else {
                CStr::from_ptr(ptr).to_string_lossy().into_owned()
            }
        };
        Err(Self::Native { status, message })
    }
}
pub mod cancellation;
use cancellation::{Operation, Task};
pub struct Audio {
    pub pcm: Vec<f32>,
    pub sample_rate: i32,
    pub metrics: Metrics,
}
/// Own on a dedicated worker. Deliberately neither Send nor Sync; handles are
/// serialized by this prototype and must never be freed from a PCM callback.
/// ```compile_fail
/// fn require_send<T: Send>() {}
/// require_send::<ortts_engine::Engine>();
/// ```
/// ```compile_fail
/// fn require_sync<T: Sync>() {}
/// require_sync::<ortts_engine::Engine>();
/// ```
pub struct Engine {
    raw: *mut c_void,
    _local: PhantomData<Rc<()>>,
}
impl Engine {
    pub fn new(
        root: &str,
        variant: &str,
        speaker: Option<&str>,
        manifest_sha: &str,
        threads: i32,
        streaming: bool,
    ) -> Result<Self, String> {
        Self::create(
            root,
            variant,
            speaker,
            manifest_sha,
            threads,
            streaming,
            None,
        )
        .map_err(|e| e.to_string())
    }
    /// The ticket is single-use. Share task.cancel_handle() before starting this
    /// call. On legacy libraries cancellation safely discards after load returns.
    pub fn new_cancellable(
        root: &str,
        variant: &str,
        speaker: Option<&str>,
        manifest_sha: &str,
        threads: i32,
        streaming: bool,
        task: &mut Task,
    ) -> Result<Self, Error> {
        let operation = task.begin()?;
        Self::create(
            root,
            variant,
            speaker,
            manifest_sha,
            threads,
            streaming,
            Some(&operation),
        )
    }
    fn create(
        root: &str,
        variant: &str,
        speaker: Option<&str>,
        manifest_sha: &str,
        threads: i32,
        streaming: bool,
        operation: Option<&Operation>,
    ) -> Result<Self, Error> {
        if operation.is_some_and(|op| op.requested()) {
            return Err(Error::Cancelled);
        }
        if unsafe { ortts_abi_version() } != 1 {
            return Err(Error::UnsupportedAbi);
        }
        let root = CString::new(root).map_err(|e| Error::InvalidInput(e.to_string()))?;
        let variant = CString::new(variant).map_err(|e| Error::InvalidInput(e.to_string()))?;
        let speaker = speaker
            .map(CString::new)
            .transpose()
            .map_err(|e| Error::InvalidInput(e.to_string()))?;
        let manifest =
            CString::new(manifest_sha).map_err(|e| Error::InvalidInput(e.to_string()))?;
        let cfg = Config {
            struct_size: std::mem::size_of::<Config>() as u32,
            root: root.as_ptr(),
            variant: variant.as_ptr(),
            speaker: speaker.as_ref().map_or(ptr::null(), |s| s.as_ptr()),
            manifest: manifest.as_ptr(),
            threads,
            streaming: streaming as i32,
        };
        let mut raw = ptr::null_mut();
        let status = unsafe {
            if let Some(create) = operation.and_then(|op| op.api().create) {
                create(&cfg, operation.unwrap().token(), &mut raw)
            } else {
                ortts_engine_create(&cfg, &mut raw)
            }
        };
        if let Err(error) = Error::status(status) {
            if !raw.is_null() {
                unsafe { ortts_engine_free(raw) };
            }
            return Err(error);
        }
        if raw.is_null() {
            return Err(Error::Native {
                status: 2,
                message: "Null engine on success".into(),
            });
        }
        let engine = Self {
            raw,
            _local: PhantomData,
        };
        if let Some(op) = operation {
            op.complete()?;
        } // cancelled load drops engine safely here
        Ok(engine)
    }
    pub fn synthesize(&mut self, text: &str, seed: u64, max_tokens: i32) -> Result<Audio, String> {
        self.run(text, seed, max_tokens, None, ptr::null_mut(), None)
            .map_err(|e| e.to_string())
    }
    /// Cancel this generation only; loaded model/session remain owned by self.
    pub fn synthesize_cancellable(
        &mut self,
        text: &str,
        seed: u64,
        max_tokens: i32,
        task: &mut Task,
    ) -> Result<Audio, Error> {
        let operation = task.begin()?;
        self.run(
            text,
            seed,
            max_tokens,
            None,
            ptr::null_mut(),
            Some(&operation),
        )
    }
    /// Return false from the callback to cancel. PCM is borrowed for the callback
    /// only. Panic is caught at this boundary, converted to cancellation/error.
    pub fn stream<F: FnMut(&[f32], i32) -> bool>(
        &mut self,
        text: &str,
        seed: u64,
        max_tokens: i32,
        sink: F,
    ) -> Result<Audio, String> {
        self.stream_inner(text, seed, max_tokens, sink, None)
            .map_err(|e| e.to_string())
    }
    pub fn stream_cancellable<F: FnMut(&[f32], i32) -> bool>(
        &mut self,
        text: &str,
        seed: u64,
        max_tokens: i32,
        sink: F,
        task: &mut Task,
    ) -> Result<Audio, Error> {
        let operation = task.begin()?;
        self.stream_inner(text, seed, max_tokens, sink, Some(&operation))
    }
    fn stream_inner<F: FnMut(&[f32], i32) -> bool>(
        &mut self,
        text: &str,
        seed: u64,
        max_tokens: i32,
        sink: F,
        operation: Option<&Operation>,
    ) -> Result<Audio, Error> {
        struct State<F> {
            f: F,
            panicked: bool,
        }
        unsafe extern "C" fn invoke<F: FnMut(&[f32], i32) -> bool>(
            p: *mut c_void,
            pcm: *const f32,
            n: usize,
            rate: i32,
        ) -> i32 {
            let s = &mut *(p as *mut State<F>);
            match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                (s.f)(std::slice::from_raw_parts(pcm, n), rate)
            })) {
                Ok(keep) => (!keep) as i32,
                Err(_) => {
                    s.panicked = true;
                    1
                }
            }
        }
        let mut state = State {
            f: sink,
            panicked: false,
        };
        let result = self.run(
            text,
            seed,
            max_tokens,
            Some(invoke::<F>),
            &mut state as *mut _ as *mut c_void,
            operation,
        );
        if state.panicked {
            Err(Error::CallbackPanicked)
        } else {
            result
        }
    }
    fn run(
        &mut self,
        text: &str,
        seed: u64,
        max_tokens: i32,
        cb: Callback,
        user: *mut c_void,
        operation: Option<&Operation>,
    ) -> Result<Audio, Error> {
        if operation.is_some_and(|op| op.requested()) {
            return Err(Error::Cancelled);
        }
        let text = CString::new(text).map_err(|e| Error::InvalidInput(e.to_string()))?;
        let req = Request {
            struct_size: std::mem::size_of::<Request>() as u32,
            text: text.as_ptr(),
            seed,
            max_tokens,
        };
        let mut out = ptr::null_mut();
        let status = unsafe {
            if let Some(synthesize) = operation.and_then(|op| op.api().synthesize) {
                synthesize(
                    self.raw,
                    &req,
                    operation.unwrap().token(),
                    cb,
                    user,
                    &mut out,
                )
            } else {
                ortts_engine_synthesize(self.raw, &req, cb, user, &mut out)
            }
        };
        struct Owned(*mut c_void);
        impl Drop for Owned {
            fn drop(&mut self) {
                unsafe { ortts_audio_free(self.0) }
            }
        }
        let out = Owned(out);
        Error::status(status)?;
        if out.0.is_null() {
            return Err(Error::InvalidAudio);
        }
        let mut metrics = Metrics::default();
        Error::status(unsafe { ortts_audio_metrics(out.0, &mut metrics) })?;
        let (samples, count, sample_rate) = unsafe {
            (
                ortts_audio_samples(out.0),
                ortts_audio_sample_count(out.0),
                ortts_audio_sample_rate(out.0),
            )
        };
        if samples.is_null()
            || count == 0
            || count > (isize::MAX as usize) / std::mem::size_of::<f32>()
            || sample_rate <= 0
        {
            return Err(Error::InvalidAudio);
        }
        let pcm = unsafe { std::slice::from_raw_parts(samples, count).to_vec() };
        if !pcm.iter().all(|v| v.is_finite()) {
            return Err(Error::InvalidAudio);
        }
        if let Some(op) = operation {
            op.complete()?;
        }
        Ok(Audio {
            pcm,
            sample_rate,
            metrics,
        })
    }
}
impl Drop for Engine {
    fn drop(&mut self) {
        unsafe { ortts_engine_free(self.raw) }
    }
}

/// Optional additive multi-model API; use a matched library built with --speech.
pub mod speech;
