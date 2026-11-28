#pragma once
#include "ortts_speech.h"
#include "audiocpp.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <functional>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/**
 * Energy-gated segmented pseudo-streaming wrapper around offline `sense_asr`.
 * Enables bilingual zh/en incremental ASR callbacks via `ortts_asr_stream_*`
 * in standard `--speech` builds without external ONNX/Sherpa dependencies.
 */
class OrTTSSenseAsrStream {
 using Clock = std::chrono::steady_clock;
 audiocpp_registry* registry_ = nullptr;
 audiocpp_model* model_ = nullptr;
 audiocpp_session* session_ = nullptr;
 uint64_t received_ = 0;
 uint64_t start_ = 0;
 uint64_t segment_ = 0;
 uint64_t revision_ = 0;
 uint64_t updates_ = 0;
 uint64_t last_emit_ = 0;
 uint64_t peak_buffered_ = 0;
 uint64_t limit_ = 0;
 uint64_t update_frames_ = 0;
 uint64_t min_partial_frames_ = 0;
 uint64_t silence_frames_ = 0;
 uint64_t trailing_silent_frames_ = 0;
 float energy_threshold_ = 0.003f;
 std::vector<float> segment_pcm_;
 std::string last_;
 bool voiced_ = false;
 double decode_ms_ = 0.0;

 struct ReqOwner {
  audiocpp_request* p = audiocpp_request_create();
  ReqOwner() { if (!p) throw std::bad_alloc(); }
  ~ReqOwner() { audiocpp_request_free(p); }
 };
 struct ResOwner {
  audiocpp_result* p = nullptr;
  ~ResOwner() { audiocpp_result_free(p); }
 };
 struct OptOwner {
  audiocpp_options* p = audiocpp_options_create();
  OptOwner() { if (!p) throw std::bad_alloc(); }
  ~OptOwner() { audiocpp_options_free(p); }
 };

 static void check(audiocpp_status s) {
  if (s != AUDIOCPP_OK) throw std::runtime_error(audiocpp_last_error());
 }

 std::pair<std::string, std::string> recognize_segment() {
  if (segment_pcm_.empty() || !voiced_) return {"", "und"};
  bool silent = std::all_of(segment_pcm_.begin(), segment_pcm_.end(), [](float v) { return v == 0.0f; });
  if (silent) return {"", "und"};
  ReqOwner q;
  check(audiocpp_request_set_audio(q.p, segment_pcm_.data(), segment_pcm_.size(), 16000, 1));
  check(audiocpp_request_set_option(q.p, "audio_chunk_mode", "none"));
  ResOwner r;
  auto t0 = Clock::now();
  check(audiocpp_session_run(session_, q.p, &r.p));
  decode_ms_ += std::chrono::duration<double, std::milli>(Clock::now() - t0).count();
  ++updates_;
  const char* text = nullptr;
  const char* lang = nullptr;
  check(audiocpp_result_text(r.p, &text, &lang));
  return {text ? text : "", (lang && *lang) ? lang : "und"};
 }

 void reset_segment_state() {
  segment_pcm_.clear();
  voiced_ = false;
  trailing_silent_frames_ = 0;
  last_.clear();
  revision_ = 0;
  start_ = received_;
  last_emit_ = received_;
 }

 bool emit_event(
     int endpoint,
     const std::string& text,
     const std::string& lang,
     const std::function<bool(const ortts_asr_stream_event&)>& sink) {
  last_ = text;
  last_emit_ = received_;
  ortts_asr_stream_event e{
   sizeof(e),
   endpoint,
   segment_,
   start_,
   received_,
   ++revision_,
   text.c_str(),
   lang.empty() ? "und" : lang.c_str(),
  };
  return !sink(e);
 }

