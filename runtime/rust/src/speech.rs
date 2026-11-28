//! Additive speech ABI. Matched --speech library required. No playback/downloads.
//! Handles stay on a worker (neither Send nor Sync). Asr is buffered-final;
//! `streaming::Stream` provides incremental ASR (`moonshine_asr`, and optional
//! `streaming_paraformer` / `zipformer_bilingual` with silence endpointing).
pub mod streaming;
pub mod cache;
pub use crate::ExecPolicy;
use crate::{
    cancellation::{
        self, resolve_symbol, CancelMode, Capabilities, NativeImage, Operation, Task,
    },
    check, check_with, cstring, validate_exec_policy, Error, Metrics,
    RawExecPolicy,
};
use std::{
    ffi::{c_char, c_void, CStr, CString},
    marker::PhantomData,
    ptr,
    rc::Rc,
    sync::OnceLock,
};
#[repr(C)]
pub(crate) struct Pair {
    key: *const c_char,
    value: *const c_char,
}
#[repr(C)]
pub(crate) struct RawConfig {
    pub(crate) size: u32,
    pub(crate) family: *const c_char,
    pub(crate) path: *const c_char,
    pub(crate) threads: i32,
    pub(crate) streaming: i32,
    pub(crate) options: *const Pair,
    pub(crate) count: usize,
    pub(crate) library: *const c_char,
    pub(crate) data: *const c_char,
    pub(crate) limit: usize,
}
#[repr(C)]
pub(crate) struct RawRequest {
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
#[repr(C)]
struct RawRequestV1_1 {
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
    speed: f32,
}
pub(crate) type Callback =
    Option<unsafe extern "C" fn(*mut c_void, *const f32, usize, i32, i32) -> i32>;
type AbiVersionFn = unsafe extern "C" fn() -> u32;
type LastErrorFn = unsafe extern "C" fn() -> *const c_char;
type CatalogJsonFn = unsafe extern "C" fn() -> *const c_char;
type TtsCreateFn = unsafe extern "C" fn(*const RawConfig, *mut *mut c_void) -> i32;
type TtsCreateCancellableFn =
    unsafe extern "C" fn(*const RawConfig, *mut c_void, *mut *mut c_void) -> i32;
type TtsSynthesizeFn = unsafe extern "C" fn(
    *mut c_void,
    *const RawRequest,
    Callback,
    *mut c_void,
    *mut *mut c_void,
) -> i32;
type TtsSynthesizeCancellableFn = unsafe extern "C" fn(
    *mut c_void,
    *const RawRequest,
    *mut c_void,
    Callback,
    *mut c_void,
    *mut *mut c_void,
) -> i32;
type TtsSynthesizeExFn = unsafe extern "C" fn(
    *mut c_void,
    *const RawRequest,
    *const RawExecPolicy,
    *mut c_void,
    Callback,
    *mut c_void,
    *mut *mut c_void,
) -> i32;
type HandleVoidFn = unsafe extern "C" fn(*mut c_void);
type AudioSamplesFn = unsafe extern "C" fn(*const c_void) -> *const f32;
type AudioFramesFn = unsafe extern "C" fn(*const c_void) -> usize;
type AudioIntFn = unsafe extern "C" fn(*const c_void) -> i32;
type AudioMetricsFn = unsafe extern "C" fn(*const c_void, *mut Metrics) -> i32;
type AsrCreateFn = unsafe extern "C" fn(*const RawConfig, *mut *mut c_void) -> i32;
type AsrCreateCancellableFn =
    unsafe extern "C" fn(*const RawConfig, *mut c_void, *mut *mut c_void) -> i32;
type AsrRunFn =
    unsafe extern "C" fn(*mut c_void, *const f32, usize, *const c_char, *mut *mut c_void) -> i32;
type AsrRunCancellableFn = unsafe extern "C" fn(
    *mut c_void,
    *const f32,
    usize,
    *const c_char,
    *mut c_void,
    *mut *mut c_void,
) -> i32;
type AsrRunExFn = unsafe extern "C" fn(
    *mut c_void,
    *const f32,
    usize,
    *const c_char,
    *const RawExecPolicy,
    *mut c_void,
    *mut *mut c_void,
) -> i32;
type AsrAcceptFn = unsafe extern "C" fn(*mut c_void, *const f32, usize) -> i32;
type AsrFinishFn = unsafe extern "C" fn(*mut c_void, *const c_char, *mut *mut c_void) -> i32;
type AsrFinishCancellableFn =
    unsafe extern "C" fn(*mut c_void, *const c_char, *mut c_void, *mut *mut c_void) -> i32;
type AsrFinishExFn = unsafe extern "C" fn(
    *mut c_void,
    *const c_char,
    *const RawExecPolicy,
    *mut c_void,
    *mut *mut c_void,
) -> i32;
type AsrResetFn = unsafe extern "C" fn(*mut c_void) -> i32;
type TranscriptStrFn = unsafe extern "C" fn(*const c_void) -> *const c_char;
type TranscriptMsFn = unsafe extern "C" fn(*const c_void) -> f64;

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

#[derive(Clone, Copy)]
pub(crate) struct SpeechApi {
    pub(crate) speech_abi_version: AbiVersionFn,
    pub(crate) speech_catalog_json: CatalogJsonFn,
    pub(crate) last_error: LastErrorFn,
    pub(crate) tts_create: TtsCreateFn,
    pub(crate) tts_create_cancellable: Option<TtsCreateCancellableFn>,
    pub(crate) tts_synthesize: TtsSynthesizeFn,
    pub(crate) tts_synthesize_cancellable: Option<TtsSynthesizeCancellableFn>,
    pub(crate) tts_synthesize_ex: Option<TtsSynthesizeExFn>,
    pub(crate) tts_cancel: Option<HandleVoidFn>,
    pub(crate) tts_free: HandleVoidFn,
    pub(crate) speech_audio_samples: AudioSamplesFn,
    pub(crate) speech_audio_frames: AudioFramesFn,
    pub(crate) speech_audio_sample_rate: AudioIntFn,
    pub(crate) speech_audio_channels: AudioIntFn,
    pub(crate) speech_audio_metrics: AudioMetricsFn,
    pub(crate) speech_audio_free: HandleVoidFn,
    pub(crate) asr_create: AsrCreateFn,
    pub(crate) asr_create_cancellable: Option<AsrCreateCancellableFn>,
    pub(crate) asr_run: AsrRunFn,
    pub(crate) asr_run_cancellable: Option<AsrRunCancellableFn>,
    pub(crate) asr_run_ex: Option<AsrRunExFn>,
    pub(crate) asr_accept: AsrAcceptFn,
    pub(crate) asr_finish: AsrFinishFn,
    pub(crate) asr_finish_cancellable: Option<AsrFinishCancellableFn>,
    pub(crate) asr_finish_ex: Option<AsrFinishExFn>,
    pub(crate) asr_reset: AsrResetFn,
    pub(crate) asr_cancel: Option<HandleVoidFn>,
    pub(crate) asr_free: HandleVoidFn,
    pub(crate) transcript_text: TranscriptStrFn,
    pub(crate) transcript_language: TranscriptStrFn,
    pub(crate) transcript_api_ms: TranscriptMsFn,
    pub(crate) transcript_free: HandleVoidFn,
    pub(crate) parallel_version: Option<AbiVersionFn>,
    pub(crate) cooperative_version: Option<AbiVersionFn>,
    pub(crate) cancel_api: cancellation::Api,
}

impl SpeechApi {
    fn linked_base(cancel_api: cancellation::Api) -> Self {
        Self {
            speech_abi_version: ortts_speech_abi_version,
            speech_catalog_json: ortts_speech_catalog_json,
            last_error: crate::ortts_last_error,
            tts_create: ortts_tts_create,
            tts_create_cancellable: None,
            tts_synthesize: ortts_tts_synthesize,
            tts_synthesize_cancellable: None,
            tts_synthesize_ex: None,
            tts_cancel: None,
            tts_free: ortts_tts_free,
            speech_audio_samples: ortts_speech_audio_samples,
            speech_audio_frames: ortts_speech_audio_frames,
            speech_audio_sample_rate: ortts_speech_audio_sample_rate,
            speech_audio_channels: ortts_speech_audio_channels,
            speech_audio_metrics: ortts_speech_audio_metrics,
            speech_audio_free: ortts_speech_audio_free,
            asr_create: ortts_asr_create,
            asr_create_cancellable: None,
            asr_run: ortts_asr_run,
            asr_run_cancellable: None,
            asr_run_ex: None,
            asr_accept: ortts_asr_accept,
            asr_finish: ortts_asr_finish,
            asr_finish_cancellable: None,
            asr_finish_ex: None,
            asr_reset: ortts_asr_reset,
            asr_cancel: None,
            asr_free: ortts_asr_free,
            transcript_text: ortts_transcript_text,
            transcript_language: ortts_transcript_language,
            transcript_api_ms: ortts_transcript_api_ms,
            transcript_free: ortts_transcript_free,
            parallel_version: None,
            cooperative_version: None,
            cancel_api,
        }
    }

