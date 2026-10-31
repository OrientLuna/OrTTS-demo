#pragma once
#include <utility>

// Shared CPU inference defaults. Platform code owns assets, playback and UI.
namespace ortts::inference {
inline constexpr std::pair<const char*, const char*> environment_defaults[] = {
 {"ORTTS_FFN_PUREC_M1", "0"},
 {"ORTTS_NATIVE_PREDICTOR_PACKED", "0"},
 {"ORTTS_CPU_PERSISTENT_POOL", "0"},
 {"ORTTS_CPU_TCONV_GEMM", "1"},
 {"ORTTS_PRIVATE_FAST_BACKEND", "cpu"},
};
inline constexpr std::pair<const char*, const char*> session_defaults[] = {
 {"qwen3_tts.perf_mode", "off"},
 {"qwen3_tts.packed_projections", "false"},
 {"qwen3_tts.conv_weight_type", "f32"},
 {"qwen3_tts.speech_decoder_conv_weight_type", "f16"},
 {"qwen3_tts.codec_pipeline", "false"},
 {"qwen3_tts.cpu_chunk_frames", "0"},
 {"qwen3_tts.stitch_decode", "false"},
};
inline constexpr std::pair<const char*, const char*> request_defaults[] = {
 {"x_vector_only_mode", "true"},
 {"language", "Chinese"},
 {"do_sample", "true"},
 {"temperature", "0.9"},
 {"top_k", "50"},
 {"top_p", "0.9"},
 {"repetition_penalty", "1.05"},
 {"subtalker_do_sample", "false"},
};
} // namespace ortts::inference
