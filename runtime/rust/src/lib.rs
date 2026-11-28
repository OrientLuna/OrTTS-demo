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
#[repr(C)]
struct RequestV1_1 {
    struct_size: u32,
    text: *const c_char,
    seed: u64,
    max_tokens: i32,
    speaker_f32: *const c_char,
    speaker_vector: *const f32,
    speaker_dim: usize,
    speed: f32,
}
#[repr(C)]
struct RequestV1_2 {
    struct_size: u32,
    text: *const c_char,
    seed: u64,
    max_tokens: i32,
    speaker_f32: *const c_char,
    speaker_vector: *const f32,
    speaker_dim: usize,
    speed: f32,
    language: *const c_char,
}

/// Optional per-request speaker override for [`Engine`].
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum SpeakerOverride<'a> {
    Path(&'a str),
    Vector(&'a [f32]),
}

/// Extended synthesis options for [`Engine::synthesize_with_options`] and [`Engine::stream_with_options`].
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct SynthesizeOptions<'a> {
    pub speaker: Option<SpeakerOverride<'a>>,
    pub speed: Option<f32>,
    pub language: Option<&'a str>,
}

impl<'a> SynthesizeOptions<'a> {
    pub const fn new() -> Self {
        Self {
            speaker: None,
            speed: None,
            language: None,
        }
    }
    pub const fn with_speaker_path(mut self, path: &'a str) -> Self {
        self.speaker = Some(SpeakerOverride::Path(path));
        self
    }
    pub const fn with_speaker_vector(mut self, vector: &'a [f32]) -> Self {
        self.speaker = Some(SpeakerOverride::Vector(vector));
        self
    }
    pub const fn with_speed(mut self, speed: f32) -> Self {
        self.speed = Some(speed);
        self
    }
    pub const fn with_language(mut self, language: &'a str) -> Self {
        self.language = Some(language);
        self
    }
}

/// Additive feature capability version for `ortts_engine_*` (`0`: legacy v1, `1`: v1.1 speaker/speed, `2`: v1.2 language routing & c0 guard).
pub fn engine_feature_version() -> u32 {
    cancellation::api().feature_version
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

/// Native status code returned when an active operation already holds the handle lock.
pub const STATUS_BUSY: i32 = 3;

/// Per-call lock acquisition policy for inference entry points.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ExecPolicy {
    /// Maximum time in milliseconds to wait for the handle lock (`0..=30000`).
    /// `0` performs a non-blocking try-lock unless `supersede` is `true` (which waits up to 500 ms).
    pub timeout_ms: u32,
    /// When `true`, requests cancellation of any active operation on the same handle and waits for the lock.
    pub supersede: bool,
}

impl ExecPolicy {
    pub const fn new(timeout_ms: u32, supersede: bool) -> Self {
        Self {
            timeout_ms,
            supersede,
        }
    }