 bool end_segment(
     int reason,
     const std::function<bool(const ortts_asr_stream_event&)>& sink,
     const std::function<bool()>& cancel) {
  if (segment_pcm_.empty()) return true;
  if (cancel()) return false;
  if (!voiced_) {
   reset_segment_state();
   return true;
  }
  auto [txt, lang] = recognize_segment();
  if (cancel()) return false;
  if (reason == ORTTS_ASR_SILENCE && txt.empty()) {
   reset_segment_state();
   return true;
  }
  if (!emit_event(reason, txt, lang, sink)) return false;
  reset_segment_state();
  ++segment_;
  return true;
 }

public:
 OrTTSSenseAsrStream(
     const std::string& model_path,
     int threads,
     uint32_t max_ms,
     uint32_t update_ms,
     uint32_t min_partial_ms,
     uint32_t silence_ms,
     float energy_threshold)
     : limit_(uint64_t(max_ms) * 16),
       update_frames_(uint64_t(update_ms) * 16),
       min_partial_frames_(uint64_t(min_partial_ms) * 16),
       silence_frames_(uint64_t(silence_ms) * 16),
       energy_threshold_(energy_threshold) {
  if (!std::filesystem::exists(model_path)) {
   throw std::invalid_argument("Missing SenseVoice ASR model package");
  }
  try {
   check(audiocpp_registry_create(nullptr, &registry_));
   audiocpp_model_config mc{"sense_asr", nullptr, nullptr, nullptr};
   check(audiocpp_model_load(registry_, model_path.c_str(), &mc, nullptr, &model_));
   OptOwner opts;
   audiocpp_backend_config backend{"cpu", 0, threads};
   check(audiocpp_session_create(model_, "asr", "offline", &backend, opts.p, &session_));
  } catch (...) {
   audiocpp_session_free(session_);
   audiocpp_model_free(model_);
   audiocpp_registry_free(registry_);
   session_ = nullptr;
   model_ = nullptr;
   registry_ = nullptr;
   throw;
  }
 }

 ~OrTTSSenseAsrStream() {
  audiocpp_session_free(session_);
  audiocpp_model_free(model_);
  audiocpp_registry_free(registry_);
 }

 OrTTSSenseAsrStream(const OrTTSSenseAsrStream&) = delete;
 OrTTSSenseAsrStream& operator=(const OrTTSSenseAsrStream&) = delete;

 bool accept(
     const float* p,
     size_t n,
     const std::function<bool(const ortts_asr_stream_event&)>& sink,
     const std::function<bool()>& cancel) {
  if (!p || !n || n > 32000) throw std::invalid_argument("ASR input must contain 1..32000 samples");
  for (size_t i = 0; i < n; ++i) {
   if (!std::isfinite(p[i])) throw std::invalid_argument("Nonfinite ASR input");
  }
  for (size_t off = 0; off < n;) {
   if (cancel()) return false;
   const size_t avail = static_cast<size_t>(limit_ - segment_pcm_.size());
   const size_t count = std::min({size_t(320), n - off, avail});
   double sum_sq = 0.0;
   for (size_t i = 0; i < count; ++i) {
    const float s = p[off + i];
    sum_sq += double(s) * double(s);
   }
   const float rms = float(std::sqrt(sum_sq / double(count)));
   if (rms >= energy_threshold_) {
    voiced_ = true;
    trailing_silent_frames_ = 0;
   } else if (voiced_) {
    trailing_silent_frames_ += count;
   }
   segment_pcm_.insert(segment_pcm_.end(), p + off, p + off + count);
   peak_buffered_ = std::max<uint64_t>(peak_buffered_, uint64_t(segment_pcm_.size()));
   received_ += count;
   off += count;

   if (silence_frames_ > 0 && voiced_ && trailing_silent_frames_ >= silence_frames_) {
    if (!end_segment(ORTTS_ASR_SILENCE, sink, cancel)) return false;
    continue;
   }
   if (segment_pcm_.size() >= limit_) {
    if (!end_segment(ORTTS_ASR_LIMIT, sink, cancel)) return false;
    continue;
   }
   if (voiced_ &&
       (received_ - start_) >= min_partial_frames_ &&
       (received_ - last_emit_) >= update_frames_) {
    auto [txt, lang] = recognize_segment();
    if (cancel()) return false;
    if (!txt.empty() && txt != last_) {
     if (!emit_event(ORTTS_ASR_PARTIAL, txt, lang, sink)) return false;
    } else {
     last_emit_ = received_;
    }
   }
  }
  return true;
 }

 bool finish(
     const std::function<bool(const ortts_asr_stream_event&)>& sink,
     const std::function<bool()>& cancel) {
  return !cancel() && end_segment(ORTTS_ASR_FLUSH, sink, cancel);
 }

 void reset() {
  received_ = 0;
  start_ = 0;
  segment_ = 0;
  revision_ = 0;
  updates_ = 0;
  last_emit_ = 0;
  peak_buffered_ = 0;
  trailing_silent_frames_ = 0;
  decode_ms_ = 0.0;
  voiced_ = false;
  last_.clear();
  segment_pcm_.clear();
 }

 void stats(ortts_asr_stream_stats* out) const {
  *out = {
   sizeof(*out),
   received_,
   received_,
   uint64_t(segment_pcm_.size()),
   updates_,
   uint64_t(segment_pcm_.size()),
   UINT64_MAX,
   uint64_t(segment_pcm_.size()),
   peak_buffered_,
   UINT64_MAX,
   std::numeric_limits<double>::quiet_NaN(),
   decode_ms_,
  };
 }
};
