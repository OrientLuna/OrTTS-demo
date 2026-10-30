fn main() {
    println!("cargo:rerun-if-env-changed=ORTTS_LIB_DIR");
    println!("cargo:rerun-if-env-changed=ORTTS_FRAMEWORK_DIR");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("ios") {
        if let Ok(path) = std::env::var("ORTTS_FRAMEWORK_DIR") {
            println!("cargo:rustc-link-search=framework={path}");
        }
        println!("cargo:rustc-link-lib=framework=OrTTS");
        return;
    }
    if let Ok(path) = std::env::var("ORTTS_LIB_DIR") {
        println!("cargo:rustc-link-search=native={path}");
    }
    println!("cargo:rustc-link-lib=dylib=ortts");
}