    fn discover() -> Self {
        let cancel_api = cancellation::api();
        let mut api = Self::linked_base(cancel_api);
        let Some(image) = NativeImage::open_linked() else {
            return api;
        };
        unsafe {
            api.parallel_version =
                resolve_symbol!(image, "ortts_parallel_inference_version", AbiVersionFn);
            api.cooperative_version = resolve_symbol!(
                image,
                "ortts_speech_cooperative_cancel_version",
                AbiVersionFn
            );
            api.tts_synthesize_ex =
                resolve_symbol!(image, "ortts_tts_synthesize_ex", TtsSynthesizeExFn);
            api.tts_cancel = resolve_symbol!(image, "ortts_tts_cancel", HandleVoidFn);
            api.asr_run_ex = resolve_symbol!(image, "ortts_asr_run_ex", AsrRunExFn);
            api.asr_finish_ex = resolve_symbol!(image, "ortts_asr_finish_ex", AsrFinishExFn);
            api.asr_cancel = resolve_symbol!(image, "ortts_asr_cancel", HandleVoidFn);
            if cancel_api.has_tokens() {
                api.tts_create_cancellable = resolve_symbol!(
                    image,
                    "ortts_tts_create_cancellable",
                    TtsCreateCancellableFn
                );
                api.tts_synthesize_cancellable = resolve_symbol!(
                    image,
                    "ortts_tts_synthesize_cancellable",
                    TtsSynthesizeCancellableFn
                );
                api.asr_create_cancellable = resolve_symbol!(
                    image,
                    "ortts_asr_create_cancellable",
                    AsrCreateCancellableFn
                );
                api.asr_run_cancellable =
                    resolve_symbol!(image, "ortts_asr_run_cancellable", AsrRunCancellableFn);
                api.asr_finish_cancellable = resolve_symbol!(
                    image,
                    "ortts_asr_finish_cancellable",
                    AsrFinishCancellableFn
                );
            }
        }
        api
    }

    pub(crate) fn available(self) -> bool {
        unsafe { (self.speech_abi_version)() == 1 }
    }

    pub(crate) fn parallel_inference_version(self) -> u32 {
        self.parallel_version.map_or(0, |f| unsafe { f() })
    }

