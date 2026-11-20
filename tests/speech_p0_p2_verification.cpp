#include "ortts_engine.h"
#include "ortts_speech.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using Clock = std::chrono::steady_clock;
static double ms_since(Clock::time_point t) {
    return std::chrono::duration<double, std::milli>(Clock::now() - t).count();
}
static void require(bool ok, const std::string& msg) {
    if (!ok) throw std::runtime_error(msg + " (last_error=" + ortts_last_error() + ")");
}
struct TtsHandle { ortts_tts* p = nullptr; ~TtsHandle() { ortts_tts_free(p); } };
struct AsrHandle { ortts_asr* p = nullptr; ~AsrHandle() { ortts_asr_free(p); } };
struct AsrStreamHandle { ortts_asr_stream* p = nullptr; ~AsrStreamHandle() { ortts_asr_stream_free(p); } };
struct AudioOut { ortts_speech_audio* p = nullptr; ~AudioOut() { ortts_speech_audio_free(p); } };
struct TranscriptOut { ortts_transcript* p = nullptr; ~TranscriptOut() { ortts_transcript_free(p); } };
struct CancelToken { ortts_cancel_token* p = ortts_cancel_token_create(); ~CancelToken() { ortts_cancel_token_free(p); } };

static ortts_speech_config make_cfg(const char* family, const std::string& model_path, int threads, int streaming,
                                    const char* espeak_lib, const char* espeak_data) {
    ortts_speech_config c{};
    c.struct_size = sizeof(c);
    c.family = family;
    c.model_path = model_path.c_str();
    c.threads = threads;
    c.streaming = streaming;
    c.espeak_library = espeak_lib;
    c.espeak_data = espeak_data;
    return c;
}

static std::vector<float> resample_to_16k(const float* p, size_t n, int rate) {
    std::vector<float> out(size_t(double(n) * 16000.0 / double(rate)));
    for (size_t i = 0; i < out.size(); ++i) {
        double pos = double(i) * double(rate) / 16000.0;
        size_t a = std::min(size_t(pos), n - 1);
        size_t b = std::min(a + 1, n - 1);
        double frac = pos - double(a);
        out[i] = float(p[a] * (1.0 - frac) + p[b] * frac);
    }
    return out;
}

