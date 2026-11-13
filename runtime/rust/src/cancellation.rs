//! Single-use operation tickets. Only CancelHandle is shared with UI/control threads.
use crate::{Callback, Config, Error, Request};
use std::{
    ffi::c_void,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex, MutexGuard, OnceLock,
    },
};

type CreateToken = unsafe extern "C" fn() -> *mut c_void;
type TokenFn = unsafe extern "C" fn(*mut c_void);
type Create = unsafe extern "C" fn(*const Config, *mut c_void, *mut *mut c_void) -> i32;
type Synthesize = unsafe extern "C" fn(
    *mut c_void,
    *const Request,
    *mut c_void,
    Callback,
    *mut c_void,
    *mut *mut c_void,
) -> i32;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CancelMode {
    /// CPU graph/step checkpoints. Does not preempt an arbitrary kernel or I/O.
    Cooperative,
    /// Native stage boundaries only; latency may include a full compute stage.
    Boundary,
    /// No matched task-token API: precheck or discard result after return.
    DiscardAfterReturn,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Capabilities {
    pub loading: CancelMode,
    pub synthesis: CancelMode,
}

#[derive(Clone, Copy, Default)]
pub(crate) struct Api {
    new: Option<CreateToken>,
    request: Option<TokenFn>,
    free: Option<TokenFn>,
    pub(crate) create: Option<Create>,
    pub(crate) synthesize: Option<Synthesize>,
    cooperative: bool,
}

impl Api {
    fn capabilities(self) -> Capabilities {
        let mode = if self.cooperative {
            CancelMode::Cooperative
        } else {
            CancelMode::Boundary
        };
        Capabilities {
            loading: if self.create.is_some() {
                mode
            } else {
                CancelMode::DiscardAfterReturn
            },
            synthesis: if self.synthesize.is_some() {
                mode
            } else {
                CancelMode::DiscardAfterReturn
            },
        }
    }
}

pub fn capabilities() -> Capabilities {
    api().capabilities()
}

fn api() -> Api {
    static API: OnceLock<Api> = OnceLock::new();
    *API.get_or_init(discover)
}

// Resolve OPTIONAL symbols from the image that owns the already linked ABI1
// function, not RTLD_DEFAULT (which could resolve a second unrelated runtime).
// No hard relocations to new symbols: old ABI1 libraries remain loadable.
#[cfg(unix)]
fn discover() -> Api {
    use std::ffi::c_char;
    #[repr(C)]
    struct DlInfo {
        file: *const c_char,
        base: *mut c_void,
        symbol: *const c_char,
        address: *mut c_void,
    }
    extern "C" {
        fn dladdr(address: *const c_void, info: *mut DlInfo) -> i32;
        fn dlopen(path: *const c_char, flags: i32) -> *mut c_void;
        fn dlsym(handle: *mut c_void, symbol: *const c_char) -> *mut c_void;
        fn dlclose(handle: *mut c_void) -> i32;
    }
    unsafe {
        let mut info: DlInfo = std::mem::zeroed();
        if dladdr(
            crate::ortts_abi_version as *const () as *const c_void,
            &mut info,
        ) == 0
            || info.file.is_null()
        {
            return Api::default();
        }
        let handle = dlopen(info.file, 1); // RTLD_LAZY; this image is already linked.
        if handle.is_null() {
            return Api::default();
        }
        macro_rules! symbol {
            ($name:literal, $ty:ty) => {{
                let ptr = dlsym(handle, concat!($name, "\0").as_ptr().cast());
                if ptr.is_null() {
                    None
                } else {
                    Some(std::mem::transmute::<*mut c_void, $ty>(ptr))
                }
            }};
        }
        let new = symbol!("ortts_cancel_token_create", CreateToken);
        let request = symbol!("ortts_cancel_token_request", TokenFn);
        let free = symbol!("ortts_cancel_token_free", TokenFn);
        let mut result = Api::default();
        if new.is_some() && request.is_some() && free.is_some() {
            result = Api {
                new,
                request,
                free,
                create: symbol!("ortts_engine_create_cancellable", Create),
                synthesize: symbol!("ortts_engine_synthesize_cancellable", Synthesize),
                cooperative: symbol!(
                    "ortts_cooperative_cancel_version",
                    unsafe extern "C" fn() -> u32
                )
                .is_some_and(|version| version() == 1),
            };
        }
        // Balances only our lookup reference. ABI1 direct linkage retains image.
        dlclose(handle);
        result
    }
}

#[cfg(not(unix))]
fn discover() -> Api {
    Api::default()
}

struct Token {
    raw: *mut c_void,
    api: Api,
}
// SAFETY: C token request is thread-safe; all requests/free are serialized by
// Inner.state. The operation guard retains the owner until native compute joins.
unsafe impl Send for Token {}
impl Drop for Token {
    fn drop(&mut self) {
        unsafe { (self.api.free.unwrap())(self.raw) }
    }
}
struct State {
    consumed: bool,
    finished: bool,
    requested: bool,
    token: Option<Token>,
}
struct Inner {
    generation: u64,
    api: Api,
    state: Mutex<State>,
}
impl Inner {
    fn lock(&self) -> MutexGuard<'_, State> {
        // No user code is invoked under this lock. Poison recovery still permits cleanup.
        self.state.lock().unwrap_or_else(|e| e.into_inner())
    }
    fn finish(&self) {
        let mut state = self.lock();
        state.finished = true;
        state.token.take(); // request/free cannot race; native invocation has returned.
    }
}