    pub const fn is_default(&self) -> bool {
        self.timeout_ms == 0 && !self.supersede
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct RawExecPolicy {
    pub(crate) struct_size: u32,
    pub(crate) timeout_ms: u32,
    pub(crate) supersede: i32,
}

impl From<&ExecPolicy> for RawExecPolicy {
    fn from(policy: &ExecPolicy) -> Self {
        Self {
            struct_size: std::mem::size_of::<Self>() as u32,
            timeout_ms: policy.timeout_ms,
            supersede: i32::from(policy.supersede),
        }
    }
}

pub(crate) fn validate_exec_policy(policy: &ExecPolicy) -> Result<(), Error> {
    if policy.timeout_ms > 30_000 {
        Err(Error::InvalidInput(
            "Execution timeout_ms must be 0..=30000".into(),
        ))
    } else {
        Ok(())
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
pub(crate) fn status_error_with(
    status: i32,
    last_error_fn: unsafe extern "C" fn() -> *const c_char,
) -> Error {
    if status == 4 {
        return Error::Cancelled;
    }
    let message = unsafe {
        let ptr = last_error_fn();
        if ptr.is_null() {
            "Unknown runtime error".into()
        } else {
            CStr::from_ptr(ptr).to_string_lossy().into_owned()
        }
    };
    Error::Native { status, message }
}
pub(crate) fn check_with(
    status: i32,
    last_error_fn: unsafe extern "C" fn() -> *const c_char,
) -> Result<(), Error> {
    if status == 0 {
        Ok(())
    } else {
        Err(status_error_with(status, last_error_fn))
    }
}
impl Error {
    pub const fn is_busy(&self) -> bool {
        matches!(self, Self::Native { status: STATUS_BUSY, .. })
    }
    pub const fn is_cancelled(&self) -> bool {
        matches!(self, Self::Cancelled)
    }
    fn status(status: i32) -> Result<(), Self> {
        check_with(status, ortts_last_error)
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
    /// Hot-switch the engine's active fixed speaker `.f32` file without reloading weights (`None` resets to `voices/female.f32`).
    pub fn set_speaker(&mut self, speaker_f32: Option<&str>) -> Result<(), Error> {
        self.set_speaker_ex(speaker_f32, &ExecPolicy::default())
    }
    /// Hot-switch the engine's active fixed speaker `.f32` file with an explicit [`ExecPolicy`].
    pub fn set_speaker_ex(
        &mut self,
        speaker_f32: Option<&str>,
        policy: &ExecPolicy,
    ) -> Result<(), Error> {
        Self::set_speaker_with_api(self.raw, cancellation::api(), speaker_f32, policy)
    }
    fn set_speaker_with_api(
        raw: *mut c_void,
        api: cancellation::Api,
        speaker_f32: Option<&str>,
        policy: &ExecPolicy,
    ) -> Result<(), Error> {
        validate_exec_policy(policy)?;
        let c_path = match speaker_f32 {
            Some(s) if s.is_empty() => {
                return Err(Error::InvalidInput("Speaker path cannot be empty".into()))
            }
            Some(s) => Some(CString::new(s).map_err(|e| Error::InvalidInput(e.to_string()))?),
            None => None,
        };
        let ptr = c_path.as_ref().map_or(ptr::null(), |s| s.as_ptr());
        let raw_policy = RawExecPolicy::from(policy);
        let status = unsafe {
            if let Some(f) = api.set_speaker_ex {
                f(raw, ptr, &raw_policy)
            } else if policy.is_default() {
                let Some(f) = api.set_speaker else {
                    return Err(Error::UnsupportedAbi);
                };
                f(raw, ptr)
            } else {
                return Err(Error::UnsupportedAbi);
            }
        };
        Error::status(status)
    }
    /// Hot-switch the engine's active speaker embedding from an in-memory F32 slice without reloading weights.
    pub fn set_speaker_vector(&mut self, vector: &[f32]) -> Result<(), Error> {
        self.set_speaker_vector_ex(vector, &ExecPolicy::default())
    }
    /// Hot-switch the engine's active speaker embedding from an in-memory F32 slice with an explicit [`ExecPolicy`].
    pub fn set_speaker_vector_ex(
        &mut self,
        vector: &[f32],
        policy: &ExecPolicy,
    ) -> Result<(), Error> {
        Self::set_speaker_vector_with_api(self.raw, cancellation::api(), vector, policy)
    }
    fn set_speaker_vector_with_api(
        raw: *mut c_void,
        api: cancellation::Api,
        vector: &[f32],
        policy: &ExecPolicy,
    ) -> Result<(), Error> {
        validate_exec_policy(policy)?;
        validate_speaker_slice(vector)?;
        let raw_policy = RawExecPolicy::from(policy);
        let status = unsafe {
            if let Some(f) = api.set_speaker_vector_ex {
                f(raw, vector.as_ptr(), vector.len(), &raw_policy)
            } else if policy.is_default() {
                let Some(f) = api.set_speaker_vector else {
                    return Err(Error::UnsupportedAbi);
                };
                f(raw, vector.as_ptr(), vector.len())
            } else {
                return Err(Error::UnsupportedAbi);
            }
        };
        Error::status(status)
    }
    pub fn synthesize(&mut self, text: &str, seed: u64, max_tokens: i32) -> Result<Audio, String> {
        let policy = ExecPolicy::default();
        self.run(RunArgs {
            text,
            seed,
            max_tokens,
            options: &SynthesizeOptions::default(),
            cb: None,
            user: ptr::null_mut(),
            policy: &policy,
            operation: None,
        })
        .map_err(|e| e.to_string())
    }
    /// Synthesize with per-request options (speaker hot-switch / speed), lock policy, and optional task cancellation.
    pub fn synthesize_with_options(
        &mut self,
        text: &str,
        seed: u64,
        max_tokens: i32,
        options: &SynthesizeOptions<'_>,
        policy: &ExecPolicy,
        task: Option<&mut Task>,
    ) -> Result<Audio, Error> {
        let operation = task.map(Task::begin).transpose()?;
        self.run(RunArgs {
            text,
            seed,
            max_tokens,
            options,
            cb: None,
            user: ptr::null_mut(),
            policy,
            operation: operation.as_ref(),
        })
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
        let policy = ExecPolicy::default();
        let options = SynthesizeOptions::default();
        self.run(RunArgs {
            text,
            seed,
            max_tokens,
            options: &options,
            cb: None,
            user: ptr::null_mut(),
            policy: &policy,
            operation: Some(&operation),
        })
    }
    /// Synthesize with an explicit lock acquisition policy and optional task cancellation.
    pub fn synthesize_ex(
        &mut self,
        text: &str,
        seed: u64,
        max_tokens: i32,
        policy: &ExecPolicy,
        task: Option<&mut Task>,
    ) -> Result<Audio, Error> {
        let operation = task.map(Task::begin).transpose()?;
        let options = SynthesizeOptions::default();
        self.run(RunArgs {
            text,
            seed,
            max_tokens,
            options: &options,
            cb: None,
            user: ptr::null_mut(),
            policy,
            operation: operation.as_ref(),
        })
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
        self.stream_inner(
            text,
            seed,
            max_tokens,
            &SynthesizeOptions::default(),
            sink,
            &ExecPolicy::default(),
            None,
        )
        .map_err(|e| e.to_string())
    }
    /// Stream PCM chunks with per-request options (speaker hot-switch / speed), lock policy, and optional task cancellation.
    pub fn stream_with_options<F: FnMut(&[f32], i32) -> bool>(
        &mut self,
        text: &str,
        seed: u64,
        max_tokens: i32,
        options: &SynthesizeOptions<'_>,
        sink: F,
        policy: &ExecPolicy,
        task: Option<&mut Task>,
    ) -> Result<Audio, Error> {
        let operation = task.map(Task::begin).transpose()?;
        self.stream_inner(
            text,
            seed,
            max_tokens,
            options,
            sink,
            policy,
            operation.as_ref(),
        )
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
        self.stream_inner(
            text,
            seed,
            max_tokens,
            &SynthesizeOptions::default(),
            sink,
            &ExecPolicy::default(),
            Some(&operation),
        )
    }
    /// Stream PCM chunks with an explicit lock acquisition policy and optional task cancellation.
    pub fn stream_ex<F: FnMut(&[f32], i32) -> bool>(
        &mut self,
        text: &str,
        seed: u64,
        max_tokens: i32,
        sink: F,
        policy: &ExecPolicy,
        task: Option<&mut Task>,
    ) -> Result<Audio, Error> {
        let operation = task.map(Task::begin).transpose()?;
        self.stream_inner(
            text,
            seed,
            max_tokens,
            &SynthesizeOptions::default(),
            sink,
            policy,
            operation.as_ref(),
        )
    }
    fn stream_inner<F: FnMut(&[f32], i32) -> bool>(
        &mut self,
        text: &str,
        seed: u64,
        max_tokens: i32,
        options: &SynthesizeOptions<'_>,
        sink: F,
        policy: &ExecPolicy,
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
        let result = self.run(RunArgs {
            text,
            seed,
            max_tokens,
            options,
            cb: Some(invoke::<F>),
            user: &mut state as *mut _ as *mut c_void,
            policy,
            operation,
        });
        if state.panicked {
            Err(Error::CallbackPanicked)
        } else {
            result
        }
    }
    fn run(&mut self, args: RunArgs<'_>) -> Result<Audio, Error> {
        let api = args.operation.map_or_else(cancellation::api, Operation::api);
        struct Owned(*mut c_void);
        impl Drop for Owned {
            fn drop(&mut self) {
                unsafe { ortts_audio_free(self.0) }
            }
        }
        let out = Owned(Self::run_raw(self.raw, api, ortts_engine_synthesize, &args)?);
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
        if let Some(op) = args.operation {
            op.complete()?;
        }
        Ok(Audio {
            pcm,
            sample_rate,
            metrics,
        })
    }
    fn run_raw(
        raw: *mut c_void,
        api: cancellation::Api,
        fallback: SynthesizeFallback,
        args: &RunArgs<'_>,
    ) -> Result<*mut c_void, Error> {
        validate_exec_policy(args.policy)?;
        if !args.policy.is_default() && api.synthesize_ex.is_none() {
            return Err(Error::UnsupportedAbi);
        }
        if args.operation.is_some_and(Operation::requested) {
            return Err(Error::Cancelled);
        }
        if let Some(speed) = args.options.speed {
            validate_speed(speed)?;
            if api.feature_version == 0 && (speed - 1.0).abs() > f32::EPSILON {
                return Err(Error::UnsupportedAbi);
            }
        }
        let speaker_cpath = match args.options.speaker {
            Some(SpeakerOverride::Path(path)) => {
                if path.is_empty() {
                    return Err(Error::InvalidInput("Speaker path cannot be empty".into()));
                }
                if api.feature_version == 0 {
                    return Err(Error::UnsupportedAbi);
                }
                Some(CString::new(path).map_err(|e| Error::InvalidInput(e.to_string()))?)
            }
            Some(SpeakerOverride::Vector(vec)) => {
                validate_speaker_slice(vec)?;
                if api.feature_version == 0 {
                    return Err(Error::UnsupportedAbi);
                }
                None
            }
            None => None,
        };
        let language_cstr = match args.options.language {
            Some(lang) => {
                if api.feature_version < 2 {
                    return Err(Error::UnsupportedAbi);
                }
                Some(CString::new(lang).map_err(|e| Error::InvalidInput(e.to_string()))?)
            }
            None => None,
        };
        let text = CString::new(args.text).map_err(|e| Error::InvalidInput(e.to_string()))?;
        let req_v1 = Request {
            struct_size: std::mem::size_of::<Request>() as u32,
            text: text.as_ptr(),
            seed: args.seed,
            max_tokens: args.max_tokens,
        };
        let (speaker_vector, speaker_dim) = match args.options.speaker {
            Some(SpeakerOverride::Vector(vec)) => (vec.as_ptr(), vec.len()),
            _ => (ptr::null(), 0),
        };
        let speaker_f32 = speaker_cpath.as_ref().map_or(ptr::null(), |s| s.as_ptr());
        let speed = args.options.speed.unwrap_or(0.0);
        let req_v11 = RequestV1_1 {
            struct_size: std::mem::size_of::<RequestV1_1>() as u32,
            text: text.as_ptr(),
            seed: args.seed,
            max_tokens: args.max_tokens,
            speaker_f32,
            speaker_vector,
            speaker_dim,
            speed,
        };
        let req_v12 = RequestV1_2 {
            struct_size: std::mem::size_of::<RequestV1_2>() as u32,
            text: text.as_ptr(),
            seed: args.seed,
            max_tokens: args.max_tokens,
            speaker_f32,
            speaker_vector,
            speaker_dim,
            speed,
            language: language_cstr.as_ref().map_or(ptr::null(), |s| s.as_ptr()),
        };
        let req_ptr: *const Request = if api.feature_version >= 2 {
            (&req_v12 as *const RequestV1_2).cast()
        } else if api.feature_version >= 1 {
            (&req_v11 as *const RequestV1_1).cast()
        } else {
            &req_v1
        };
        let raw_policy = RawExecPolicy::from(args.policy);
        let mut out = ptr::null_mut();
        let status = unsafe {
            if let Some(synthesize_ex) = api.synthesize_ex {
                synthesize_ex(
                    raw,
                    req_ptr,
                    &raw_policy,
                    args.operation.map_or(ptr::null_mut(), Operation::token),
                    args.cb,
                    args.user,
                    &mut out,
                )
            } else if let (Some(op), Some(synthesize)) = (args.operation, api.synthesize) {
                synthesize(raw, req_ptr, op.token(), args.cb, args.user, &mut out)
            } else {
                fallback(raw, req_ptr, args.cb, args.user, &mut out)
            }
        };
        if let Err(err) = Error::status(status) {
            if !out.is_null() {
                unsafe { ortts_audio_free(out) };
            }
            return Err(err);
        }
        if out.is_null() {
            return Err(Error::InvalidAudio);
        }
        Ok(out)
    }
}
pub(crate) fn validate_speed(speed: f32) -> Result<(), Error> {
    if !speed.is_finite() || !(0.5..=2.0).contains(&speed) {
        Err(Error::InvalidInput(
            "Speech speed must be finite within 0.5..=2.0".into(),
        ))
    } else {
        Ok(())
    }
}
fn validate_speaker_slice(vector: &[f32]) -> Result<(), Error> {
    if (vector.len() != 1024 && vector.len() != 2048)
        || !vector.iter().all(|v| v.is_finite())
        || vector.iter().map(|&v| (v as f64) * (v as f64)).sum::<f64>() <= 0.0
    {
        Err(Error::InvalidInput(
            "Speaker vector must be 1024 or 2048 finite non-zero F32 values".into(),
        ))
    } else {
        Ok(())
    }
}
type SynthesizeFallback =
    unsafe extern "C" fn(*mut c_void, *const Request, Callback, *mut c_void, *mut *mut c_void) -> i32;
struct RunArgs<'a> {
    text: &'a str,
    seed: u64,
    max_tokens: i32,
    options: &'a SynthesizeOptions<'a>,
    cb: Callback,
    user: *mut c_void,
    policy: &'a ExecPolicy,
    operation: Option<&'a Operation>,
}
impl Drop for Engine {
    fn drop(&mut self) {
        unsafe { ortts_engine_free(self.raw) }
    }
}

/// Optional additive multi-model API; use a matched library built with --speech.
pub mod speech;
pub use speech::{parallel_inference_version, supports_parallel_tts_asr};

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU32, Ordering};

    #[test]
    fn error_helpers_match_busy_and_cancelled() {
        let busy = Error::Native {
            status: STATUS_BUSY,
            message: "custom message".into(),
        };
        assert!(busy.is_busy());
        assert!(!busy.is_cancelled());
        assert!(Error::Cancelled.is_cancelled());
        assert!(!Error::Cancelled.is_busy());
        assert!(!Error::UnsupportedAbi.is_busy());
    }

    #[test]
    fn exec_policy_validation_and_ex_dispatch() {
        static CALL_KIND: AtomicU32 = AtomicU32::new(0);
        static LAST_TIMEOUT: AtomicU32 = AtomicU32::new(0);
        static LAST_SUPERSEDE: AtomicU32 = AtomicU32::new(9);

        unsafe extern "C" fn mock_fallback(
            _: *mut c_void,
            _: *const Request,
            _: Callback,
            _: *mut c_void,
            _: *mut *mut c_void,
        ) -> i32 {
            CALL_KIND.store(1, Ordering::SeqCst);
            STATUS_BUSY
        }
        unsafe extern "C" fn mock_ex(
            _: *mut c_void,
            _: *const Request,
            policy: *const RawExecPolicy,
            _: *mut c_void,
            _: Callback,
            _: *mut c_void,
            _: *mut *mut c_void,
        ) -> i32 {
            CALL_KIND.store(2, Ordering::SeqCst);
            let p = unsafe { &*policy };
            assert_eq!(p.struct_size as usize, std::mem::size_of::<RawExecPolicy>());
            LAST_TIMEOUT.store(p.timeout_ms, Ordering::SeqCst);
            LAST_SUPERSEDE.store(p.supersede as u32, Ordering::SeqCst);
            STATUS_BUSY
        }

        let invalid = ExecPolicy::new(30_001, false);
        let default_opts = SynthesizeOptions::default();
        assert!(matches!(
            Engine::run_raw(
                ptr::null_mut(),
                cancellation::Api::default(),
                mock_fallback,
                &RunArgs {
                    text: "hi",
                    seed: 1,
                    max_tokens: 8,
                    options: &default_opts,
                    cb: None,
                    user: ptr::null_mut(),
                    policy: &invalid,
                    operation: None,
                },
            ),
            Err(Error::InvalidInput(_))
        ));

        let non_default = ExecPolicy::new(500, true);
        assert!(matches!(
            Engine::run_raw(
                ptr::null_mut(),
                cancellation::Api::default(),
                mock_fallback,
                &RunArgs {
                    text: "hi",
                    seed: 1,
                    max_tokens: 8,
                    options: &default_opts,
                    cb: None,
                    user: ptr::null_mut(),
                    policy: &non_default,
                    operation: None,
                },
            ),
            Err(Error::UnsupportedAbi)
        ));

        let default_policy = ExecPolicy::default();
        let err = Engine::run_raw(
            ptr::null_mut(),
            cancellation::Api::default(),
            mock_fallback,
            &RunArgs {
                text: "hi",
                seed: 1,
                max_tokens: 8,
                options: &default_opts,
                cb: None,
                user: ptr::null_mut(),
                policy: &default_policy,
                operation: None,
            },
        )
        .unwrap_err();
        assert_eq!(CALL_KIND.load(Ordering::SeqCst), 1);
        assert!(err.is_busy());

        let api_with_ex = cancellation::Api {
            synthesize_ex: Some(mock_ex),
            ..cancellation::Api::default()
        };
        let err = Engine::run_raw(
            ptr::null_mut(),
            api_with_ex,
            mock_fallback,
            &RunArgs {
                text: "hi",
                seed: 1,
                max_tokens: 8,
                options: &default_opts,
                cb: None,
                user: ptr::null_mut(),
                policy: &non_default,
                operation: None,
            },
        )
        .unwrap_err();
        assert_eq!(CALL_KIND.load(Ordering::SeqCst), 2);
        assert_eq!(LAST_TIMEOUT.load(Ordering::SeqCst), 500);
        assert_eq!(LAST_SUPERSEDE.load(Ordering::SeqCst), 1);
        assert!(err.is_busy());
    }

    #[test]
    fn speaker_override_and_speed_dispatch_validation() {
        unsafe extern "C" fn mock_v11(
            _: *mut c_void,
            req: *const Request,
            _: *const RawExecPolicy,
            _: *mut c_void,
            _: Callback,
            _: *mut c_void,
            _: *mut *mut c_void,
        ) -> i32 {
            let r = unsafe { &*req.cast::<RequestV1_1>() };
            assert_eq!(r.struct_size as usize, std::mem::size_of::<RequestV1_1>());
            assert!(!r.speaker_vector.is_null());
            assert_eq!(r.speaker_dim, 1024);
            assert!((r.speed - 1.25).abs() < 1e-6);
            STATUS_BUSY
        }
        unsafe extern "C" fn mock_unused(
            _: *mut c_void,
            _: *const Request,
            _: Callback,
            _: *mut c_void,
            _: *mut *mut c_void,
        ) -> i32 {
            0
        }
        let legacy_api = cancellation::Api::default();
        let vec1024 = vec![0.1_f32; 1024];
        let opts_vec = SynthesizeOptions::new().with_speaker_vector(&vec1024);
        assert!(matches!(
            Engine::run_raw(
                ptr::null_mut(),
                legacy_api,
                mock_unused,
                &RunArgs {
                    text: "hi",
                    seed: 1,
                    max_tokens: 8,
                    options: &opts_vec,
                    cb: None,
                    user: ptr::null_mut(),
                    policy: &ExecPolicy::default(),
                    operation: None,
                }
            ),
            Err(Error::UnsupportedAbi)
        ));
        let bad_speed = SynthesizeOptions::new().with_speed(2.5);
        assert!(matches!(
            Engine::run_raw(
                ptr::null_mut(),
                legacy_api,
                mock_unused,
                &RunArgs {
                    text: "hi",
                    seed: 1,
                    max_tokens: 8,
                    options: &bad_speed,
                    cb: None,
                    user: ptr::null_mut(),
                    policy: &ExecPolicy::default(),
                    operation: None,
                }
            ),
            Err(Error::InvalidInput(_))
        ));

        let v11_api = cancellation::Api {
            feature_version: 1,
            synthesize_ex: Some(mock_v11),
            ..cancellation::Api::default()
        };
        let opts = SynthesizeOptions::new()
            .with_speaker_vector(&vec1024)
            .with_speed(1.25);
        let err = Engine::run_raw(
            ptr::null_mut(),
            v11_api,
            mock_unused,
            &RunArgs {
                text: "hi",
                seed: 1,
                max_tokens: 8,
                options: &opts,
                cb: None,
                user: ptr::null_mut(),
                policy: &ExecPolicy::default(),
                operation: None,
            },
        )
        .unwrap_err();
        assert!(err.is_busy());

        // v1.1 runtime must reject explicit v1.2 language override with UnsupportedAbi
        let opts_lang = SynthesizeOptions::new().with_language("English");
        assert!(matches!(
            Engine::run_raw(
                ptr::null_mut(),
                v11_api,
                mock_unused,
                &RunArgs {
                    text: "hi",
                    seed: 1,
                    max_tokens: 8,
                    options: &opts_lang,
                    cb: None,
                    user: ptr::null_mut(),
                    policy: &ExecPolicy::default(),
                    operation: None,
                }
            ),
            Err(Error::UnsupportedAbi)
        ));

        unsafe extern "C" fn mock_v12(
            _: *mut c_void,
            req: *const Request,
            _: *const RawExecPolicy,
            _: *mut c_void,
            _: Callback,
            _: *mut c_void,
            _: *mut *mut c_void,
        ) -> i32 {
            let r = unsafe { &*req.cast::<RequestV1_2>() };
            assert_eq!(r.struct_size as usize, std::mem::size_of::<RequestV1_2>());
            assert!(!r.language.is_null());
            let lang = unsafe { CStr::from_ptr(r.language) }.to_str().unwrap();
            assert_eq!(lang, "English");
            STATUS_BUSY
        }
        let v12_api = cancellation::Api {
            feature_version: 2,
            synthesize_ex: Some(mock_v12),
            ..cancellation::Api::default()
        };
        let err = Engine::run_raw(
            ptr::null_mut(),
            v12_api,
            mock_unused,
            &RunArgs {
                text: "hi",
                seed: 1,
                max_tokens: 8,
                options: &opts_lang,
                cb: None,
                user: ptr::null_mut(),
                policy: &ExecPolicy::default(),
                operation: None,
            },
        )
        .unwrap_err();
        assert!(err.is_busy());
    }
}
