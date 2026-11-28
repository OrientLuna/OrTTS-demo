#include "ortts_engine.h"
#include "ortts_speech.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void require(bool ok, const char* msg) {
 if (!ok) throw std::runtime_error(msg);
}

void ok(ortts_status s, const char* ctx) {
 if (s != ORTTS_OK) {
  throw std::runtime_error(std::string(ctx) + ": " + (ortts_last_error() ? ortts_last_error() : "unknown"));
 }
}

uint64_t fnv1a_f32(const float* p, size_t n) {
 uint64_t h = 14695981039346656037ull;
 const uint8_t* b = reinterpret_cast<const uint8_t*>(p);
 for (size_t i = 0; i < n * sizeof(float); ++i) {
  h ^= b[i];
  h *= 1099511628211ull;
 }
 return h;
}

std::vector<float> read_f32_file(const std::string& path) {
 std::ifstream in(path, std::ios::binary | std::ios::ate);
 require(bool(in), ("Cannot open f32 file: " + path).c_str());
 std::streamsize bytes = in.tellg();
 require(bytes > 0 && bytes % sizeof(float) == 0, "Invalid f32 file size");
 std::vector<float> out(static_cast<size_t>(bytes) / sizeof(float));
 in.seekg(0);
 in.read(reinterpret_cast<char*>(out.data()), bytes);
 require(bool(in), "Short f32 read");
 return out;
}

std::vector<float> resample_linear_16k(const float* p, size_t frames, int rate) {
 require(p && frames > 0 && rate > 0, "Invalid PCM for resample");
 size_t out_n = static_cast<size_t>(double(frames) * 16000.0 / double(rate));
 std::vector<float> out(out_n);
 for (size_t i = 0; i < out_n; ++i) {
  double pos = double(i) * double(rate) / 16000.0;
  size_t a = std::min(size_t(pos), frames - 1);
  size_t b = std::min(a + 1, frames - 1);
  double t = pos - double(a);
  out[i] = static_cast<float>(p[a] * (1.0 - t) + p[b] * t);
 }
 return out;
}

struct StreamRecord {
 int endpoint;
 std::string text;
 std::string language;
};

int stream_cb(void* user, const ortts_asr_stream_event* ev) {
 auto* rec = static_cast<std::vector<StreamRecord>*>(user);
 rec->push_back({ev->endpoint, ev->text ? ev->text : "", ev->language ? ev->language : ""});
 return 0;
}

} // namespace