/// A single-use ticket for ONE load or synthesis, never reused for another round.
/// Create on the worker or transfer it to that worker; share only its cancel handle.
pub struct Task {
    inner: Arc<Inner>,
}
/// Send + Sync, cloneable, generation-bound; never contains an engine pointer.
#[derive(Clone)]
pub struct CancelHandle {
    inner: Arc<Inner>,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CancelOutcome {
    Requested,
    AlreadyRequested,
    Inactive,
}

impl Task {
    pub fn new() -> Result<Self, Error> {
        Self::with_api(api())
    }
    fn with_api(api: Api) -> Result<Self, Error> {
        static NEXT: AtomicU64 = AtomicU64::new(1);
        let generation = NEXT
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |n| n.checked_add(1))
            .map_err(|_| Error::InvalidInput("Task generation exhausted".into()))?;
        let token = if let Some(new) = api.new {
            let raw = unsafe { new() };
            if raw.is_null() {
                return Err(Error::InvalidInput(
                    "Cannot allocate cancellation token".into(),
                ));
            }
            Some(Token { raw, api })
        } else {
            None
        };
        Ok(Self {
            inner: Arc::new(Inner {
                generation,
                api,
                state: Mutex::new(State {
                    consumed: false,
                    finished: false,
                    requested: false,
                    token,
                }),
            }),
        })
    }
    pub fn cancel_handle(&self) -> CancelHandle {
        CancelHandle {
            inner: self.inner.clone(),
        }
    }
    pub fn generation(&self) -> u64 {
        self.inner.generation
    }
    pub fn capabilities(&self) -> Capabilities {
        self.inner.api.capabilities()
    }
    pub(crate) fn begin(&mut self) -> Result<Operation, Error> {
        let mut state = self.inner.lock();
        if state.consumed || state.finished {
            return Err(Error::TaskConsumed);
        }
        state.consumed = true;
        Ok(Operation {
            inner: self.inner.clone(),
        })
    }
}
impl Drop for Task {
    fn drop(&mut self) {
        self.inner.finish();
    }
}
impl CancelHandle {
    pub fn generation(&self) -> u64 {
        self.inner.generation
    }
    pub fn cancel(&self) -> CancelOutcome {
        let mut state = self.inner.lock();
        if state.finished {
            return CancelOutcome::Inactive;
        }
        if state.requested {
            return CancelOutcome::AlreadyRequested;
        }
        state.requested = true;
        if let Some(token) = &state.token {
            unsafe { (token.api.request.unwrap())(token.raw) };
        }
        CancelOutcome::Requested
    }
}

