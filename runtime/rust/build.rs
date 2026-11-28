fn main() {
    if matches!(
        std::env::var("CARGO_CFG_TARGET_OS").as_deref(),
        Ok("linux" | "android")
    ) {
        println!("cargo:rustc-link-lib=dl");
    }
    println!("cargo:rerun-if-env-changed=ORTTS_LIB_DIR");
    println!("cargo:rerun-if-env-changed=ORTTS_FRAMEWORK_DIR");
    println!("cargo:rerun-if-env-changed=ORTTS_EMBED_DEV_RPATH");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("ios") {
        if let Ok(path) = std::env::var("ORTTS_FRAMEWORK_DIR") {
            println!("cargo:rustc-link-search=framework={path}");
        }
        println!("cargo:rustc-link-lib=framework=OrTTS");
        return;
    }
    if let Ok(path) = std::env::var("ORTTS_LIB_DIR") {
        println!("cargo:rustc-link-search=native={path}");
        if std::env::var("ORTTS_EMBED_DEV_RPATH").as_deref() == Ok("1")
            && matches!(
                std::env::var("CARGO_CFG_TARGET_OS").as_deref(),
                Ok("macos" | "linux")
            )
        {
            println!("cargo:rustc-link-arg=-Wl,-rpath,{path}");
        }
    }
    println!("cargo:rustc-link-lib=dylib=ortts");
}
