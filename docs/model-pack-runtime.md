# Model packs

The CPU runtime supports P3 and P5 predictors with either Qwen–LFM or LiquidCodec acoustics. A pack selects its decoder; applications do not need separate runtime branches. Existing packs and the C ABI remain compatible.

For the unified backend, prepare the pinned local sources with `tools/prepare_unified_runtime.py --release-compat` and build with `--liquidcodec`. No SDK or model download is performed by these tools.

New packs use the existing `ortts-download-manifest-v1` file list and selection rules. Add the following runtime section to `model.json`:

```json
{
  "runtime": {
    "schema": "ortts-runtime-v1",
    "decoder": {
      "kind": "liquidcodec",
      "variant": "base",
      "manifest": "native/lc/runtime.json",
      "dequant_manifest": "native/dequant/MANIFEST.json"
    }
  }
}
```

Every file must have its actual byte length and SHA-256 in `files`. Common assets include the model GGUF, its original `native/config.json`, both voice vectors, the selected acoustic files and the dequant bundle. P3 adds `P3/predictor/{predictor.gguf,config.json,talker_config.json}`; P5 uses the predictor already included in the base model. Do not download both native and floating-point P3 copies. Existing safetensors packs remain supported.

Use each base model's own configuration, predictor heads, embeddings and projection. The 0.6B model uses 1024-value F32 speaker vectors; 1.7B uses its own 2048-value vectors. A shared reference recording does not make these vectors interchangeable. The runtime checks the configuration, vector length, finite values and native tensor shapes without padding.

`native/lc/runtime.json` selects `F32`, `MIXED_Q8_0` or `MIXED_Q4_0` and binds the actual core file SHA. Format support does not imply equal quality or performance on every model/device. Native Q8_0 text embeddings are supported through selected-row decoding; the full table stays quantized. Existing F32/F16/BF16 embeddings remain supported. The dequant bundle contains only the 16 official Qwen codebook tables and two projections. `tools/make_dequant_bundle.py` extracts these unchanged from a trusted local bundle and rejects payloads that differ from the reviewed table catalog. LiquidCodec packs using this bundle do not need the legacy LFM decoder weights.

The downloader and local ZIP importer use the same manifest. Keep shared acoustic and dequant files in the common download group. Existing default download addresses are unchanged.

A CPU offline invocation is:

```sh
ortts-tts --pack-root /path/to/model-pack --variant P3 \
  --speaker /path/to/model-pack/voices/female.f32 \
  --text '你好，欢迎使用语音合成。' --out /path/to/new-output \
  --threads 4 --seed 20261029 --repeats 1 --max-tokens 513
```

Use the C ABI's PCM callback or Android application for incremental playback. The CLI above returns a complete utterance. Preserve true EOS, one-frame lookahead and the final overlap-add flush; do not trim silence to report a lower RTF.

For C ABI callers, `bridge_manifest_sha256` holds the trusted SHA of the selected bridge or dequant `MANIFEST.json`. Its field name and ABI version stay unchanged. Use the SHA from the verified download manifest.