pub(crate) struct Operation {
    inner: Arc<Inner>,
}
impl Operation {
    pub(crate) fn requested(&self) -> bool {
        self.inner.lock().requested
    }
    pub(crate) fn token(&self) -> *mut c_void {
        self.inner
            .lock()
            .token
            .as_ref()
            .map_or(std::ptr::null_mut(), |token| token.raw)
    }
    pub(crate) fn api(&self) -> Api {
        self.inner.api
    }
    /// Linearize successful completion against cancel; late handles become inert.
    pub(crate) fn complete(&self) -> Result<(), Error> {
        let mut state = self.inner.lock();
        let cancelled = state.requested;
        state.finished = true;
        state.token.take();
        if cancelled {
            Err(Error::Cancelled)
        } else {
            Ok(())
        }
    }
}
impl Drop for Operation {
    fn drop(&mut self) {
        self.inner.finish();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn handle_is_send_sync() {
        fn require<T: Send + Sync>() {}
        require::<CancelHandle>();
    }
    #[test]
    fn stale_handle_cannot_cancel_next_task() {
        let mut first = Task::with_api(Api::default()).unwrap();
        let old = first.cancel_handle();
        let op = first.begin().unwrap();
        op.complete().unwrap();
        let mut next = Task::with_api(Api::default()).unwrap();
        let new_op = next.begin().unwrap();
        assert_ne!(old.generation(), next.generation());
        assert_eq!(old.cancel(), CancelOutcome::Inactive);
        assert!(!new_op.requested());
        assert!(matches!(first.begin(), Err(Error::TaskConsumed)));
    }
    #[test]
    fn precancel_and_drop_without_execution() {
        let mut task = Task::with_api(Api::default()).unwrap();
        let handle = task.cancel_handle();
        assert_eq!(handle.cancel(), CancelOutcome::Requested);
        assert_eq!(handle.cancel(), CancelOutcome::AlreadyRequested);
        let op = task.begin().unwrap();
        assert!(op.requested());
        assert_eq!(op.complete(), Err(Error::Cancelled));
        drop(op);
        drop(task);
        assert_eq!(handle.cancel(), CancelOutcome::Inactive);
    }
    #[test]
    fn completion_and_cancel_are_linearized() {
        for _ in 0..100 {
            let mut task = Task::with_api(Api::default()).unwrap();
            let handle = task.cancel_handle();
            let op = task.begin().unwrap();
            let thread = std::thread::spawn(move || handle.cancel());
            let result = op.complete();
            let outcome = thread.join().unwrap();
            assert!(matches!(
                (result, outcome),
                (Ok(()), CancelOutcome::Inactive)
                    | (Err(Error::Cancelled), CancelOutcome::Requested)
            ));
        }
    }
    #[test]
    fn absent_symbols_have_explicit_degradation() {
        assert_eq!(
            Api::default().capabilities(),
            Capabilities {
                loading: CancelMode::DiscardAfterReturn,
                synthesis: CancelMode::DiscardAfterReturn,
            }
        );
    }

    #[test]
    fn partial_v1_api_does_not_claim_token_synthesis() {
        unsafe extern "C" fn create(_: *const Config, _: *mut c_void, _: *mut *mut c_void) -> i32 {
            0
        }
        let boundary = Api {
            create: Some(create),
            ..Api::default()
        }
        .capabilities();
        assert_eq!(boundary.loading, CancelMode::Boundary);
        assert_eq!(boundary.synthesis, CancelMode::DiscardAfterReturn);
        let graph = Api {
            create: Some(create),
            cooperative: true,
            ..Api::default()
        }
        .capabilities();
        assert_eq!(graph.loading, CancelMode::Cooperative);
        assert_eq!(graph.synthesis, CancelMode::DiscardAfterReturn);
    }

    #[test]
    fn native_token_free_is_serialized_with_cancel() {
        use std::sync::atomic::AtomicUsize;
        static FREES: AtomicUsize = AtomicUsize::new(0);
        unsafe extern "C" fn new() -> *mut c_void {
            Box::into_raw(Box::new(false)).cast()
        }
        unsafe extern "C" fn request(ptr: *mut c_void) {
            // Intentionally non-atomic: safe only if request/free is serialized.
            *ptr.cast::<bool>() = true;
            std::thread::yield_now();
        }
        unsafe extern "C" fn free(ptr: *mut c_void) {
            drop(Box::from_raw(ptr.cast::<bool>()));
            FREES.fetch_add(1, Ordering::SeqCst);
        }
        for _ in 0..100 {
            let mut task = Task::with_api(Api {
                new: Some(new),
                request: Some(request),
                free: Some(free),
                ..Api::default()
            })
            .unwrap();
            let handle = task.cancel_handle();
            let late = handle.clone();
            let op = task.begin().unwrap();
            let thread = std::thread::spawn(move || {
                for _ in 0..10 {
                    handle.cancel();
                }
            });
            let _ = op.complete();
            thread.join().unwrap();
            drop(op);
            drop(task);
            assert_eq!(late.cancel(), CancelOutcome::Inactive);
        }
        assert_eq!(FREES.load(Ordering::SeqCst), 100);
    }
}
