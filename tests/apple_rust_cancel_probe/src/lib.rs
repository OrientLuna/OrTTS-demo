//! Standalone acceptance shim; never link this test module into a production app.
#[path = "../../../runtime/rust/examples/cancellation.rs"]
mod acceptance;
use std::ffi::{c_char, CStr};

/// # Safety
/// Arguments must be valid, NUL-terminated UTF-8 paths/SHA; called on a fixed worker.
#[no_mangle]
pub unsafe extern "C" fn ortts_rust_cancel_probe(
    root: *const c_char,
    sha: *const c_char,
    output: *const c_char,
) -> i32 {
    let result = std::panic::catch_unwind(|| {
        let root = CStr::from_ptr(root).to_str().map_err(|e| e.to_string())?;
        let sha = CStr::from_ptr(sha).to_str().map_err(|e| e.to_string())?;
        let output = CStr::from_ptr(output).to_str().map_err(|e| e.to_string())?;
        match acceptance::acceptance(root, sha) {
            Ok(report) => std::fs::write(output, report).map_err(|e| e.to_string()),
            Err(error) => {
                eprintln!("Rust cancellation acceptance: {error}");
                std::fs::write(
                    output,
                    "{\"status\":\"failed\",\"reason\":\"see process log\"}",
                )
                .ok();
                Err(error)
            }
        }
    });
    if matches!(result, Ok(Ok(()))) {
        0
    } else {
        1
    }
}
