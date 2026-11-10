# CPU backends

Android ARM64 can package three CPU implementations together: baseline, DotProd + FP16, and I8MM. The engine checks CPU capabilities before opening a module, chooses the highest supported ISA tier, and keeps only the selected module resident. Models and the C/Rust APIs are shared.

Prepare the usual verified unified speech source, then add the CPU modules:

```sh
python3 tools/prepare_cpu_dispatch.py \
  --source /path/to/prepared/audio.cpp \
  --out /path/to/cpu-source

python3 tools/build_android.py --cpu-auto --liquidcodec --speech \
  --source /path/to/cpu-source/audio.cpp \
  --ndk /path/to/ndk --sdk /path/to/android-sdk \
  --java /path/to/jdk --gradle /path/to/gradle \
  --g2p-install /path/to/mobile-g2p-install
```

For an Android C/Rust plugin, use `tools/build_engine.py --target android-arm64 --profile arm64-auto --liquidcodec --speech` with the same source and installed toolchain. Distribute the entire installed `lib/` directory, including `libggml.so`, `libggml-base.so`, and all three CPU modules; the NDK C++ runtime must also be available. Keep the libraries together in the application native library directory.

The loader reports the selected module through `OrTTSCPU` logcat messages and the existing trace output. Missing or incompatible higher-level modules fall back to a supported lower level. An installation with no usable CPU module fails with an error.

Existing static Linux and Apple profiles remain available. Their library layout and public interfaces are unchanged. CPU module selection does not change model precision, KV settings, or enable an NPU backend.