    pub(crate) fn capabilities(self) -> Capabilities {
        if !self.available() || !self.cancel_api.has_tokens() {
            return Capabilities {
                loading: CancelMode::DiscardAfterReturn,
                synthesis: CancelMode::DiscardAfterReturn,
            };
        }
        let cooperative = self.cooperative_version.is_some_and(|v| unsafe { v() } >= 1);
        let mode = if cooperative {
            CancelMode::Cooperative
        } else {
            CancelMode::Boundary
        };
        let has_loading =
            self.tts_create_cancellable.is_some() && self.asr_create_cancellable.is_some();
        let has_synthesis = self.tts_synthesize_cancellable.is_some()
            && self.asr_run_cancellable.is_some()
            && self.asr_finish_cancellable.is_some();
        Capabilities {
            loading: if has_loading {
                mode
            } else {
                CancelMode::DiscardAfterReturn
            },
            synthesis: if has_synthesis {
                mode
            } else {
                CancelMode::DiscardAfterReturn
            },
        }
    }
}

pub(crate) fn speech_api() -> SpeechApi {
    static API: OnceLock<SpeechApi> = OnceLock::new();
    *API.get_or_init(SpeechApi::discover)
}

fn cp(s: &Option<CString>) -> *const c_char {
    s.as_ref().map_or(ptr::null(), |s| s.as_ptr())
}
fn cstring_err(s: &str) -> Result<CString, Error> {
    CString::new(s).map_err(|_| Error::InvalidInput("Interior NUL in input".into()))
}
type OptionPairs = (Vec<(CString, CString)>, Vec<Pair>);
fn pairs(v: &[(&str, &str)]) -> Result<OptionPairs, String> {
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
fn pairs_err(v: &[(&str, &str)]) -> Result<OptionPairs, Error> {
    pairs(v).map_err(Error::InvalidInput)
}
pub fn available() -> bool {
    speech_api().available()
}
pub fn catalog() -> String {
    unsafe {
        let ptr = (speech_api().speech_catalog_json)();
        if ptr.is_null() {
            "{}".into()
        } else {
            CStr::from_ptr(ptr).to_string_lossy().into_owned()
        }
    }
}
/// Reports the runtime parallel inference ABI capability (`0`: absent/disabled,
/// `2`: per-handle concurrency without process-wide `setenv` mutation).
pub fn parallel_inference_version() -> u32 {
    speech_api().parallel_inference_version()
}
/// Returns `true` when at least one TTS handle and one ASR handle can run concurrently
/// on separate workers without hitting the legacy process-wide gate.
pub fn supports_parallel_tts_asr() -> bool {
    parallel_inference_version() >= 2
}
/// Reports speech-domain load and inference cancellation capabilities.
pub fn cancellation_capabilities() -> Capabilities {
    speech_api().capabilities()
}
/// Parses `catalog()` and returns enabled incremental streaming ASR families.
pub fn streaming_asr_families() -> Vec<String> {
    streaming::families()
}

/// Self-describing per-family TTS capabilities returned by [`runtime_capabilities`].
#[derive(Clone, Debug, PartialEq, Eq, Default)]
pub struct TtsCapabilities {
    pub family: String,
    pub api: String,
    pub streaming: bool,
    pub per_request_speaker: bool,
    pub speaker_vector_clone: bool,
    pub reference_audio_clone: bool,
    pub speed_control: bool,
    pub sample_rate: u32,
    pub channels: u32,
    pub languages: Vec<String>,
}

/// Self-describing per-family ASR capabilities returned by [`runtime_capabilities`].
#[derive(Clone, Debug, PartialEq, Eq, Default)]
pub struct AsrCapabilities {
    pub family: String,
    pub api: String,
    pub streaming: bool,
    pub true_streaming: bool,
    pub streaming_kind: String,
    pub languages: Vec<String>,
    pub sample_rate: u32,
    pub recommended_bilingual: bool,
}

/// Structured runtime capability manifest parsed from [`catalog()`].
#[derive(Clone, Debug, PartialEq, Eq, Default)]
pub struct RuntimeCapabilities {
    pub abi_version: u32,
    pub engine_feature_version: u32,
    pub recommended_bilingual_asr: Option<String>,
    pub tts: Vec<TtsCapabilities>,
    pub asr: Vec<AsrCapabilities>,
}

/// Queries [`catalog()`] and parses structured runtime capabilities without extra dependencies.
pub fn runtime_capabilities() -> RuntimeCapabilities {
    parse_runtime_capabilities(&catalog())
}

/// Parses a `ortts_speech_catalog_json()` payload into [`RuntimeCapabilities`].
pub fn parse_runtime_capabilities(catalog_json: &str) -> RuntimeCapabilities {
    enum JVal {
        Null,
        Bool(bool),
        Num(i64),
        Str(String),
        Arr(Vec<JVal>),
        Obj(Vec<(String, JVal)>),
    }
    impl JVal {
        fn get(&self, key: &str) -> Option<&JVal> {
            match self {
                Self::Obj(entries) => entries.iter().find(|(k, _)| k == key).map(|(_, v)| v),
                _ => None,
            }
        }
        fn as_str(&self) -> Option<&str> {
            match self {
                Self::Str(s) => Some(s.as_str()),
                _ => None,
            }
        }
        fn as_bool(&self) -> Option<bool> {
            match self {
                Self::Bool(b) => Some(*b),
                _ => None,
            }
        }
        fn as_u32(&self) -> Option<u32> {
            match self {
                Self::Num(n) if *n >= 0 => u32::try_from(*n).ok(),
                _ => None,
            }
        }
        fn as_str_vec(&self) -> Vec<String> {
            match self {
                Self::Arr(items) => items.iter().filter_map(|v| v.as_str().map(str::to_owned)).collect(),
                _ => Vec::new(),
            }
        }
    }
    fn ws(b: &[u8], i: &mut usize) {
        while b.get(*i).is_some_and(u8::is_ascii_whitespace) {
            *i += 1;
        }
    }
    fn parse_str(b: &[u8], i: &mut usize) -> Option<String> {
        ws(b, i);
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
                            let h = std::str::from_utf8(b.get(*i..*i + 4)?).ok()?;
                            let code = u32::from_str_radix(h, 16).ok()?;
                            *i += 4;
                            out.push(char::from_u32(code).unwrap_or(char::REPLACEMENT_CHARACTER));
                        }
                        _ => return None,
                    }
                }
                _ => {
                    let start = *i - 1;
                    while *i < b.len() && b[*i] != b'"' && b[*i] != b'\\' {
                        *i += 1;
                    }
                    out.push_str(std::str::from_utf8(&b[start..*i]).ok()?);
                }
            }
        }
        None
    }
    fn parse_val(b: &[u8], i: &mut usize) -> Option<JVal> {
        ws(b, i);
        match *b.get(*i)? {
            b'"' => parse_str(b, i).map(JVal::Str),
            b'{' => {
                *i += 1;
                ws(b, i);
                let mut entries = Vec::new();
                if b.get(*i) == Some(&b'}') {
                    *i += 1;
                    return Some(JVal::Obj(entries));
                }
                loop {
                    let k = parse_str(b, i)?;
                    ws(b, i);
                    if *b.get(*i)? != b':' {
                        return None;
                    }
                    *i += 1;
                    entries.push((k, parse_val(b, i)?));
                    ws(b, i);
                    match *b.get(*i)? {
                        b',' => *i += 1,
                        b'}' => {
                            *i += 1;
                            return Some(JVal::Obj(entries));
                        }
                        _ => return None,
                    }
                }
            }
            b'[' => {
                *i += 1;
                ws(b, i);
                let mut items = Vec::new();
                if b.get(*i) == Some(&b']') {
                    *i += 1;
                    return Some(JVal::Arr(items));
                }
                loop {
                    items.push(parse_val(b, i)?);
                    ws(b, i);
                    match *b.get(*i)? {
                        b',' => *i += 1,
                        b']' => {
                            *i += 1;
                            return Some(JVal::Arr(items));
                        }
                        _ => return None,
                    }
                }
            }
            _ => {
                let start = *i;
                while b
                    .get(*i)
                    .is_some_and(|c| c.is_ascii_alphanumeric() || matches!(c, b'-' | b'+' | b'.'))
                {
                    *i += 1;
                }
                let tok = std::str::from_utf8(b.get(start..*i)?).ok()?;
                match tok {
                    "true" => Some(JVal::Bool(true)),
                    "false" => Some(JVal::Bool(false)),
                    "null" => Some(JVal::Null),
                    _ => tok
                        .parse::<i64>()
                        .ok()
                        .map(JVal::Num)
                        .or(Some(JVal::Null)),
                }
            }
        }
    }

    let mut idx = 0;
    let Some(root) = parse_val(catalog_json.as_bytes(), &mut idx) else {
        return RuntimeCapabilities::default();
    };
    let mut caps = RuntimeCapabilities {
        abi_version: root.get("abi_version").and_then(JVal::as_u32).unwrap_or(1),
        engine_feature_version: root
            .get("engine_feature_version")
            .and_then(JVal::as_u32)
            .unwrap_or(0),
        recommended_bilingual_asr: root
            .get("recommended_bilingual_asr")
            .and_then(JVal::as_str)
            .map(str::to_owned),
        tts: Vec::new(),
        asr: Vec::new(),
    };
    if let Some(JVal::Obj(entries)) = root.get("capabilities").and_then(|c| c.get("tts")) {
        for (fam, obj) in entries {
            caps.tts.push(TtsCapabilities {
                family: fam.clone(),
                api: obj.get("api").and_then(JVal::as_str).unwrap_or("").to_owned(),
                streaming: obj.get("streaming").and_then(JVal::as_bool).unwrap_or(false),
                per_request_speaker: obj
                    .get("per_request_speaker")
                    .and_then(JVal::as_bool)
                    .unwrap_or(false),
                speaker_vector_clone: obj
                    .get("speaker_vector_clone")
                    .and_then(JVal::as_bool)
                    .unwrap_or(false),
                reference_audio_clone: obj
                    .get("reference_audio_clone")
                    .and_then(JVal::as_bool)
                    .unwrap_or(false),
                speed_control: obj
                    .get("speed_control")
                    .and_then(JVal::as_bool)
                    .unwrap_or(false),
                sample_rate: obj.get("sample_rate").and_then(JVal::as_u32).unwrap_or(0),
                channels: obj.get("channels").and_then(JVal::as_u32).unwrap_or(1),
                languages: obj
                    .get("languages")
                    .map(JVal::as_str_vec)
                    .unwrap_or_default(),
            });
        }
    }
    if let Some(JVal::Obj(entries)) = root.get("capabilities").and_then(|c| c.get("asr")) {
        for (fam, obj) in entries {
            caps.asr.push(AsrCapabilities {
                family: fam.clone(),
                api: obj.get("api").and_then(JVal::as_str).unwrap_or("").to_owned(),
                streaming: obj.get("streaming").and_then(JVal::as_bool).unwrap_or(false),
                true_streaming: obj
                    .get("true_streaming")
                    .and_then(JVal::as_bool)
                    .unwrap_or(false),
                streaming_kind: obj
                    .get("streaming_kind")
                    .and_then(JVal::as_str)
                    .unwrap_or("")
                    .to_owned(),
                languages: obj
                    .get("languages")
                    .map(JVal::as_str_vec)
                    .unwrap_or_default(),
                sample_rate: obj.get("sample_rate").and_then(JVal::as_u32).unwrap_or(16000),
                recommended_bilingual: obj
                    .get("recommended_bilingual")
                    .and_then(JVal::as_bool)
                    .unwrap_or(false),
            });
        }
    }
    caps
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
pub(crate) struct PreparedConfig {
    _family: CString,
    _path: CString,
    _library: Option<CString>,
    _data: Option<CString>,
    _options: Vec<(CString, CString)>,
    _raw_options: Vec<Pair>,
    pub(crate) raw: RawConfig,
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
    /// Constructs a configuration suitable for `streaming::Stream` (`moonshine_asr`,
    /// `streaming_paraformer`, `zipformer_bilingual`) with offline-only fields cleared.
    pub const fn new_streaming_asr(family: &'a str, model_path: &'a str, threads: i32) -> Self {
        Self {
            family,
            model_path,
            threads,
            streaming: true,
            session_options: &[],
            espeak_library: None,
            espeak_data: None,
            max_input_frames: 0,
        }
    }
    pub(crate) fn prepare(&self) -> Result<PreparedConfig, Error> {
        let family = cstring_err(self.family)?;
        let path = cstring_err(self.model_path)?;
        let library = self.espeak_library.map(cstring_err).transpose()?;
        let data = self.espeak_data.map(cstring_err).transpose()?;
        let (owned_options, raw_options) = pairs_err(self.session_options)?;
        let raw = RawConfig {
            size: std::mem::size_of::<RawConfig>() as u32,
            family: family.as_ptr(),
            path: path.as_ptr(),
            threads: self.threads,
            streaming: self.streaming as i32,
            options: raw_options.as_ptr(),
            count: raw_options.len(),
            library: cp(&library),
            data: cp(&data),
            limit: self.max_input_frames,
        };
        Ok(PreparedConfig {
            _family: family,
            _path: path,
            _library: library,
            _data: data,
            _options: owned_options,
            _raw_options: raw_options,
            raw,
        })
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
    pub speed: Option<f32>,
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
            speed: None,
        }
    }
    pub const fn with_speed(mut self, speed: f32) -> Self {
        self.speed = Some(speed);
        self
    }
}
pub struct Audio {
    pub pcm: Vec<f32>,
    pub sample_rate: i32,
    pub channels: i32,
    pub metrics: Metrics,
}
pub(crate) struct TtsRunError {
    pub(crate) error: Error,
    pub(crate) entered_ffi: bool,
    pub(crate) stopped_by_sink: bool,
}
pub struct Tts {
    raw: *mut c_void,
    api: SpeechApi,
    _local: PhantomData<Rc<()>>,
}
impl Tts {
    pub fn new(c: &Config<'_>) -> Result<Self, String> {
        Self::open_with_op(speech_api(), c, None).map_err(|e| e.to_string())
    }
    /// Load a TTS handle with a single-use cancellation task.
    pub fn new_cancellable(c: &Config<'_>, task: &mut Task) -> Result<Self, Error> {
        let operation = task.begin()?;
        let engine = Self::open_with_op(speech_api(), c, Some(&operation))?;
        operation.complete()?;
        Ok(engine)
    }
    pub(crate) fn open_with_op(
        api: SpeechApi,
        c: &Config<'_>,
        operation: Option<&Operation>,
    ) -> Result<Self, Error> {
        if operation.is_some_and(Operation::requested) {
            return Err(Error::Cancelled);
        }
        if !api.available() {
            return Err(Error::UnsupportedAbi);
        }
        let prepared = c.prepare()?;
        if operation.is_some_and(Operation::requested) {
            return Err(Error::Cancelled);
        }
        let mut out = ptr::null_mut();
        let status = unsafe {
            if let (Some(op), Some(create)) = (operation, api.tts_create_cancellable) {
                create(&prepared.raw, op.token(), &mut out)
            } else {
                (api.tts_create)(&prepared.raw, &mut out)
            }
        };
        if let Err(err) = check_with(status, api.last_error) {
            if !out.is_null() {
                unsafe { (api.tts_free)(out) };
            }
            return Err(err);
        }
        if out.is_null() {
            return Err(Error::Native {
                status: 2,
                message: "Null TTS handle on success".into(),
            });
        }
        if operation.is_some_and(Operation::requested) {
            unsafe { (api.tts_free)(out) };
            return Err(Error::Cancelled);
        }
        Ok(Self {
            raw: out,
            api,
            _local: PhantomData,
        })
    }
    pub fn synthesize(&mut self, r: &Request<'_>) -> Result<Audio, String> {
        self.run_no_sink(r, &ExecPolicy::default(), None)
            .map_err(|e| e.error.to_string())
    }
    /// Synthesize with a single-use cancellation task while preserving loaded weights.
    pub fn synthesize_cancellable(
        &mut self,
        r: &Request<'_>,
        task: &mut Task,
    ) -> Result<Audio, Error> {
        let operation = task.begin()?;
        self.run_no_sink(r, &ExecPolicy::default(), Some(operation))
            .map_err(|e| e.error)
    }
    /// Synthesize with an execution lock policy and optional cancellation task.
    pub fn synthesize_ex(
        &mut self,
        r: &Request<'_>,
        policy: &ExecPolicy,
        task: Option<&mut Task>,
    ) -> Result<Audio, Error> {
        let operation = task.map(Task::begin).transpose()?;
        self.run_no_sink(r, policy, operation).map_err(|e| e.error)
    }
    /// Chunk PCM is borrowed and interleaved. Return false to cancel; panic is contained.
    pub fn stream<F: FnMut(&[f32], i32, i32) -> bool>(
        &mut self,
        r: &Request<'_>,
        sink: F,
    ) -> Result<Audio, String> {
        self.run_with_sink(r, sink, &ExecPolicy::default(), None)
            .map_err(|e| e.error.to_string())
    }
    /// Stream synthesized chunks with a single-use cancellation task while preserving weights.
    pub fn stream_cancellable<F: FnMut(&[f32], i32, i32) -> bool>(
        &mut self,
        r: &Request<'_>,
        sink: F,
        task: &mut Task,
    ) -> Result<Audio, Error> {
        let operation = task.begin()?;
        self.run_with_sink(r, sink, &ExecPolicy::default(), Some(operation))
            .map_err(|e| e.error)
    }
    /// Stream synthesized chunks with an execution lock policy and optional cancellation task.
    pub fn stream_ex<F: FnMut(&[f32], i32, i32) -> bool>(
        &mut self,
        r: &Request<'_>,
        sink: F,
        policy: &ExecPolicy,
        task: Option<&mut Task>,
    ) -> Result<Audio, Error> {
        let operation = task.map(Task::begin).transpose()?;
        self.run_with_sink(r, sink, policy, operation)
            .map_err(|e| e.error)
    }
    /// Request cooperative cancellation of an in-flight synthesis on this handle.
    pub fn cancel(&self) {
        if let Some(cancel_fn) = self.api.tts_cancel {
            unsafe { cancel_fn(self.raw) }
        }
    }
    pub(crate) fn run_no_sink(
        &mut self,
        r: &Request<'_>,
        policy: &ExecPolicy,
        operation: Option<Operation>,
    ) -> Result<Audio, TtsRunError> {
        self.run_dispatch(r, None, ptr::null_mut(), policy, operation)
    }
    pub(crate) fn run_with_sink<F: FnMut(&[f32], i32, i32) -> bool>(
        &mut self,
        r: &Request<'_>,
        sink: F,
        policy: &ExecPolicy,
        operation: Option<Operation>,
    ) -> Result<Audio, TtsRunError> {
        struct State<F> {
            f: F,
            panicked: bool,
            stopped_by_sink: bool,
        }
        unsafe extern "C" fn invoke<F: FnMut(&[f32], i32, i32) -> bool>(
            u: *mut c_void,
            p: *const f32,
            n: usize,
            rate: i32,
            ch: i32,
        ) -> i32 {
            let s = &mut *(u as *mut State<F>);
            if !(1..=2).contains(&ch) || n.checked_mul(ch as usize).is_none() {
                return 1;
            }
            match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                (s.f)(std::slice::from_raw_parts(p, n * ch as usize), rate, ch)
            })) {
                Ok(true) => 0,
                Ok(false) => {
                    s.stopped_by_sink = true;
                    1
                }
                Err(_) => {
                    s.panicked = true;
                    1
                }
            }
        }
        let mut s = State {
            f: sink,
            panicked: false,
            stopped_by_sink: false,
        };
        let result = self.run_dispatch(
            r,
            Some(invoke::<F>),
            &mut s as *mut _ as *mut c_void,
            policy,
            operation,
        );
        if s.panicked {
            Err(TtsRunError {
                error: Error::CallbackPanicked,
                entered_ffi: true,
                stopped_by_sink: false,
            })
        } else {
            result.map_err(|mut err| {
                err.stopped_by_sink |= s.stopped_by_sink;
                err
            })
        }
    }
    fn run_dispatch(
        &mut self,
        r: &Request<'_>,
        cb: Callback,
        user: *mut c_void,
        policy: &ExecPolicy,
        operation: Option<Operation>,
    ) -> Result<Audio, TtsRunError> {
        let pre_err = |error| TtsRunError {
            error,
            entered_ffi: false,
            stopped_by_sink: false,
        };
        validate_exec_policy(policy).map_err(pre_err)?;
        if !policy.is_default() && self.api.tts_synthesize_ex.is_none() {
            return Err(pre_err(Error::UnsupportedAbi));
        }
        if operation.as_ref().is_some_and(Operation::requested) {
            return Err(pre_err(Error::Cancelled));
        }
        let text = cstring_err(r.text).map_err(pre_err)?;
        let lang = r.language.map(cstring_err).transpose().map_err(pre_err)?;
        let voice = r.voice.map(cstring_err).transpose().map_err(pre_err)?;
        let ref_text = r
            .reference
            .as_ref()
            .map(|v| cstring_err(v.text))
            .transpose()
            .map_err(pre_err)?;
        let (_owned, options) = pairs_err(r.options).map_err(pre_err)?;
        let (reference, frames, rate, channels) = if let Some(v) = &r.reference {
            if v.channels < 1 || v.channels > 2 || v.pcm.len() % v.channels as usize != 0 {
                return Err(pre_err(Error::InvalidInput(
                    "Invalid reference channels/frames".into(),
                )));
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
        let raw_policy = RawExecPolicy::from(policy);
        let token = operation.as_ref().map_or(ptr::null_mut(), Operation::token);
        if let Some(speed) = r.speed {
            crate::validate_speed(speed).map_err(pre_err)?;
            if self.api.cancel_api.feature_version == 0 && (speed - 1.0).abs() > f32::EPSILON {
                return Err(pre_err(Error::UnsupportedAbi));
            }
        }
        let req_v11 = RawRequestV1_1 {
            size: std::mem::size_of::<RawRequestV1_1>() as u32,
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
            speed: r.speed.unwrap_or(0.0),
        };
        let req_ptr: *const RawRequest = if self.api.cancel_api.feature_version >= 1 {
            (&req_v11 as *const RawRequestV1_1).cast()
        } else {
            &req
        };
        let mut out = ptr::null_mut();
        let status = unsafe {
            if let Some(synth_ex) = self.api.tts_synthesize_ex {
                synth_ex(self.raw, req_ptr, &raw_policy, token, cb, user, &mut out)
            } else if let (Some(_), Some(synth_cancellable)) =
                (&operation, self.api.tts_synthesize_cancellable)
            {
                synth_cancellable(self.raw, req_ptr, token, cb, user, &mut out)
            } else {
                (self.api.tts_synthesize)(self.raw, req_ptr, cb, user, &mut out)
            }
        };
        struct Owned {
            ptr: *mut c_void,
            free: HandleVoidFn,
        }
        impl Drop for Owned {
            fn drop(&mut self) {
                if !self.ptr.is_null() {
                    unsafe { (self.free)(self.ptr) }
                }
            }
        }
        let a = Owned {
            ptr: out,
            free: self.api.speech_audio_free,
        };
        let ffi_err = |error| TtsRunError {
            error,
            entered_ffi: true,
            stopped_by_sink: false,
        };
        check_with(status, self.api.last_error).map_err(ffi_err)?;
        if a.ptr.is_null() {
            return Err(ffi_err(Error::InvalidAudio));
        }
        let (frames, ch, rate, p) = unsafe {
            (
                (self.api.speech_audio_frames)(a.ptr),
                (self.api.speech_audio_channels)(a.ptr),
                (self.api.speech_audio_sample_rate)(a.ptr),
                (self.api.speech_audio_samples)(a.ptr),
            )
        };
        if !(1..=2).contains(&ch) || p.is_null() || frames == 0 || rate <= 0 {
            return Err(ffi_err(Error::InvalidAudio));
        }
        let n = frames
            .checked_mul(ch as usize)
            .filter(|count| *count <= (isize::MAX as usize) / std::mem::size_of::<f32>())
            .ok_or_else(|| ffi_err(Error::InvalidAudio))?;
        let mut metrics = Metrics::default();
        check_with(
            unsafe { (self.api.speech_audio_metrics)(a.ptr, &mut metrics) },
            self.api.last_error,
        )
        .map_err(ffi_err)?;
        let pcm = unsafe { std::slice::from_raw_parts(p, n).to_vec() };
        if !pcm.iter().all(|v| v.is_finite()) {
            return Err(ffi_err(Error::InvalidAudio));
        }
        if let Some(op) = operation {
            op.complete().map_err(ffi_err)?;
        }
        Ok(Audio {
            pcm,
            sample_rate: rate,
            channels: ch,
            metrics,
        })
    }
}
impl Drop for Tts {
    fn drop(&mut self) {
        unsafe { (self.api.tts_free)(self.raw) }
    }
}
pub struct Transcript {
    pub text: String,
    pub language: String,
    pub api_ms: f64,
}
fn transcript_with(api: &SpeechApi, p: *mut c_void) -> Result<Transcript, Error> {
    if p.is_null() {
        return Err(Error::Native {
            status: 2,
            message: "Null transcript returned by runtime".into(),
        });
    }
    unsafe {
        let text_ptr = (api.transcript_text)(p);
        let lang_ptr = (api.transcript_language)(p);
        let t = Transcript {
            text: if text_ptr.is_null() {
                String::new()
            } else {
                CStr::from_ptr(text_ptr).to_string_lossy().into_owned()
            },
            language: if lang_ptr.is_null() {
                String::new()
            } else {
                CStr::from_ptr(lang_ptr).to_string_lossy().into_owned()
            },
            api_ms: (api.transcript_api_ms)(p),
        };
        (api.transcript_free)(p);
        Ok(t)
    }
}
pub struct Asr {
    raw: *mut c_void,
    api: SpeechApi,
    _local: PhantomData<Rc<()>>,
}
impl Asr {
    pub fn new(c: &Config<'_>) -> Result<Self, String> {
        Self::open_with_op(speech_api(), c, None).map_err(|e| e.to_string())
    }
    /// Load an ASR handle with a single-use cancellation task.
    pub fn new_cancellable(c: &Config<'_>, task: &mut Task) -> Result<Self, Error> {
        let operation = task.begin()?;
        let engine = Self::open_with_op(speech_api(), c, Some(&operation))?;
        operation.complete()?;
        Ok(engine)
    }
    fn open_with_op(
        api: SpeechApi,
        c: &Config<'_>,
        operation: Option<&Operation>,
    ) -> Result<Self, Error> {
        if operation.is_some_and(Operation::requested) {
            return Err(Error::Cancelled);
        }
        if !api.available() {
            return Err(Error::UnsupportedAbi);
        }
        let prepared = c.prepare()?;
        if operation.is_some_and(Operation::requested) {
            return Err(Error::Cancelled);
        }
        let mut out = ptr::null_mut();
        let status = unsafe {
            if let (Some(op), Some(create)) = (operation, api.asr_create_cancellable) {
                create(&prepared.raw, op.token(), &mut out)
            } else {
                (api.asr_create)(&prepared.raw, &mut out)
            }
        };
        if let Err(err) = check_with(status, api.last_error) {
            if !out.is_null() {
                unsafe { (api.asr_free)(out) };
            }
            return Err(err);
        }
        if out.is_null() {
            return Err(Error::Native {
                status: 2,
                message: "Null ASR handle on success".into(),
            });
        }
        if operation.is_some_and(Operation::requested) {
            unsafe { (api.asr_free)(out) };
            return Err(Error::Cancelled);
        }
        Ok(Self {
            raw: out,
            api,
            _local: PhantomData,
        })
    }
    pub fn run(&mut self, pcm16k: &[f32], language: Option<&str>) -> Result<Transcript, String> {
        self.run_with_op(pcm16k, language, &ExecPolicy::default(), None)
            .map_err(|e| e.to_string())
    }
    /// Transcribe 16kHz mono PCM with a single-use cancellation task.
    pub fn run_cancellable(
        &mut self,
        pcm16k: &[f32],
        language: Option<&str>,
        task: &mut Task,
    ) -> Result<Transcript, Error> {
        let operation = task.begin()?;
        self.run_with_op(pcm16k, language, &ExecPolicy::default(), Some(operation))
    }
    /// Transcribe 16kHz mono PCM with an execution lock policy and optional cancellation task.
    pub fn run_ex(
        &mut self,
        pcm16k: &[f32],
        language: Option<&str>,
        policy: &ExecPolicy,
        task: Option<&mut Task>,
    ) -> Result<Transcript, Error> {
        let operation = task.map(Task::begin).transpose()?;
        self.run_with_op(pcm16k, language, policy, operation)
    }
    fn run_with_op(
        &mut self,
        pcm16k: &[f32],
        language: Option<&str>,
        policy: &ExecPolicy,
        operation: Option<Operation>,
    ) -> Result<Transcript, Error> {
        validate_exec_policy(policy)?;
        if !policy.is_default() && self.api.asr_run_ex.is_none() {
            return Err(Error::UnsupportedAbi);
        }
        if pcm16k.is_empty() || !pcm16k.iter().all(|v| v.is_finite()) {
            return Err(Error::InvalidInput(
                "ASR input must be non-empty finite 16kHz mono f32 PCM".into(),
            ));
        }
        if operation.as_ref().is_some_and(Operation::requested) {
            return Err(Error::Cancelled);
        }
        let lang = language.map(cstring_err).transpose()?;
        let raw_policy = RawExecPolicy::from(policy);
        let token = operation.as_ref().map_or(ptr::null_mut(), Operation::token);
        let mut out = ptr::null_mut();
        let status = unsafe {
            if let Some(run_ex) = self.api.asr_run_ex {
                run_ex(
                    self.raw,
                    pcm16k.as_ptr(),
                    pcm16k.len(),
                    cp(&lang),
                    &raw_policy,
                    token,
                    &mut out,
                )
            } else if let (Some(_), Some(run_cancellable)) =
                (&operation, self.api.asr_run_cancellable)
            {
                run_cancellable(
                    self.raw,
                    pcm16k.as_ptr(),
                    pcm16k.len(),
                    cp(&lang),
                    token,
                    &mut out,
                )
            } else {
                (self.api.asr_run)(self.raw, pcm16k.as_ptr(), pcm16k.len(), cp(&lang), &mut out)
            }
        };
        if let Err(err) = check_with(status, self.api.last_error) {
            if !out.is_null() {
                unsafe { (self.api.transcript_free)(out) };
            }
            return Err(err);
        }
        let t = transcript_with(&self.api, out)?;
        if let Some(op) = operation {
            op.complete()?;
        }
        Ok(t)
    }
    pub fn accept(&mut self, pcm16k: &[f32]) -> Result<(), String> {
        check(unsafe { (self.api.asr_accept)(self.raw, pcm16k.as_ptr(), pcm16k.len()) })
    }
    pub fn finish(&mut self, language: Option<&str>) -> Result<Transcript, String> {
        self.finish_with_op(language, &ExecPolicy::default(), None)
            .map_err(|e| e.to_string())
    }
    /// Finish buffered ASR input and decode with a single-use cancellation task.
    pub fn finish_cancellable(
        &mut self,
        language: Option<&str>,
        task: &mut Task,
    ) -> Result<Transcript, Error> {
        let operation = task.begin()?;
        self.finish_with_op(language, &ExecPolicy::default(), Some(operation))
    }
    /// Finish buffered ASR input with an execution lock policy and optional cancellation task.
    pub fn finish_ex(
        &mut self,
        language: Option<&str>,
        policy: &ExecPolicy,
        task: Option<&mut Task>,
    ) -> Result<Transcript, Error> {
        let operation = task.map(Task::begin).transpose()?;
        self.finish_with_op(language, policy, operation)
    }
    fn finish_with_op(
        &mut self,
        language: Option<&str>,
        policy: &ExecPolicy,
        operation: Option<Operation>,
    ) -> Result<Transcript, Error> {
        validate_exec_policy(policy)?;
        if !policy.is_default() && self.api.asr_finish_ex.is_none() {
            return Err(Error::UnsupportedAbi);
        }
        if operation.as_ref().is_some_and(Operation::requested) {
            return Err(Error::Cancelled);
        }
        let lang = language.map(cstring_err).transpose()?;
        let raw_policy = RawExecPolicy::from(policy);
        let token = operation.as_ref().map_or(ptr::null_mut(), Operation::token);
        let mut out = ptr::null_mut();
        let status = unsafe {
            if let Some(finish_ex) = self.api.asr_finish_ex {
                finish_ex(self.raw, cp(&lang), &raw_policy, token, &mut out)
            } else if let (Some(_), Some(finish_cancellable)) =
                (&operation, self.api.asr_finish_cancellable)
            {
                finish_cancellable(self.raw, cp(&lang), token, &mut out)
            } else {
                (self.api.asr_finish)(self.raw, cp(&lang), &mut out)
            }
        };
        if let Err(err) = check_with(status, self.api.last_error) {
            if !out.is_null() {
                unsafe { (self.api.transcript_free)(out) };
            }
            return Err(err);
        }
        let t = transcript_with(&self.api, out)?;
        if let Some(op) = operation {
            op.complete()?;
        }
        Ok(t)
    }
    pub fn reset(&mut self) -> Result<(), String> {
        check(unsafe { (self.api.asr_reset)(self.raw) })
    }
    /// Request cooperative cancellation of an in-flight ASR operation on this handle.
    pub fn cancel(&self) {
        if let Some(cancel_fn) = self.api.asr_cancel {
            unsafe { cancel_fn(self.raw) }
        }
    }
}
impl Drop for Asr {
    fn drop(&mut self) {
        unsafe { (self.api.asr_free)(self.raw) }
    }
}

#[cfg(test)]
pub(crate) mod test_support {
    use super::*;
    use crate::cancellation::CancelHandle;
    use std::{
        cell::RefCell,
        sync::{
            atomic::{AtomicBool, AtomicUsize, Ordering},
            Arc, Mutex,
        },
    };

    #[derive(Clone, Default)]
    pub(crate) struct MockState {
        pub(crate) creates: Arc<AtomicUsize>,
        pub(crate) frees: Arc<AtomicUsize>,
        pub(crate) ops: Arc<AtomicUsize>,
        pub(crate) last_policy: Arc<Mutex<Option<(u32, i32)>>>,
        pub(crate) active_cancel: Arc<Mutex<Option<CancelHandle>>>,
        pub(crate) barrier: Option<Arc<std::sync::Barrier>>,
    }

    struct MockAudio {
        pcm: Vec<f32>,
        rate: i32,
        channels: i32,
    }

    struct MockTranscript {
        text: CString,
        lang: CString,
    }

    thread_local! {
        static NEXT_STATE: RefCell<Option<MockState>> = const { RefCell::new(None) };
    }

    pub(crate) fn install_thread_state(state: MockState) {
        NEXT_STATE.with(|slot| *slot.borrow_mut() = Some(state));
    }

    pub(crate) fn take_thread_state() -> MockState {
        NEXT_STATE.with(|slot| slot.borrow_mut().take().unwrap_or_default())
    }

    pub(crate) unsafe extern "C" fn mock_token_new() -> *mut c_void {
        Box::into_raw(Box::new(AtomicBool::new(false))).cast()
    }
    pub(crate) unsafe extern "C" fn mock_token_request(ptr: *mut c_void) {
        if !ptr.is_null() {
            (*ptr.cast::<AtomicBool>()).store(true, Ordering::SeqCst);
        }
    }
    pub(crate) unsafe extern "C" fn mock_token_free(ptr: *mut c_void) {
        if !ptr.is_null() {
            drop(Box::from_raw(ptr.cast::<AtomicBool>()));
        }
    }
    pub(crate) fn mock_cancel_api(cooperative: bool) -> cancellation::Api {
        cancellation::Api {
            new: Some(mock_token_new),
            request: Some(mock_token_request),
            free: Some(mock_token_free),
            cooperative,
            ..cancellation::Api::default()
        }
    }

    unsafe extern "C" fn mock_abi_one() -> u32 {
        1
    }
    unsafe extern "C" fn mock_parallel_two() -> u32 {
        2
    }
    unsafe extern "C" fn mock_last_error() -> *const c_char {
        c"mock speech error".as_ptr()
    }
    unsafe extern "C" fn mock_catalog_json() -> *const c_char {
        c"{}".as_ptr()
    }
    unsafe extern "C" fn mock_audio_samples(ptr: *const c_void) -> *const f32 {
        if ptr.is_null() {
            ptr::null()
        } else {
            (*ptr.cast::<MockAudio>()).pcm.as_ptr()
        }
    }
    unsafe extern "C" fn mock_audio_frames(ptr: *const c_void) -> usize {
        if ptr.is_null() {
            0
        } else {
            let a = &*ptr.cast::<MockAudio>();
            a.pcm.len() / a.channels as usize
        }
    }
    unsafe extern "C" fn mock_audio_rate(ptr: *const c_void) -> i32 {
        if ptr.is_null() {
            0
        } else {
            (*ptr.cast::<MockAudio>()).rate
        }
    }
    unsafe extern "C" fn mock_audio_channels(ptr: *const c_void) -> i32 {
        if ptr.is_null() {
            0
        } else {
            (*ptr.cast::<MockAudio>()).channels
        }
    }
    unsafe extern "C" fn mock_audio_metrics(_: *const c_void, m: *mut Metrics) -> i32 {
        if !m.is_null() {
            (*m).chunks = 1;
        }
        0
    }
    unsafe extern "C" fn mock_audio_free(ptr: *mut c_void) {
        if !ptr.is_null() {
            drop(Box::from_raw(ptr.cast::<MockAudio>()));
        }
    }
    unsafe extern "C" fn mock_transcript_text(ptr: *const c_void) -> *const c_char {
        (*ptr.cast::<MockTranscript>()).text.as_ptr()
    }
    unsafe extern "C" fn mock_transcript_lang(ptr: *const c_void) -> *const c_char {
        (*ptr.cast::<MockTranscript>()).lang.as_ptr()
    }
    unsafe extern "C" fn mock_transcript_ms(_: *const c_void) -> f64 {
        1.5
    }
    unsafe extern "C" fn mock_transcript_free(ptr: *mut c_void) {
        if !ptr.is_null() {
            drop(Box::from_raw(ptr.cast::<MockTranscript>()));
        }
    }
    fn trigger_active_cancel(state: &MockState) {
        if let Some(handle) = state.active_cancel.lock().unwrap().take() {
            handle.cancel();
        }
    }
    fn token_cancelled(token: *mut c_void) -> bool {
        !token.is_null() && unsafe { (*token.cast::<AtomicBool>()).load(Ordering::SeqCst) }
    }
    unsafe extern "C" fn mock_create(
        cfg: *const RawConfig,
        token: *mut c_void,
        out: *mut *mut c_void,
    ) -> i32 {
        let state = take_thread_state();
        state.creates.fetch_add(1, Ordering::SeqCst);
        let path = CStr::from_ptr((*cfg).path).to_string_lossy().into_owned();
        if path == "load_cancel_leak_guard" {
            // Allocate handle to verify caller frees partial handle on cancelled load.
            *out = Box::into_raw(Box::new(state.clone())).cast();
            trigger_active_cancel(&state);
            return if token_cancelled(token) { 4 } else { 0 };
        }
        if path == "load_boundary_race" {
            *out = Box::into_raw(Box::new(state.clone())).cast();
            trigger_active_cancel(&state);
            return 0;
        }
        *out = Box::into_raw(Box::new(state)).cast();
        0
    }
    unsafe extern "C" fn mock_create_plain(cfg: *const RawConfig, out: *mut *mut c_void) -> i32 {
        mock_create(cfg, ptr::null_mut(), out)
    }
    unsafe extern "C" fn mock_free(ptr: *mut c_void) {
        if !ptr.is_null() {
            let state = Box::from_raw(ptr.cast::<MockState>());
            state.frees.fetch_add(1, Ordering::SeqCst);
        }
    }
    unsafe extern "C" fn mock_tts_synth_ex(
        handle: *mut c_void,
        req: *const RawRequest,
        policy: *const RawExecPolicy,
        token: *mut c_void,
        cb: Callback,
        user: *mut c_void,
        out: *mut *mut c_void,
    ) -> i32 {
        let state = &mut *handle.cast::<MockState>();
        state.ops.fetch_add(1, Ordering::SeqCst);
        if !policy.is_null() {
            let p = &*policy;
            *state.last_policy.lock().unwrap() = Some((p.timeout_ms, p.supersede));
        }
        let cmd = CStr::from_ptr((*req).text).to_string_lossy();
        if let Some(b) = &state.barrier {
            b.wait();
        }
        match cmd.as_ref() {
            "busy" => crate::STATUS_BUSY,
            "runtime_error" => 2,
            "cancel_op" => {
                trigger_active_cancel(state);
                if token_cancelled(token) {
                    4
                } else {
                    2
                }
            }
            "stream_sink_stop_returns_4" | "stream_chunks" => {
                let sample = [0.25_f32, -0.25];
                if let Some(cb_fn) = cb {
                    if cb_fn(user, sample.as_ptr(), sample.len(), 24_000, 1) != 0 {
                        return 4;
                    }
                }
                if cmd == "cancel_after_chunk" || cmd == "stream_sink_stop_returns_4" {
                    trigger_active_cancel(state);
                    return 4;
                }
                *out = Box::into_raw(Box::new(MockAudio {
                    pcm: sample.to_vec(),
                    rate: 24_000,
                    channels: 1,
                }))
                .cast();
                0
            }
            "stream_sink_cancel_midway" => {
                let sample = [0.25_f32, -0.25];
                if let Some(cb_fn) = cb {
                    if cb_fn(user, sample.as_ptr(), sample.len(), 24_000, 1) != 0 {
                        return 4;
                    }
                }
                trigger_active_cancel(state);
                if token_cancelled(token) {
                    4
                } else {
                    0
                }
            }
            _ => {
                *out = Box::into_raw(Box::new(MockAudio {
                    pcm: vec![0.1, 0.2],
                    rate: 24_000,
                    channels: 1,
                }))
                .cast();
                0
            }
        }
    }
    unsafe extern "C" fn mock_tts_synth_cancellable(
        handle: *mut c_void,
        req: *const RawRequest,
        token: *mut c_void,
        cb: Callback,
        user: *mut c_void,
        out: *mut *mut c_void,
    ) -> i32 {
        mock_tts_synth_ex(handle, req, ptr::null(), token, cb, user, out)
    }
    unsafe extern "C" fn mock_tts_synth_plain(
        handle: *mut c_void,
        req: *const RawRequest,
        cb: Callback,
        user: *mut c_void,
        out: *mut *mut c_void,
    ) -> i32 {
        mock_tts_synth_ex(handle, req, ptr::null(), ptr::null_mut(), cb, user, out)
    }
    unsafe extern "C" fn mock_asr_run_ex(
        handle: *mut c_void,
        _pcm: *const f32,
        n: usize,
        lang: *const c_char,
        policy: *const RawExecPolicy,
        token: *mut c_void,
        out: *mut *mut c_void,
    ) -> i32 {
        let state = &mut *handle.cast::<MockState>();
        state.ops.fetch_add(1, Ordering::SeqCst);
        if !policy.is_null() {
            let p = &*policy;
            *state.last_policy.lock().unwrap() = Some((p.timeout_ms, p.supersede));
        }
        if let Some(b) = &state.barrier {
            b.wait();
        }
        let lang_str = if lang.is_null() {
            "en".to_string()
        } else {
            CStr::from_ptr(lang).to_string_lossy().into_owned()
        };
        if lang_str == "cancel_op" {
            trigger_active_cancel(state);
            if token_cancelled(token) {
                return 4;
            }
        }
        if lang_str == "busy" || n == 999 {
            return crate::STATUS_BUSY;
        }
        *out = Box::into_raw(Box::new(MockTranscript {
            text: CString::new("mock ok").unwrap(),
            lang: CString::new(lang_str).unwrap(),
        }))
        .cast();
        0
    }
    unsafe extern "C" fn mock_asr_run_cancellable(
        handle: *mut c_void,
        pcm: *const f32,
        n: usize,
        lang: *const c_char,
        token: *mut c_void,
        out: *mut *mut c_void,
    ) -> i32 {
        mock_asr_run_ex(handle, pcm, n, lang, ptr::null(), token, out)
    }
    unsafe extern "C" fn mock_asr_run_plain(
        handle: *mut c_void,
        pcm: *const f32,
        n: usize,
        lang: *const c_char,
        out: *mut *mut c_void,
    ) -> i32 {
        mock_asr_run_ex(handle, pcm, n, lang, ptr::null(), ptr::null_mut(), out)
    }
    unsafe extern "C" fn mock_asr_finish_ex(
        handle: *mut c_void,
        lang: *const c_char,
        policy: *const RawExecPolicy,
        token: *mut c_void,
        out: *mut *mut c_void,
    ) -> i32 {
        mock_asr_run_ex(handle, ptr::null(), 1, lang, policy, token, out)
    }
    unsafe extern "C" fn mock_asr_finish_cancellable(
        handle: *mut c_void,
        lang: *const c_char,
        token: *mut c_void,
        out: *mut *mut c_void,
    ) -> i32 {
        mock_asr_finish_ex(handle, lang, ptr::null(), token, out)
    }
    unsafe extern "C" fn mock_asr_finish_plain(
        handle: *mut c_void,
        lang: *const c_char,
        out: *mut *mut c_void,
    ) -> i32 {
        mock_asr_finish_ex(handle, lang, ptr::null(), ptr::null_mut(), out)
    }
    unsafe extern "C" fn mock_asr_accept(_: *mut c_void, _: *const f32, _: usize) -> i32 {
        0
    }
    unsafe extern "C" fn mock_asr_reset(_: *mut c_void) -> i32 {
        0
    }

    pub(crate) fn mock_speech_api(cooperative: bool, with_ex: bool) -> SpeechApi {
        SpeechApi {
            speech_abi_version: mock_abi_one,
            speech_catalog_json: mock_catalog_json,
            last_error: mock_last_error,
            tts_create: mock_create_plain,
            tts_create_cancellable: Some(mock_create),
            tts_synthesize: mock_tts_synth_plain,
            tts_synthesize_cancellable: Some(mock_tts_synth_cancellable),
            tts_synthesize_ex: with_ex.then_some(mock_tts_synth_ex),
            tts_cancel: None,
            tts_free: mock_free,
            speech_audio_samples: mock_audio_samples,
            speech_audio_frames: mock_audio_frames,
            speech_audio_sample_rate: mock_audio_rate,
            speech_audio_channels: mock_audio_channels,
            speech_audio_metrics: mock_audio_metrics,
            speech_audio_free: mock_audio_free,
            asr_create: mock_create_plain,
            asr_create_cancellable: Some(mock_create),
            asr_run: mock_asr_run_plain,
            asr_run_cancellable: Some(mock_asr_run_cancellable),
            asr_run_ex: with_ex.then_some(mock_asr_run_ex),
            asr_accept: mock_asr_accept,
            asr_finish: mock_asr_finish_plain,
            asr_finish_cancellable: Some(mock_asr_finish_cancellable),
            asr_finish_ex: with_ex.then_some(mock_asr_finish_ex),
            asr_reset: mock_asr_reset,
            asr_cancel: None,
            asr_free: mock_free,
            transcript_text: mock_transcript_text,
            transcript_language: mock_transcript_lang,
            transcript_api_ms: mock_transcript_ms,
            transcript_free: mock_transcript_free,
            parallel_version: Some(mock_parallel_two),
            cooperative_version: cooperative.then_some(mock_abi_one),
            cancel_api: mock_cancel_api(cooperative),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::test_support::*;
    use super::*;
    use crate::cancellation::CancelOutcome;
    use std::sync::{
        atomic::Ordering,
        Arc, Barrier,
    };

    #[test]
    fn option_pairs_retain_c_string_storage() {
        let (owned, raw) = pairs(&[("language", "zh"), ("voice", "female")]).unwrap();
        assert_eq!(owned.len(), raw.len());
        for ((key, value), pair) in owned.iter().zip(&raw) {
            assert_eq!(pair.key, key.as_ptr());
            assert_eq!(pair.value, value.as_ptr());
            assert_eq!(unsafe { CStr::from_ptr(pair.key) }, key.as_c_str());
            assert_eq!(unsafe { CStr::from_ptr(pair.value) }, value.as_c_str());
        }
        let (owned, raw) = pairs(&[]).unwrap();
        assert!(owned.is_empty() && raw.is_empty());
    }

    #[test]
    fn option_pairs_reject_interior_nul() {
        assert!(pairs(&[("bad\0key", "value")]).is_err());
        assert!(pairs(&[("key", "bad\0value")]).is_err());
    }

    #[test]
    fn parallel_inference_version_and_capabilities_matrix() {
        let mut api = mock_speech_api(false, false);
        api.parallel_version = None;
        api.tts_create_cancellable = None;
        api.tts_synthesize_cancellable = None;
        assert_eq!(api.parallel_inference_version(), 0);
        assert_eq!(
            api.capabilities(),
            Capabilities {
                loading: CancelMode::DiscardAfterReturn,
                synthesis: CancelMode::DiscardAfterReturn,
            }
        );

        unsafe extern "C" fn parallel_one() -> u32 {
            1
        }
        let mut boundary = mock_speech_api(false, true);
        boundary.parallel_version = Some(parallel_one);
        assert_eq!(boundary.parallel_inference_version(), 1);
        assert_eq!(
            boundary.capabilities(),
            Capabilities {
                loading: CancelMode::Boundary,
                synthesis: CancelMode::Boundary,
            }
        );

        let coop = mock_speech_api(true, true);
        assert_eq!(coop.parallel_inference_version(), 2);
        assert_eq!(
            coop.capabilities(),
            Capabilities {
                loading: CancelMode::Cooperative,
                synthesis: CancelMode::Cooperative,
            }
        );
    }

    #[test]
    fn tts_and_asr_precancel_and_load_cancel() {
        let api = mock_speech_api(true, true);
        let cancel_api = api.cancel_api;

        // Pre-cancel TTS load
        let state = MockState::default();
        install_thread_state(state.clone());
        let mut task = Task::with_api(cancel_api).unwrap();
        let handle = task.cancel_handle();
        assert_eq!(handle.cancel(), CancelOutcome::Requested);
        let op = task.begin().unwrap();
        let res = Tts::open_with_op(api, &Config::new("pocket_tts", "normal"), Some(&op));
        assert!(matches!(res, Err(Error::Cancelled)));
        assert_eq!(state.creates.load(Ordering::SeqCst), 0);
        drop(op);
        assert_eq!(handle.cancel(), CancelOutcome::Inactive);

        // Pre-cancel ASR load
        let state = MockState::default();
        install_thread_state(state.clone());
        let mut task = Task::with_api(cancel_api).unwrap();
        let handle = task.cancel_handle();
        assert_eq!(handle.cancel(), CancelOutcome::Requested);
        let op = task.begin().unwrap();
        let res = Asr::open_with_op(api, &Config::new("sense_asr", "normal"), Some(&op));
        assert!(matches!(res, Err(Error::Cancelled)));
        assert_eq!(state.creates.load(Ordering::SeqCst), 0);
        drop(op);

        // Cooperative load cancel returning partial handle + ORTTS_CANCELLED must free handle
        for model in ["load_cancel_leak_guard", "load_boundary_race"] {
            let state = MockState::default();
            let mut task = Task::with_api(cancel_api).unwrap();
            let handle = task.cancel_handle();
            *state.active_cancel.lock().unwrap() = Some(handle.clone());
            install_thread_state(state.clone());
            let op = task.begin().unwrap();
            let loaded = Tts::open_with_op(api, &Config::new("pocket_tts", model), Some(&op))
                .and_then(|e| {
                    op.complete()?;
                    Ok(e)
                });
            assert!(matches!(loaded, Err(Error::Cancelled)));
            assert_eq!(state.creates.load(Ordering::SeqCst), 1);
            assert_eq!(state.frees.load(Ordering::SeqCst), 1);
            drop(op);
            assert_eq!(handle.cancel(), CancelOutcome::Inactive);

            let state_asr = MockState::default();
            let mut task_asr = Task::with_api(cancel_api).unwrap();
            let handle_asr = task_asr.cancel_handle();
            *state_asr.active_cancel.lock().unwrap() = Some(handle_asr.clone());
            install_thread_state(state_asr.clone());
            let op_asr = task_asr.begin().unwrap();
            let loaded_asr =
                Asr::open_with_op(api, &Config::new("sense_asr", model), Some(&op_asr))
                    .and_then(|e| {
                        op_asr.complete()?;
                        Ok(e)
                    });
            assert!(matches!(loaded_asr, Err(Error::Cancelled)));
            assert_eq!(state_asr.creates.load(Ordering::SeqCst), 1);
            assert_eq!(state_asr.frees.load(Ordering::SeqCst), 1);
            drop(op_asr);
            assert_eq!(handle_asr.cancel(), CancelOutcome::Inactive);
        }
    }

    #[test]
    fn tts_and_asr_operation_cancel_and_stale_handle_isolation() {
        let api = mock_speech_api(true, true);
        let cancel_api = api.cancel_api;

        let tts_state = MockState::default();
        install_thread_state(tts_state.clone());
        let mut tts = Tts::open_with_op(api, &Config::new("pocket_tts", "ok"), None).unwrap();

        let asr_state = MockState::default();
        install_thread_state(asr_state.clone());
        let mut asr = Asr::open_with_op(api, &Config::new("sense_asr", "ok"), None).unwrap();

        // Cancel in-flight TTS synthesize & stream, and verify handle remains reusable
        let mut t1 = Task::with_api(cancel_api).unwrap();
        let old_tts = t1.cancel_handle();
        *tts_state.active_cancel.lock().unwrap() = Some(old_tts.clone());
        assert!(matches!(
            tts.synthesize_cancellable(&Request::new("cancel_op"), &mut t1),
            Err(Error::Cancelled)
        ));
        assert!(matches!(
            tts.synthesize_cancellable(&Request::new("ok"), &mut t1),
            Err(Error::TaskConsumed)
        ));
        assert_eq!(old_tts.cancel(), CancelOutcome::Inactive);
        assert_eq!(tts_state.frees.load(Ordering::SeqCst), 0);

        let mut t2 = Task::with_api(cancel_api).unwrap();
        let old_tts_stream = t2.cancel_handle();
        *tts_state.active_cancel.lock().unwrap() = Some(old_tts_stream.clone());
        let mut seen = 0usize;
        assert!(matches!(
            tts.stream_cancellable(
                &Request::new("stream_sink_cancel_midway"),
                |pcm, rate, ch| {
                    seen += pcm.len();
                    assert_eq!((rate, ch), (24_000, 1));
                    true
                },
                &mut t2
            ),
            Err(Error::Cancelled)
        ));
        assert_eq!(seen, 2);
        assert_eq!(old_tts_stream.cancel(), CancelOutcome::Inactive);

        // Next TTS task is unaffected by stale handle
        let mut t3 = Task::with_api(cancel_api).unwrap();
        assert_eq!(old_tts.cancel(), CancelOutcome::Inactive);
        let audio = tts
            .synthesize_cancellable(&Request::new("ok"), &mut t3)
            .unwrap();
        assert_eq!(audio.pcm, vec![0.1, 0.2]);
        assert_eq!(tts_state.frees.load(Ordering::SeqCst), 0);

        // Cancel in-flight ASR run and finish, then recover on fresh Task
        let mut a1 = Task::with_api(cancel_api).unwrap();
        let old_asr = a1.cancel_handle();
        *asr_state.active_cancel.lock().unwrap() = Some(old_asr.clone());
        assert!(matches!(
            asr.run_cancellable(&[0.0; 160], Some("cancel_op"), &mut a1),
            Err(Error::Cancelled)
        ));
        assert_eq!(old_asr.cancel(), CancelOutcome::Inactive);

        let mut a2 = Task::with_api(cancel_api).unwrap();
        let old_asr_fin = a2.cancel_handle();
        *asr_state.active_cancel.lock().unwrap() = Some(old_asr_fin.clone());
        assert!(matches!(
            asr.finish_cancellable(Some("cancel_op"), &mut a2),
            Err(Error::Cancelled)
        ));
        assert_eq!(old_asr_fin.cancel(), CancelOutcome::Inactive);

        let mut a3 = Task::with_api(cancel_api).unwrap();
        assert_eq!(old_asr.cancel(), CancelOutcome::Inactive);
        let tr = asr.run_cancellable(&[0.1; 160], Some("en"), &mut a3).unwrap();
        assert_eq!(tr.text, "mock ok");
        assert_eq!(asr_state.frees.load(Ordering::SeqCst), 0);
    }

    #[test]
    fn speech_exec_policy_and_legacy_fallback() {
        let api_ex = mock_speech_api(true, true);
        let tts_state = MockState::default();
        install_thread_state(tts_state.clone());
        let mut tts = Tts::open_with_op(api_ex, &Config::new("pocket_tts", "ok"), None).unwrap();
        let policy = ExecPolicy::new(750, true);
        let audio = tts.synthesize_ex(&Request::new("ok"), &policy, None).unwrap();
        assert_eq!(audio.pcm, vec![0.1, 0.2]);
        assert_eq!(*tts_state.last_policy.lock().unwrap(), Some((750, 1)));
        assert!(matches!(
            tts.synthesize_ex(&Request::new("busy"), &policy, None),
            Err(err) if err.is_busy()
        ));
        assert!(matches!(
            tts.synthesize_ex(&Request::new("ok"), &ExecPolicy::new(30_001, false), None),
            Err(Error::InvalidInput(_))
        ));

        let api_no_ex = mock_speech_api(true, false);
        let legacy_tts_state = MockState::default();
        install_thread_state(legacy_tts_state.clone());
        let mut legacy_tts =
            Tts::open_with_op(api_no_ex, &Config::new("pocket_tts", "ok"), None).unwrap();
        assert!(matches!(
            legacy_tts.synthesize_ex(&Request::new("ok"), &ExecPolicy::new(100, false), None),
            Err(Error::UnsupportedAbi)
        ));
        assert!(legacy_tts
            .synthesize_ex(&Request::new("ok"), &ExecPolicy::default(), None)
            .is_ok());

        let legacy_asr_state = MockState::default();
        install_thread_state(legacy_asr_state);
        let mut legacy_asr =
            Asr::open_with_op(api_no_ex, &Config::new("sense_asr", "ok"), None).unwrap();
        assert!(matches!(
            legacy_asr.run_ex(&[0.0; 16], Some("en"), &ExecPolicy::new(0, true), None),
            Err(Error::UnsupportedAbi)
        ));
        assert!(legacy_asr
            .finish_ex(Some("en"), &ExecPolicy::default(), None)
            .is_ok());
    }

    #[test]
    fn mock_parallel_tts_and_asr_concurrent_threads_no_busy() {
        let api = mock_speech_api(true, true);
        assert_eq!(api.parallel_inference_version(), 2);
        let overlap_barrier = Arc::new(Barrier::new(2));
        let tts_barrier = overlap_barrier.clone();

        let tts_thread = std::thread::spawn(move || {
            let tts_state = MockState {
                barrier: Some(tts_barrier),
                ..MockState::default()
            };
            install_thread_state(tts_state);
            let mut tts = Tts::open_with_op(api, &Config::new("pocket_tts", "ok"), None).unwrap();
            let mut task = Task::with_api(api.cancel_api).unwrap();
            tts.synthesize_ex(
                &Request::new("ok"),
                &ExecPolicy::default(),
                Some(&mut task),
            )
        });
        let asr_thread = std::thread::spawn(move || {
            let asr_state = MockState {
                barrier: Some(overlap_barrier),
                ..MockState::default()
            };
            install_thread_state(asr_state);
            let mut asr = Asr::open_with_op(api, &Config::new("sense_asr", "ok"), None).unwrap();
            let mut task = Task::with_api(api.cancel_api).unwrap();
            asr.run_ex(
                &[0.1_f32; 320],
                Some("en"),
                &ExecPolicy::default(),
                Some(&mut task),
            )
        });

        let audio = tts_thread.join().unwrap().unwrap();
        let transcript = asr_thread.join().unwrap().unwrap();
        assert_eq!(audio.pcm, vec![0.1, 0.2]);
        assert_eq!(transcript.text, "mock ok");
    }

    #[test]
    fn parse_runtime_capabilities_and_speed_dispatch() {
        let sample = r#"{
            "schema": 1,
            "abi_version": 1,
            "engine_feature_version": 2,
            "recommended_bilingual_asr": "sense_asr",
            "capabilities": {
                "tts": {
                    "ortts_qwen3_lfm": {
                        "api": "ortts_engine_*",
                        "streaming": true,
                        "per_request_speaker": true,
                        "speaker_vector_clone": false,
                        "reference_audio_clone": false,
                        "speed_control": false,
                        "sample_rate": 24000,
                        "channels": 1,
                        "languages": ["zh", "en"]
                    },
                    "kokoro_tts": {
                        "api": "ortts_tts_*",
                        "streaming": true,
                        "per_request_speaker": true,
                        "speaker_vector_clone": false,
                        "reference_audio_clone": false,
                        "speed_control": true,
                        "sample_rate": 24000,
                        "channels": 1,
                        "languages": ["zh", "en-us", "en-gb"]
                    }
                },
                "asr": {
                    "sense_asr": {
                        "api": "ortts_asr_*|ortts_asr_stream_*",
                        "streaming": true,
                        "true_streaming": false,
                        "streaming_kind": "segmented-energy",
                        "languages": ["zh", "en"],
                        "sample_rate": 16000,
                        "recommended_bilingual": true
                    }
                }
            }
        }"#;
        let caps = parse_runtime_capabilities(sample);
        assert_eq!(caps.abi_version, 1);
        assert_eq!(caps.engine_feature_version, 2);
        assert_eq!(caps.recommended_bilingual_asr.as_deref(), Some("sense_asr"));
        assert_eq!(caps.tts.len(), 2);
        assert!(caps.tts[0].per_request_speaker);
        assert!(!caps.tts[0].speed_control);
        assert!(caps.tts[1].speed_control);
        assert_eq!(caps.asr.len(), 1);
        assert!(!caps.asr[0].true_streaming);
        assert!(caps.asr[0].recommended_bilingual);

        let api = mock_speech_api(true, true);
        let state = MockState::default();
        install_thread_state(state);
        let mut tts = Tts::open_with_op(api, &Config::new("kokoro_tts", "ok"), None).unwrap();
        assert!(matches!(
            tts.synthesize_ex(&Request::new("ok").with_speed(3.0), &ExecPolicy::default(), None),
            Err(Error::InvalidInput(_))
        ));
        assert!(matches!(
            tts.synthesize_ex(&Request::new("ok").with_speed(1.5), &ExecPolicy::default(), None),
            Err(Error::UnsupportedAbi)
        ));
    }
}