int main(int argc, char** argv) {
 try {
  std::string models_root = argc > 1 ? argv[1] : "/data/local/tmp/ortts_std_20261126/models";
  std::string own_root = models_root + "/serial";
  std::string speech_root = models_root + "/speech-models";
  const char* espeak_lib = std::getenv("AUDIOCPP_ESPEAK_LIBRARY");
  const char* espeak_data = std::getenv("AUDIOCPP_ESPEAK_DATA");

  require(ortts_abi_version() == 1, "ortts_abi_version != 1");
  require(ortts_engine_feature_version() == 2, "ortts_engine_feature_version != 2");
  require(ortts_speech_abi_version() == 1, "ortts_speech_abi_version != 1");
  require(ortts_asr_stream_abi_version() == 1, "ortts_asr_stream_abi_version != 1");
  require(ortts_parallel_inference_version() == 2, "ortts_parallel_inference_version != 2");

  const std::string cat = ortts_speech_catalog_json();
  require(cat.find("\"capabilities\"") != std::string::npos, "catalog missing capabilities");
  require(cat.find("\"ortts_qwen3_lfm\"") != std::string::npos, "catalog missing ortts_qwen3_lfm");
  require(cat.find("\"per_request_speaker\":true") != std::string::npos, "catalog missing per_request_speaker:true");
  require(cat.find("\"speed_control\":true") != std::string::npos, "catalog missing speed_control:true");
  require(cat.find("\"speed_control\":false") != std::string::npos, "catalog missing speed_control:false");
  require(cat.find("\"sense_asr\"") != std::string::npos, "catalog missing sense_asr");
  std::cout << "[PASS] ABI versions & self-describing catalog checks\n";

  // 1. P0: Per-request & engine-level speaker switching on one resident engine
  ortts_config cfg{};
  cfg.struct_size = sizeof(cfg);
  cfg.asset_root = own_root.c_str();
  cfg.variant = "P3";
  cfg.speaker_f32 = nullptr;
  cfg.bridge_manifest_sha256 = "78954b071cabd84e126a9a5e27ad5903cd10e574ae0509da5d7254e5023e2fd4";
  cfg.threads = 4;
  cfg.streaming = 1;

  ortts_engine* eng = nullptr;
  ok(ortts_engine_create(&cfg, &eng), "ortts_engine_create");

  const std::string female_path = own_root + "/voices/female.f32";
  const std::string male_path = own_root + "/voices/male.f32";
  auto female_vec = read_f32_file(female_path);
  auto male_vec = read_f32_file(male_path);

  auto run_own = [&](const char* spk_path, const float* spk_vec, size_t spk_dim, float speed) {
   ortts_request req{};
   req.struct_size = sizeof(req);
   req.text = "你好。";
   req.seed = 42;
   req.max_tokens = 128;
   req.speaker_f32 = spk_path;
   req.speaker_vector = spk_vec;
   req.speaker_dim = spk_dim;
   req.speed = speed;
   ortts_audio* audio = nullptr;
   ok(ortts_engine_synthesize(eng, &req, nullptr, nullptr, &audio), "ortts_engine_synthesize");
   uint64_t h = fnv1a_f32(ortts_audio_samples(audio), ortts_audio_sample_count(audio));
   size_t n = ortts_audio_sample_count(audio);
   ortts_audio_free(audio);
   return std::pair<uint64_t, size_t>{h, n};
  };

  auto [h_female, n_female] = run_own(nullptr, nullptr, 0, 0.0f);
  auto [h_male_path, n_male] = run_own(male_path.c_str(), nullptr, 0, 0.0f);
  require(h_female != h_male_path, "Per-request male.f32 produced identical PCM to female.f32");

  auto [h_male_vec, n_male_vec] = run_own(nullptr, male_vec.data(), male_vec.size(), 0.0f);
  require(h_male_vec == h_male_path && n_male_vec == n_male, "Per-request male vector did not match male.f32");

  auto [h_default_after, _n0] = run_own(nullptr, nullptr, 0, 0.0f);
  require(h_default_after == h_female, "Per-request override unexpectedly mutated engine default");

  // Speed ignored cleanly when valid, rejected when out of range
  auto [h_speed_ignored, _n1] = run_own(nullptr, nullptr, 0, 1.25f);
  require(h_speed_ignored == h_female, "Own model should safely ignore valid speed");
  {
   ortts_request bad_req{};
   bad_req.struct_size = sizeof(bad_req);
   bad_req.text = "你好。";
   bad_req.seed = 42;
   bad_req.max_tokens = 64;
   bad_req.speed = 3.0f;
   ortts_audio* bad = nullptr;
   require(ortts_engine_synthesize(eng, &bad_req, nullptr, nullptr, &bad) == ORTTS_INVALID, "Invalid speed > 2.0 must fail");
   ortts_audio_free(bad);
  }

  // Legacy ortts_request_v1 and v1.1 compatibility + v1.2 language routing
  {
   ortts_request_v1 v1_req{ORTTS_REQUEST_V1_SIZE, "你好。", 42, 128};
   ortts_audio* a_v1 = nullptr;
   ok(ortts_engine_synthesize(eng, reinterpret_cast<const ortts_request*>(&v1_req), nullptr, nullptr, &a_v1), "v1 struct synth");
   uint64_t h_v1 = fnv1a_f32(ortts_audio_samples(a_v1), ortts_audio_sample_count(a_v1));
   ortts_audio_free(a_v1);
   require(h_v1 == h_female, "v1 request struct parity mismatch");

   ortts_request_v1_1 v11_req{ORTTS_REQUEST_V1_1_SIZE, "你好。", 42, 128, nullptr, nullptr, 0, 0.0f};
   ortts_audio* a_v11 = nullptr;
   ok(ortts_engine_synthesize(eng, reinterpret_cast<const ortts_request*>(&v11_req), nullptr, nullptr, &a_v11), "v1.1 struct synth");
   uint64_t h_v11 = fnv1a_f32(ortts_audio_samples(a_v11), ortts_audio_sample_count(a_v11));
   ortts_audio_free(a_v11);
   require(h_v11 == h_female, "v1.1 request struct parity mismatch");

   ortts_request bad_lang_req{};
   bad_lang_req.struct_size = sizeof(bad_lang_req);
   bad_lang_req.text = "Hello.";
   bad_lang_req.seed = 42;
   bad_lang_req.max_tokens = 64;
   bad_lang_req.language = "Klingon";
   ortts_audio* bad_lang = nullptr;
   require(ortts_engine_synthesize(eng, &bad_lang_req, nullptr, nullptr, &bad_lang) == ORTTS_INVALID, "Invalid language must fail");
   ortts_audio_free(bad_lang);
  }

  // Engine-level set_speaker / set_speaker_vector
  ok(ortts_engine_set_speaker(eng, male_path.c_str()), "set_speaker(male)");
  auto [h_set_male, _n2] = run_own(nullptr, nullptr, 0, 0.0f);
  require(h_set_male == h_male_path, "set_speaker(male) mismatch");

  ok(ortts_engine_set_speaker_vector(eng, female_vec.data(), female_vec.size()), "set_speaker_vector(female)");
  auto [h_set_female, _n3] = run_own(nullptr, nullptr, 0, 0.0f);
  require(h_set_female == h_female, "set_speaker_vector(female) mismatch");

  ortts_engine_free(eng);
  std::cout << "[PASS] P0 Single-engine speaker hot-switching (path + vector + set_speaker + v1 compat): female="
            << n_female << " samples, male=" << n_male << " samples\n";

  // 2. P1 Speed on Kokoro TTS + capture Chinese PCM for streaming ASR
  std::vector<float> zh_speech_16k;
  {
   ortts_speech_config sc{};
   sc.struct_size = sizeof(sc);
   sc.family = "kokoro_tts";
   std::string kokoro_path = speech_root + "/Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf";
   sc.model_path = kokoro_path.c_str();
   sc.threads = 4;
   sc.streaming = 0;
   sc.espeak_library = espeak_lib;
   sc.espeak_data = espeak_data;
   ortts_tts* tts = nullptr;
   ok(ortts_tts_create(&sc, &tts), "kokoro create");

   auto synth_kokoro = [&](float speed) {
    ortts_tts_request tr{};
    tr.struct_size = sizeof(tr);
    tr.text = "请把蓝色文件夹送到三楼会议室。";
    tr.language = "zh";
    tr.voice_id = "zf_xiaobei";
    tr.seed_set = 1;
    tr.seed = 42;
    tr.speed = speed;
    ortts_speech_audio* out = nullptr;
    ok(ortts_tts_synthesize(tts, &tr, nullptr, nullptr, &out), "kokoro synth");
    size_t frames = ortts_speech_audio_frames(out);
    if (std::abs(speed - 1.0f) < 1e-4f) {
     zh_speech_16k = resample_linear_16k(
         ortts_speech_audio_samples(out), frames, ortts_speech_audio_sample_rate(out));
    }
    ortts_speech_audio_free(out);
    return frames;
   };
   size_t f_slow = synth_kokoro(0.75f);
   size_t f_norm = synth_kokoro(1.0f);
   size_t f_fast = synth_kokoro(1.5f);
   require(f_slow > f_norm && f_norm > f_fast, "Kokoro speed must yield monotonic durations");
   ortts_tts_free(tts);
   std::cout << "[PASS] P1 Kokoro speed control frames: 0.75x=" << f_slow
             << " > 1.0x=" << f_norm << " > 1.5x=" << f_fast << "\n";
  }

  // 3. P1 Speed on Piper + Pocket ignore/reject
  {
   ortts_speech_config sc{};
   sc.struct_size = sizeof(sc);
   sc.family = "piper_tts";
   std::string piper_path = speech_root + "/Piper-TTS-GGUF/piper-en-us-lessac-medium-orig.gguf";
   sc.model_path = piper_path.c_str();
   sc.threads = 4;
   sc.streaming = 0;
   sc.espeak_library = espeak_lib;
   sc.espeak_data = espeak_data;
   ortts_tts* tts = nullptr;
   ok(ortts_tts_create(&sc, &tts), "piper create");
   auto synth_piper = [&](float speed) {
    ortts_tts_request tr{};
    tr.struct_size = sizeof(tr);
    tr.text = "Please check the train schedule before leaving home.";
    tr.language = "en";
    tr.seed_set = 1;
    tr.seed = 42;
    tr.speed = speed;
    ortts_speech_audio* out = nullptr;
    ok(ortts_tts_synthesize(tts, &tr, nullptr, nullptr, &out), "piper synth");
    size_t frames = ortts_speech_audio_frames(out);
    ortts_speech_audio_free(out);
    return frames;
   };
   size_t f_slow = synth_piper(0.75f);
   size_t f_norm = synth_piper(1.0f);
   size_t f_fast = synth_piper(1.5f);
   require(f_slow > f_norm && f_norm > f_fast, "Piper speed must yield monotonic durations");
   ortts_tts_free(tts);
   std::cout << "[PASS] P1 Piper speed control frames: 0.75x=" << f_slow
             << " > 1.0x=" << f_norm << " > 1.5x=" << f_fast << "\n";
  }
  {
   ortts_speech_config sc{};
   sc.struct_size = sizeof(sc);
   sc.family = "pocket_tts";
   std::string pocket_path = speech_root + "/PocketTTS-GGUF/english/pocket-tts-english-q8_0.gguf";
   sc.model_path = pocket_path.c_str();
   sc.threads = 4;
   sc.streaming = 0;
   ortts_tts* tts = nullptr;
   ok(ortts_tts_create(&sc, &tts), "pocket create");
   ortts_tts_request tr{};
   tr.struct_size = sizeof(tr);
   tr.text = "Hello world.";
   tr.language = "en";
   tr.voice_id = "alba";
   tr.seed_set = 1;
   tr.seed = 42;
   tr.speed = 1.25f;
   ortts_speech_audio* out = nullptr;
   ok(ortts_tts_synthesize(tts, &tr, nullptr, nullptr, &out), "pocket speed ignore");
   ortts_speech_audio_free(out);
   tr.speed = 0.25f;
   require(ortts_tts_synthesize(tts, &tr, nullptr, nullptr, &out) == ORTTS_INVALID, "pocket invalid speed");
   ortts_tts_free(tts);
   std::cout << "[PASS] P1 Pocket speed ignore/reject\n";
  }

  // 4. P2 Bilingual streaming ASR: built-in sense_asr segmented stream + optional zipformer_bilingual
  std::vector<float> asr_input = zh_speech_16k;
  asr_input.resize(asr_input.size() + 16000, 0.0f); // 1.0s silence for ORTTS_ASR_SILENCE

  {
   std::string sense_path = speech_root + "/sensevoice-small-q8-audiocpp-v1.gguf";
   ortts_speech_config cfg_s{};
   cfg_s.struct_size = sizeof(cfg_s);
   cfg_s.family = "sense_asr";
   cfg_s.model_path = sense_path.c_str();
   cfg_s.threads = 4;
   cfg_s.streaming = 1;
   ortts_asr_stream_config scfg{sizeof(scfg), 600, 800, 15000, 600, 0.002f};
   ortts_asr_stream* stream = nullptr;
   ok(ortts_asr_stream_create(&cfg_s, &scfg, &stream), "sense_asr stream create");
   std::vector<StreamRecord> events;
   for (size_t off = 0; off < asr_input.size(); off += 3200) {
    size_t chunk = std::min(size_t(3200), asr_input.size() - off);
    ok(ortts_asr_stream_accept(stream, asr_input.data() + off, chunk, stream_cb, &events), "sense stream accept");
   }
   ok(ortts_asr_stream_finish(stream, stream_cb, &events), "sense stream finish");
   ortts_asr_stream_stats st{sizeof(st)};
   ok(ortts_asr_stream_get_stats(stream, &st), "sense stream stats");
   bool has_silence_final = std::any_of(events.begin(), events.end(), [](const StreamRecord& r) {
    return r.endpoint == ORTTS_ASR_SILENCE && !r.text.empty();
   });
   require(has_silence_final, "sense_asr segmented stream did not emit ORTTS_ASR_SILENCE final");
   std::string combined;
   for (const auto& r : events) {
    if (r.endpoint != ORTTS_ASR_PARTIAL && !r.text.empty()) combined += r.text;
   }
   require(combined.find("文件") != std::string::npos || combined.find("会议") != std::string::npos,
           ("Unexpected sense_asr transcript: " + combined).c_str());
   require(st.received_frames == asr_input.size() && st.peak_buffered_pcm_frames > 0, "Invalid sense stream stats");
   ortts_asr_stream_free(stream);
   std::cout << "[PASS] P2 sense_asr segmented streaming ASR events=" << events.size()
             << " transcript=\"" << combined << "\" peak_buf=" << st.peak_buffered_pcm_frames << "\n";
  }

  std::string zip_path = speech_root + "/asr-lite-zh-en-v1";
  if (std::filesystem::is_directory(zip_path)) {
   ortts_speech_config cfg_z{};
   cfg_z.struct_size = sizeof(cfg_z);
   cfg_z.family = "zipformer_bilingual";
   cfg_z.model_path = zip_path.c_str();
   cfg_z.threads = 4;
   cfg_z.streaming = 1;
   ortts_asr_stream_config scfg{sizeof(scfg), 400, 800, 15000, 600, 0.002f};
   ortts_asr_stream* stream = nullptr;
   ok(ortts_asr_stream_create(&cfg_z, &scfg, &stream), "zipformer_bilingual create");
   std::vector<StreamRecord> events;
   for (size_t off = 0; off < asr_input.size(); off += 3200) {
    size_t chunk = std::min(size_t(3200), asr_input.size() - off);
    ok(ortts_asr_stream_accept(stream, asr_input.data() + off, chunk, stream_cb, &events), "zipformer accept");
   }
   ok(ortts_asr_stream_finish(stream, stream_cb, &events), "zipformer finish");
   std::string combined;
   for (const auto& r : events) {
    if (r.endpoint != ORTTS_ASR_PARTIAL && !r.text.empty()) combined += r.text;
   }
   require(!combined.empty(), "zipformer_bilingual produced empty transcript");
   ortts_asr_stream_free(stream);
   std::cout << "[PASS] P2 zipformer_bilingual streaming ASR events=" << events.size()
             << " transcript=\"" << combined << "\"\n";
  }

  std::cout << "ALL_SDK_INCREMENTAL_CHECKS_PASSED\n";
  return 0;
 } catch (const std::exception& e) {
  std::cerr << "FAIL: " << e.what() << "\n";
  return 1;
 }
}