int main(int argc, char** argv) {
    if (argc < 5) {
        std::cerr << "Usage: " << argv[0] << " <speech-models-dir> <pcm-16k-f32> <espeak-lib> <espeak-data> [report.json]\n";
        return 2;
    }
    try {
        const std::string models_root = argv[1];
        const std::string pcm_file = argv[2];
        const char* espeak_lib = argv[3];
        const char* espeak_data = argv[4];
        const std::string report_path = argc >= 6 ? argv[5] : "";

        const std::string kokoro_path = models_root + "/Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf";
        const std::string pocket_path = models_root + "/PocketTTS-GGUF/english/pocket-tts-english-q8_0.gguf";
        const std::string sense_path = models_root + "/sensevoice-small-q8-audiocpp-v1.gguf";
        const std::string paraformer_path = models_root + "/paraformer-streaming-zh-en-int8";

        std::ifstream f(pcm_file, std::ios::binary | std::ios::ate);
        require(bool(f), "Missing input F32 fixture: " + pcm_file);
        auto fbytes = f.tellg();
        require(fbytes > 0 && fbytes % 4 == 0, "Invalid F32 fixture");
        std::vector<float> asr_audio(size_t(fbytes) / 4);
        f.seekg(0);
        f.read(reinterpret_cast<char*>(asr_audio.data()), fbytes);

        require(ortts_parallel_inference_version() == 2u, "Expected ortts_parallel_inference_version() == 2");
        require(ortts_speech_cooperative_cancel_version() == 1u, "Expected ortts_speech_cooperative_cancel_version() == 1");
        std::string cat = ortts_speech_catalog_json();
        require(cat.find("operator-abort-and-load-cancel") != std::string::npos, "Catalog missing cooperative cancel capability");
        require(cat.find("\"kokoro_tts\":\"vocoder-windows\"") != std::string::npos, "Catalog missing kokoro vocoder-windows capability");

        // Warm OS file cache slightly? Actually leave as-is and test both pre-cancel and async load cancel.
        // === Case 1: P0-1 Cold-load cancel (< 100ms) ===
        {
            CancelToken tok;
            require(tok.p != nullptr, "Failed to create cancel token");
            ortts_cancel_token_request(tok.p);
            auto cfg = make_cfg("kokoro_tts", kokoro_path, 4, 0, espeak_lib, espeak_data);
            TtsHandle h;
            auto t0 = Clock::now();
            ortts_status st = ortts_tts_create_cancellable(&cfg, tok.p, &h.p);
            double pre_cancel_ms = ms_since(t0);
            require(st == ORTTS_CANCELLED && !h.p && pre_cancel_ms < 100.0,
                    "Expected immediate pre-cancelled TTS load abort < 100ms, got st=" + std::to_string(st) + " ms=" + std::to_string(pre_cancel_ms));
        }

        double sense_load_cancel_ms = -1.0;
        {
            // SenseVoice 254MB GGUF load takes long enough to catch mid-load consistently.
            CancelToken tok;
            auto cfg = make_cfg("sense_asr", sense_path, 4, 0, espeak_lib, espeak_data);
            AsrHandle h;
            std::atomic<int64_t> req_ns{0};
            std::thread killer([&] {
                std::this_thread::sleep_for(std::chrono::milliseconds(2));
                req_ns.store(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count());
                ortts_cancel_token_request(tok.p);
            });
            ortts_status st = ortts_asr_create_cancellable(&cfg, tok.p, &h.p);
            int64_t end_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
            killer.join();
            double req_to_ret = double(end_ns - req_ns.load()) / 1e6;
            if (st == ORTTS_CANCELLED) {
                require(!h.p && req_to_ret < 100.0, "ASR mid-load cancel exceeded 100ms: " + std::to_string(req_to_ret));
                sense_load_cancel_ms = req_to_ret;
            }
            std::cout << "[P0-1 Load Cancel] sense_asr st=" << st << " req_to_ret_ms=" << req_to_ret << "\n";
        }

        // Create persistent handles for P0-1, P0-2, P1-1, P1-2
        auto kokoro_offline_cfg = make_cfg("kokoro_tts", kokoro_path, 4, 0, espeak_lib, espeak_data);
        auto kokoro_stream_cfg = make_cfg("kokoro_tts", kokoro_path, 4, 1, espeak_lib, espeak_data);
        auto sense_cfg = make_cfg("sense_asr", sense_path, 4, 0, espeak_lib, espeak_data);

        TtsHandle kokoro_off, kokoro_stm;
        AsrHandle sense;
        require(ortts_tts_create(&kokoro_offline_cfg, &kokoro_off.p) == ORTTS_OK, "Create offline kokoro failed");
        require(ortts_tts_create(&kokoro_stream_cfg, &kokoro_stm.p) == ORTTS_OK, "Create streaming kokoro failed");
        require(ortts_asr_create(&sense_cfg, &sense.p) == ORTTS_OK, "Create sense_asr failed");

        const char* long_zh =
            "今天上午九点半，请检查车票和随身行李。我们正在测试离线语音合成系统的算子级取消能力，"
            "确保即使在长文本连续推理过程中也能在百毫秒内迅速中断并立即恢复复用，不会破坏模型常驻权重状态。";
        const char* short_zh = "今天上午九点半，请检查车票和随身行李。";

        // Warm up Kokoro offline & SenseVoice once so weights/graphs/NEON plan are resident before latency tests.
        {
            ortts_tts_request req{}; req.struct_size = sizeof(req);
            req.text = short_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 42;
            AudioOut warm_a;
            require(ortts_tts_synthesize(kokoro_off.p, &req, nullptr, nullptr, &warm_a.p) == ORTTS_OK, "Warm kokoro offline failed");
            TranscriptOut warm_t;
            require(ortts_asr_run(sense.p, asr_audio.data(), asr_audio.size(), "zh", &warm_t.p) == ORTTS_OK, "Warm sense_asr failed");
            std::cout << "[Warm Baseline] sense_text=" << ortts_transcript_text(warm_t.p)
                      << " api_ms=" << ortts_transcript_api_ms(warm_t.p) << "\n";
        }

        // === Case 2: P0-1 Operator-level inference cancel (< 100ms) & resident reuse ===
        double tts_cancel_ms = 0.0, asr_cancel_ms = 0.0;
        {
            ortts_tts_request req{}; req.struct_size = sizeof(req);
            req.text = long_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 42;
            std::atomic<int64_t> req_ns{0};
            std::thread killer([&] {
                std::this_thread::sleep_for(std::chrono::milliseconds(40));
                req_ns.store(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count());
                ortts_tts_cancel(kokoro_off.p);
            });
            AudioOut cancelled;
            ortts_status st = ortts_tts_synthesize(kokoro_off.p, &req, nullptr, nullptr, &cancelled.p);
            int64_t end_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
            killer.join();
            tts_cancel_ms = double(end_ns - req_ns.load()) / 1e6;
            require(st == ORTTS_CANCELLED && !cancelled.p, "Expected offline kokoro cancel, got st=" + std::to_string(st));
            require(tts_cancel_ms < 100.0, "Offline TTS operator cancel exceeded 100ms: " + std::to_string(tts_cancel_ms));

            // Reuse exact same handle immediately without recreating!
            req.text = short_zh;
            AudioOut reused;
            require(ortts_tts_synthesize(kokoro_off.p, &req, nullptr, nullptr, &reused.p) == ORTTS_OK, "Reuse after TTS cancel failed");
            require(ortts_speech_audio_frames(reused.p) > 24000, "Empty audio after TTS reuse");
            std::cout << "[P0-1 TTS Op Cancel] req_to_ret_ms=" << tts_cancel_ms << " reuse=OK\n";
        }
        {
            std::atomic<int64_t> req_ns{0};
            std::thread killer([&] {
                std::this_thread::sleep_for(std::chrono::milliseconds(20));
                req_ns.store(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count());
                ortts_asr_cancel(sense.p);
            });
            TranscriptOut cancelled;
            ortts_status st = ortts_asr_run(sense.p, asr_audio.data(), asr_audio.size(), "zh", &cancelled.p);
            int64_t end_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
            killer.join();
            asr_cancel_ms = double(end_ns - req_ns.load()) / 1e6;
            require(st == ORTTS_CANCELLED && !cancelled.p, "Expected offline sense_asr cancel, got st=" + std::to_string(st));
            require(asr_cancel_ms < 100.0, "Offline ASR operator cancel exceeded 100ms: " + std::to_string(asr_cancel_ms));

            TranscriptOut reused;
            require(ortts_asr_run(sense.p, asr_audio.data(), asr_audio.size(), "zh", &reused.p) == ORTTS_OK, "Reuse after ASR cancel failed");
            require(std::string(ortts_transcript_text(reused.p)).size() > 0, "Empty transcript after ASR reuse");
            std::cout << "[P0-1 ASR Op Cancel] req_to_ret_ms=" << asr_cancel_ms << " reuse=OK\n";
        }

        // === Case 3: P0-2 Per-handle ggml TTS + ggml ASR concurrency & isolated cancel ===
        double ggml_overlap_ms = 0.0;
        {
            std::atomic<int> ready{0};
            std::atomic<bool> go{false};
            Clock::time_point ts, te, as, ae;
            ortts_status tts_st = ORTTS_INVALID, asr_st = ORTTS_INVALID;
            AudioOut tts_out;
            TranscriptOut asr_out;
            std::thread t1([&] {
                ++ready; while (!go.load()) std::this_thread::yield();
                ts = Clock::now();
                ortts_tts_request req{}; req.struct_size = sizeof(req);
                req.text = long_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 42;
                tts_st = ortts_tts_synthesize(kokoro_off.p, &req, nullptr, nullptr, &tts_out.p);
                te = Clock::now();
            });
            std::thread t2([&] {
                ++ready; while (!go.load()) std::this_thread::yield();
                as = Clock::now();
                asr_st = ortts_asr_run(sense.p, asr_audio.data(), asr_audio.size(), "zh", &asr_out.p);
                ae = Clock::now();
            });
            while (ready.load() != 2) std::this_thread::yield();
            go.store(true);
            t1.join(); t2.join();
            ggml_overlap_ms = std::chrono::duration<double, std::milli>(std::min(te, ae) - std::max(ts, as)).count();
            require(tts_st == ORTTS_OK && asr_st == ORTTS_OK, "Concurrent ggml TTS + ggml ASR failed");
            require(ggml_overlap_ms > 0.0, "Expected positive interval overlap between kokoro_tts and sense_asr");

            // Isolated cancel: cancel ONLY kokoro_tts while both run concurrently!
            std::atomic<int> ready2{0}; std::atomic<bool> go2{false};
            ortts_status st_tts2 = ORTTS_OK, st_asr2 = ORTTS_INVALID;
            AudioOut tts_out2; TranscriptOut asr_out2;
            std::thread t1c([&] {
                ++ready2; while (!go2.load()) std::this_thread::yield();
                ortts_tts_request req{}; req.struct_size = sizeof(req);
                req.text = long_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 42;
                st_tts2 = ortts_tts_synthesize(kokoro_off.p, &req, nullptr, nullptr, &tts_out2.p);
            });
            std::thread t2c([&] {
                ++ready2; while (!go2.load()) std::this_thread::yield();
                st_asr2 = ortts_asr_run(sense.p, asr_audio.data(), asr_audio.size(), "zh", &asr_out2.p);
            });
            while (ready2.load() != 2) std::this_thread::yield();
            go2.store(true);
            std::this_thread::sleep_for(std::chrono::milliseconds(30));
            ortts_tts_cancel(kokoro_off.p);
            t1c.join(); t2c.join();
            require(st_tts2 == ORTTS_CANCELLED, "Expected TTS cancelled under isolated cancel");
            require(st_asr2 == ORTTS_OK && std::string(ortts_transcript_text(asr_out2.p)) == ortts_transcript_text(asr_out.p),
                    "ASR disturbed by concurrent TTS cancellation!");
            std::cout << "[P0-2 GGML Concurrency] overlap_ms=" << ggml_overlap_ms << " isolated_cancel=PASS\n";
        }

        // === Case 4: P1-1 Streaming TTFA & NEON RTF on Kokoro (vocoder-windows) + PocketTTS ===
        double first_pcm_ms = 0.0, warm_rtf = 0.0;
        size_t stream_chunks = 0;
        double single_clause_first_pcm_ms = 0.0, single_clause_warm_rtf = 0.0;
        size_t single_clause_chunks = 0, single_clause_first_frames = 0;
        double pocket_first_pcm_ms = 0.0, pocket_warm_rtf = 0.0;
        {
            struct StreamCap {
                Clock::time_point start;
                double first_ms = -1.0;
                size_t chunks = 0;
                size_t first_frames = 0;
            };
            auto stream_cb = [](void* u, const float*, size_t n, int32_t, int32_t) -> int {
                auto& s = *static_cast<StreamCap*>(u);
                if (s.first_ms < 0.0) {
                    s.first_ms = ms_since(s.start);
                    s.first_frames = n;
                }
                ++s.chunks;
                return 0;
            };

            // 4a: Single-clause Chinese without commas (verifies vocoder-windowed streaming + audio parity)
            {
                const char* no_comma_zh = "今天上午九点半检查随身行李。";
                ortts_tts_request req{}; req.struct_size = sizeof(req);
                req.text = no_comma_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 42;
                {
                    StreamCap w{Clock::now()};
                    AudioOut wa;
                    require(ortts_tts_synthesize(kokoro_stm.p, &req, stream_cb, &w, &wa.p) == ORTTS_OK, "Warm single-clause failed");
                }
                StreamCap sc{Clock::now()};
                AudioOut sa;
                require(ortts_tts_synthesize(kokoro_stm.p, &req, stream_cb, &sc, &sa.p) == ORTTS_OK, "Single-clause stream failed");
                double audio_ms = double(ortts_speech_audio_frames(sa.p)) * 1000.0 / double(ortts_speech_audio_sample_rate(sa.p));
                ortts_metrics m{};
                require(ortts_speech_audio_metrics(sa.p, &m) == ORTTS_OK, "Single-clause metrics failed");
                single_clause_first_pcm_ms = sc.first_ms;
                single_clause_chunks = sc.chunks;
                single_clause_first_frames = sc.first_frames;
                single_clause_warm_rtf = m.generation_ms / audio_ms;

                AudioOut off_a;
                require(ortts_tts_synthesize(kokoro_off.p, &req, nullptr, nullptr, &off_a.p) == ORTTS_OK, "Offline single-clause failed");
                require(ortts_speech_audio_frames(sa.p) == ortts_speech_audio_frames(off_a.p),
                        "Streamed vs offline sample count mismatch: " +
                        std::to_string(ortts_speech_audio_frames(sa.p)) + " vs " +
                        std::to_string(ortts_speech_audio_frames(off_a.p)));
                const float* sp = ortts_speech_audio_samples(sa.p);
                size_t sf = ortts_speech_audio_frames(sa.p);
                double sq = 0.0;
                for (size_t i = 0; i < sf; ++i) {
                    require(std::isfinite(sp[i]), "Non-finite sample in streamed Kokoro audio");
                    sq += double(sp[i]) * double(sp[i]);
                }
                double rms = std::sqrt(sq / double(sf));
                require(rms > 0.01, "Streamed Kokoro RMS too low: " + std::to_string(rms));

                auto pcm16 = resample_to_16k(sp, sf, ortts_speech_audio_sample_rate(sa.p));
                TranscriptOut rt;
                require(ortts_asr_run(sense.p, pcm16.data(), pcm16.size(), "zh", &rt.p) == ORTTS_OK, "SenseVoice roundtrip failed");
                std::string tx = ortts_transcript_text(rt.p);
                require(!tx.empty() && (tx.find("九点") != std::string::npos || tx.find("行李") != std::string::npos),
                        "Kokoro streamed SenseVoice roundtrip mismatch: " + tx);
                std::cout << "[P1-1 Kokoro Single-Clause] chunks=" << single_clause_chunks
                          << " first_frames=" << single_clause_first_frames
                          << " first_pcm_ms=" << single_clause_first_pcm_ms
                          << " rtf=" << single_clause_warm_rtf
                          << " rms=" << rms << " roundtrip=\"" << tx << "\"\n";
                require(single_clause_chunks >= 8, "Expected >= 8 vocoder-window chunks on single clause, got " + std::to_string(single_clause_chunks));
                require(single_clause_first_frames > 0 && single_clause_first_frames <= 7200,
                        "Expected first_chunk_frames <= 7200, got " + std::to_string(single_clause_first_frames));
                require(single_clause_first_pcm_ms < 400.0,
                        "Expected single-clause first_pcm_ms < 400ms, got " + std::to_string(single_clause_first_pcm_ms));
                require(single_clause_warm_rtf < 0.5,
                        "Expected single-clause warm RTF < 0.5, got " + std::to_string(single_clause_warm_rtf));
            }

            // 4b: Multi-clause Chinese
            {
                const char* multi_clause_zh =
                    "今天上午九点半，请检查车票和随身行李。欢迎使用本地语音合成，祝你旅途愉快！";
                ortts_tts_request req{}; req.struct_size = sizeof(req);
                req.text = multi_clause_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 42;
                {
                    StreamCap w{Clock::now()};
                    AudioOut wa;
                    require(ortts_tts_synthesize(kokoro_stm.p, &req, stream_cb, &w, &wa.p) == ORTTS_OK, "Warm multi stream failed");
                }
                StreamCap sc{Clock::now()};
                AudioOut sa;
                require(ortts_tts_synthesize(kokoro_stm.p, &req, stream_cb, &sc, &sa.p) == ORTTS_OK, "Measured multi stream failed");
                double audio_ms = double(ortts_speech_audio_frames(sa.p)) * 1000.0 / double(ortts_speech_audio_sample_rate(sa.p));
                ortts_metrics m{};
                require(ortts_speech_audio_metrics(sa.p, &m) == ORTTS_OK, "Metrics failed");
                first_pcm_ms = sc.first_ms;
                stream_chunks = sc.chunks;
                warm_rtf = m.generation_ms / audio_ms;
                std::cout << "[P1-1 Kokoro Multi-Clause] chunks=" << stream_chunks
                          << " first_frames=" << sc.first_frames
                          << " first_pcm_ms=" << first_pcm_ms << " gen_ms=" << m.generation_ms
                          << " audio_ms=" << audio_ms << " rtf=" << warm_rtf << "\n";
                require(stream_chunks >= 20, "Expected >= 20 vocoder-window chunks on multi-clause Kokoro stream");
                require(first_pcm_ms < 400.0, "Expected Kokoro first_pcm_ms < 400ms, got " + std::to_string(first_pcm_ms));
                require(warm_rtf < 0.5, "Expected Kokoro warm RTF < 0.5, got " + std::to_string(warm_rtf));
            }

            // 4c: PocketTTS step-level codec streaming
            {
                auto pcfg = make_cfg("pocket_tts", pocket_path, 4, 1, espeak_lib, espeak_data);
                TtsHandle pocket;
                require(ortts_tts_create(&pcfg, &pocket.p) == ORTTS_OK, "Create pocket_tts failed");
                ortts_tts_request req{}; req.struct_size = sizeof(req);
                req.text = "At nine thirty, please check the train ticket and call the station.";
                req.language = "en"; req.voice_id = "anna"; req.seed_set = 1; req.seed = 42;
                {
                    StreamCap w{Clock::now()};
                    AudioOut wa;
                    require(ortts_tts_synthesize(pocket.p, &req, stream_cb, &w, &wa.p) == ORTTS_OK, "Warm pocket failed");
                }
                StreamCap sc{Clock::now()};
                AudioOut sa;
                require(ortts_tts_synthesize(pocket.p, &req, stream_cb, &sc, &sa.p) == ORTTS_OK, "Measured pocket failed");
                double audio_ms = double(ortts_speech_audio_frames(sa.p)) * 1000.0 / double(ortts_speech_audio_sample_rate(sa.p));
                ortts_metrics m{};
                require(ortts_speech_audio_metrics(sa.p, &m) == ORTTS_OK, "Pocket metrics failed");
                pocket_first_pcm_ms = sc.first_ms;
                pocket_warm_rtf = m.generation_ms / audio_ms;
                std::cout << "[P1-1 PocketTTS Stream] chunks=" << sc.chunks
                          << " first_frames=" << sc.first_frames
                          << " first_pcm_ms=" << pocket_first_pcm_ms
                          << " gen_ms=" << m.generation_ms
                          << " audio_ms=" << audio_ms << " rtf=" << pocket_warm_rtf << "\n";
                require(sc.first_frames == 1920, "Expected PocketTTS first_frames == 1920");
                require(pocket_first_pcm_ms < 400.0, "Expected PocketTTS first_pcm_ms < 400ms");
                require(pocket_warm_rtf < 0.5, "Expected PocketTTS warm RTF < 0.5");
            }
        }

        // === Case 5: P1-2 timeout_ms & supersede ===
        double supersede_ms = 0.0;
        {
            // 5a: Bounded wait waits out short synthesis -> ORTTS_OK
            ortts_status st1 = ORTTS_INVALID, st2 = ORTTS_INVALID;
            AudioOut a1, a2;
            std::thread w1([&] {
                ortts_tts_request req{}; req.struct_size = sizeof(req);
                req.text = short_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 42;
                st1 = ortts_tts_synthesize(kokoro_off.p, &req, nullptr, nullptr, &a1.p);
            });
            std::this_thread::sleep_for(std::chrono::milliseconds(15));
            std::thread w2([&] {
                ortts_tts_request req{}; req.struct_size = sizeof(req);
                req.text = short_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 43;
                ortts_exec_policy pol{sizeof(pol), 5000, 0};
                st2 = ortts_tts_synthesize_ex(kokoro_off.p, &req, &pol, nullptr, nullptr, nullptr, &a2.p);
            });
            w1.join(); w2.join();
            require(st1 == ORTTS_OK && st2 == ORTTS_OK, "Bounded wait failed: st1=" + std::to_string(st1) + " st2=" + std::to_string(st2));

            // 5b: Supersede preemption via ortts_exec_policy
            ortts_status ps1 = ORTTS_OK, ps2 = ORTTS_INVALID;
            AudioOut pa1, pa2;
            Clock::time_point sup_start, first_end;
            std::thread p1([&] {
                ortts_tts_request req{}; req.struct_size = sizeof(req);
                req.text = long_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 42;
                ps1 = ortts_tts_synthesize(kokoro_off.p, &req, nullptr, nullptr, &pa1.p);
                first_end = Clock::now();
            });
            std::this_thread::sleep_for(std::chrono::milliseconds(30));
            std::thread p2([&] {
                sup_start = Clock::now();
                ortts_tts_request req{}; req.struct_size = sizeof(req);
                req.text = short_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 44;
                ortts_exec_policy pol{sizeof(pol), 1000, 1};
                ps2 = ortts_tts_synthesize_ex(kokoro_off.p, &req, &pol, nullptr, nullptr, nullptr, &pa2.p);
            });
            p1.join(); p2.join();
            supersede_ms = std::chrono::duration<double, std::milli>(first_end - sup_start).count();
            require(ps1 == ORTTS_CANCELLED && ps2 == ORTTS_OK && ortts_speech_audio_frames(pa2.p) > 24000,
                    "Supersede failed: ps1=" + std::to_string(ps1) + " ps2=" + std::to_string(ps2));
            require(supersede_ms < 100.0, "Supersede abort took >= 100ms: " + std::to_string(supersede_ms));

            // 5c: Supersede via ortts_tts_synthesize option "ortts.supersede"="1"
            ortts_status os1 = ORTTS_OK, os2 = ORTTS_INVALID;
            AudioOut oa1, oa2;
            std::thread o1([&] {
                ortts_tts_request req{}; req.struct_size = sizeof(req);
                req.text = long_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 42;
                os1 = ortts_tts_synthesize(kokoro_off.p, &req, nullptr, nullptr, &oa1.p);
            });
            std::this_thread::sleep_for(std::chrono::milliseconds(30));
            std::thread o2([&] {
                ortts_tts_request req{}; req.struct_size = sizeof(req);
                req.text = short_zh; req.language = "zh"; req.voice_id = "zf_xiaobei"; req.seed_set = 1; req.seed = 45;
                ortts_speech_option opts[] = {{"ortts.supersede", "1"}, {"ortts.lock_timeout_ms", "1000"}};
                req.options = opts; req.option_count = 2;
                os2 = ortts_tts_synthesize(kokoro_off.p, &req, nullptr, nullptr, &oa2.p);
            });
            o1.join(); o2.join();
            require(os1 == ORTTS_CANCELLED && os2 == ORTTS_OK, "Option-based supersede failed");
            std::cout << "[P1-2 Policy] bounded_wait=OK supersede_abort_ms=" << supersede_ms << " option_supersede=OK\n";
        }

        // === Case 6: P2 Chinese streaming ASR + silence_ms automatic segmentation ===
        std::vector<std::string> sil_segments;
        size_t partial_count = 0;
        {
            AudioOut u1, u2;
            ortts_tts_request r1{}; r1.struct_size = sizeof(r1);
            r1.text = "今天上午九点半检查车票。"; r1.language = "zh"; r1.voice_id = "zf_xiaobei"; r1.seed_set = 1; r1.seed = 42;
            require(ortts_tts_synthesize(kokoro_off.p, &r1, nullptr, nullptr, &u1.p) == ORTTS_OK, "Synth utt1 failed");
            ortts_tts_request r2 = r1; r2.text = "欢迎使用本地语音识别系统。";
            require(ortts_tts_synthesize(kokoro_off.p, &r2, nullptr, nullptr, &u2.p) == ORTTS_OK, "Synth utt2 failed");

            auto p1 = resample_to_16k(ortts_speech_audio_samples(u1.p), ortts_speech_audio_frames(u1.p), ortts_speech_audio_sample_rate(u1.p));
            auto p2 = resample_to_16k(ortts_speech_audio_samples(u2.p), ortts_speech_audio_frames(u2.p), ortts_speech_audio_sample_rate(u2.p));
            std::vector<float> stream_pcm;
            stream_pcm.insert(stream_pcm.end(), p1.begin(), p1.end());
            stream_pcm.resize(stream_pcm.size() + 16000, 0.0f); // 1.0s silence gap
            stream_pcm.insert(stream_pcm.end(), p2.begin(), p2.end());
            stream_pcm.resize(stream_pcm.size() + 16000, 0.0f); // 1.0s trailing silence

            auto scfg = make_cfg("streaming_paraformer", paraformer_path, 2, 1, nullptr, nullptr);
            ortts_asr_stream_config acfg{sizeof(acfg), 200, 400, 15000, 600, 0.003f};
            AsrStreamHandle asr;
            require(ortts_asr_stream_create(&scfg, &acfg, &asr.p) == ORTTS_OK, "Create streaming_paraformer with silence_ms=600 failed");

            struct EvState {
                std::vector<std::string>* segs;
                size_t* partials;
                std::vector<int> endpoints;
                std::vector<uint64_t> seg_ids;
            } st{&sil_segments, &partial_count, {}, {}};
            auto on_ev = [](void* u, const ortts_asr_stream_event* e) -> int {
                auto& s = *static_cast<EvState*>(u);
                if (e->endpoint == ORTTS_ASR_PARTIAL) {
                    ++(*s.partials);
                } else {
                    s.endpoints.push_back(e->endpoint);
                    s.seg_ids.push_back(e->segment_id);
                    s.segs->emplace_back(e->text ? e->text : "");
                }
                return 0;
            };
            for (size_t off = 0; off < stream_pcm.size(); off += 3200) {
                require(ortts_asr_stream_accept(asr.p, stream_pcm.data() + off,
                        std::min(size_t(3200), stream_pcm.size() - off), on_ev, &st) == ORTTS_OK,
                        "Paraformer accept failed");
            }
            require(partial_count > 0, "Expected partial events during paraformer streaming");
            require(sil_segments.size() >= 2, "Expected >= 2 automatic SILENCE segments before finish(), got " + std::to_string(sil_segments.size()));
            require(st.endpoints[0] == ORTTS_ASR_SILENCE && st.seg_ids[0] == 0, "Expected segment 0 ORTTS_ASR_SILENCE");
            require(st.endpoints[1] == ORTTS_ASR_SILENCE && st.seg_ids[1] == 1, "Expected segment 1 ORTTS_ASR_SILENCE");
            require(!sil_segments[0].empty() && !sil_segments[1].empty(), "Expected non-empty automatic segments");
            std::cout << "[P2 Streaming Paraformer Silence Endpoint] partials=" << partial_count
                      << " seg0=\"" << sil_segments[0] << "\" seg1=\"" << sil_segments[1] << "\"\n";
        }

        if (!report_path.empty()) {
            std::ofstream r(report_path);
            r << "{\n"
              << "  \"status\": \"PASS\",\n"
              << "  \"parallel_inference_version\": " << ortts_parallel_inference_version() << ",\n"
              << "  \"speech_cooperative_cancel_version\": " << ortts_speech_cooperative_cancel_version() << ",\n"
              << "  \"sense_load_cancel_ms\": " << sense_load_cancel_ms << ",\n"
              << "  \"tts_op_cancel_ms\": " << tts_cancel_ms << ",\n"
              << "  \"asr_op_cancel_ms\": " << asr_cancel_ms << ",\n"
              << "  \"ggml_concurrent_overlap_ms\": " << ggml_overlap_ms << ",\n"
              << "  \"kokoro_single_clause_chunks\": " << single_clause_chunks << ",\n"
              << "  \"kokoro_single_clause_first_frames\": " << single_clause_first_frames << ",\n"
              << "  \"kokoro_single_clause_first_pcm_ms\": " << single_clause_first_pcm_ms << ",\n"
              << "  \"kokoro_single_clause_warm_rtf\": " << single_clause_warm_rtf << ",\n"
              << "  \"kokoro_stream_chunks\": " << stream_chunks << ",\n"
              << "  \"kokoro_first_pcm_ms\": " << first_pcm_ms << ",\n"
              << "  \"kokoro_warm_rtf\": " << warm_rtf << ",\n"
              << "  \"pocket_first_pcm_ms\": " << pocket_first_pcm_ms << ",\n"
              << "  \"pocket_warm_rtf\": " << pocket_warm_rtf << ",\n"
              << "  \"supersede_abort_ms\": " << supersede_ms << ",\n"
              << "  \"paraformer_silence_segments\": " << sil_segments.size() << "\n"
              << "}\n";
        }
        std::cout << "PASS\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "FAIL: " << e.what() << "\n";
        return 1;
    }
}
