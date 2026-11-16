// Optional App QA entry. Exercises real TTS/ASR handles on distinct threads.
// Holding a PCM/text callback proves the first operation still owns the gate.
#include "ortts_engine.h"
#include "ortts_speech.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <fstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
void check(ortts_status status) {
    if (status != ORTTS_OK) throw std::runtime_error(ortts_last_error());
}
struct State {
    ortts_engine* tts = nullptr;
    ortts_asr_stream* asr = nullptr;
    bool attempt_asr = false, attempt_tts = false;
    int asr_during_tts = -1, tts_during_asr = -1;
    size_t pcm_frames = 0;
    std::string text;
    std::vector<float> tts_pcm;
    int same_tts = -1, same_asr = -1;
    bool cancel_tts = false, cancel_asr = false;
};
int text_event(void* user, const ortts_asr_stream_event* event) {
    auto& s = *static_cast<State*>(user);
    ortts_asr_stream_stats stats{}; stats.struct_size = sizeof(stats);
    s.same_asr = ortts_asr_stream_get_stats(s.asr, &stats);
    if (event->endpoint && event->text) s.text += event->text;
    if (s.attempt_tts) {
        s.attempt_tts = false;
        std::thread worker([&] {
            ortts_request r{sizeof(r), "Hello.", 42, 32};
            ortts_audio* output = nullptr;
            s.tts_during_asr = ortts_engine_synthesize(s.tts, &r, nullptr, nullptr, &output);
            ortts_audio_free(output);
        });
        worker.join();
    }
    return s.cancel_asr ? 1 : 0;
}
int pcm_event(void* user, const float*, size_t frames, int32_t) {
    auto& s = *static_cast<State*>(user);
    ortts_request busy_req{sizeof(busy_req), "Hello.", 42, 32};
    ortts_audio* other = nullptr;
    s.same_tts = ortts_engine_synthesize(s.tts, &busy_req, nullptr, nullptr, &other);
    ortts_audio_free(other);
    s.pcm_frames += frames;
    if (s.attempt_asr) {
        s.attempt_asr = false;
        std::thread worker([&] {
            float silence[1600]{};
            s.asr_during_tts = ortts_asr_stream_accept(s.asr, silence, 1600, text_event, &s);
        });
        worker.join();
    }
    return s.cancel_tts ? 1 : 0;
}
}
extern "C" int ortts_app_concurrency_check(const char* models, const char* asr_root, const char* input, const char* report) {
    State s;
    bool recovery_tts = false, recovery_asr = false;
    try {
        std::ifstream file(input, std::ios::binary | std::ios::ate);
        if (!file) throw std::runtime_error("Missing F32 fixture");
        std::streamoff bytes = file.tellg();
        if (bytes <= 0 || bytes % 4 || bytes > 16000 * 60 * 4) throw std::runtime_error("Invalid fixture");
        std::vector<float> pcm(size_t(bytes) / 4);
        file.seekg(0);
        if (!file.read(reinterpret_cast<char*>(pcm.data()), bytes)) throw std::runtime_error("Incomplete fixture");
        ortts_config cfg{}; cfg.struct_size = sizeof(cfg); cfg.asset_root = models; cfg.variant = "P3";
        std::string speaker = std::string(models) + "/voices/female.f32"; cfg.speaker_f32 = speaker.c_str();
        cfg.bridge_manifest_sha256 = "78954b071cabd84e126a9a5e27ad5903cd10e574ae0509da5d7254e5023e2fd4";
        cfg.threads = 2; cfg.streaming = 1;
        check(ortts_engine_create(&cfg, &s.tts));
        ortts_speech_config asr{}; asr.struct_size = sizeof(asr); asr.family = "streaming_paraformer";
        asr.model_path = asr_root; asr.threads = 2; asr.streaming = 1;
        ortts_asr_stream_config stream{sizeof(stream), 200, 400, 15000, 0, .003f};
        check(ortts_asr_stream_create(&asr, &stream, &s.asr));
        auto synthesize = [&] {
            ortts_request request{sizeof(request), "你好，欢迎使用本地语音合成。", 42, 128};
            ortts_audio* output = nullptr;
            auto status = ortts_engine_synthesize(s.tts, &request, pcm_event, &s, &output);
            bool nonempty = output && ortts_audio_sample_count(output) > 0;
            if (nonempty) s.tts_pcm.assign(ortts_audio_samples(output),ortts_audio_samples(output)+ortts_audio_sample_count(output));
            ortts_audio_free(output); check(status);
            if (!nonempty) throw std::runtime_error("Empty TTS output");
        };
        s.attempt_asr = true; synthesize();
        if (s.asr_during_tts != ORTTS_OK) throw std::runtime_error("ASR should execute while TTS owns ggml gate");
        const auto reference_pcm = s.tts_pcm;
        check(ortts_asr_stream_reset(s.asr)); s.attempt_tts = true;
        for (size_t i = 0; i < pcm.size(); i += 1600)
            check(ortts_asr_stream_accept(s.asr, pcm.data()+i, std::min(size_t(1600),pcm.size()-i),text_event,&s));
        check(ortts_asr_stream_finish(s.asr, text_event, &s));
        if (s.tts_during_asr != ORTTS_OK) throw std::runtime_error("TTS should execute while ASR owns Sherpa gate");
        if (s.same_tts != ORTTS_BUSY || s.same_asr != ORTTS_BUSY) throw std::runtime_error("Same-domain gate was lost");
        const std::string reference_text = s.text;
        // Free-running real inference, not just a held callback. Start both
        // workers together and require overlapping API intervals AND unchanged
        // deterministic outputs against the preceding sequential reference.
        using Clock=std::chrono::steady_clock;
        double overlap_ms=0;
        auto recognize = [&] {
            check(ortts_asr_stream_reset(s.asr));s.text.clear();
            for(size_t i=0;i<pcm.size();i+=1600)check(ortts_asr_stream_accept(s.asr,pcm.data()+i,std::min(size_t(1600),pcm.size()-i),text_event,&s));
            check(ortts_asr_stream_finish(s.asr,text_event,&s));
        };
        for(int repetition=0;repetition<3;++repetition){
            std::atomic<int>ready{0};std::atomic<bool>go{false};
            Clock::time_point ts,te,as,ae;std::exception_ptr tts_error,asr_error;
            std::thread tts([&]{++ready;while(!go.load())std::this_thread::yield();ts=Clock::now();try{synthesize();}catch(...){tts_error=std::current_exception();}te=Clock::now();});
            std::thread asr_worker([&]{++ready;while(!go.load())std::this_thread::yield();as=Clock::now();try{recognize();}catch(...){asr_error=std::current_exception();}ae=Clock::now();});
            while(ready.load()!=2)std::this_thread::yield();go=true;tts.join();asr_worker.join();
            if(tts_error)std::rethrow_exception(tts_error);if(asr_error)std::rethrow_exception(asr_error);
            double duration=std::chrono::duration<double,std::milli>(std::min(te,ae)-std::max(ts,as)).count();
            if(duration<=0||s.text!=reference_text||s.tts_pcm!=reference_pcm)throw std::runtime_error("Concurrent overlap/output equality failed");
            overlap_ms+=duration;
        }
        // Cancel each executor independently; sticky ASR cancellation is reset
        // before reuse. The opposite handle stays resident throughout.
        s.cancel_asr=true;check(ortts_asr_stream_reset(s.asr));
        ortts_status cancelled=ORTTS_OK;
        for(size_t i=0;i<pcm.size()&&cancelled==ORTTS_OK;i+=1600)cancelled=ortts_asr_stream_accept(s.asr,pcm.data()+i,std::min(size_t(1600),pcm.size()-i),text_event,&s);
        if(cancelled==ORTTS_OK)cancelled=ortts_asr_stream_finish(s.asr,text_event,&s);
        if(cancelled!=ORTTS_CANCELLED)throw std::runtime_error("ASR callback cancellation failed");
        s.cancel_asr=false;synthesize();
        s.cancel_tts=true;ortts_request cancel_request{sizeof(cancel_request),"Hello, welcome to local synthesis.",42,128};ortts_audio*discard=nullptr;
        cancelled=ortts_engine_synthesize(s.tts,&cancel_request,pcm_event,&s,&discard);ortts_audio_free(discard);s.cancel_tts=false;
        if(cancelled!=ORTTS_CANCELLED)throw std::runtime_error("TTS callback cancellation failed");
        recognize();
        recovery_asr = !s.text.empty(); s.pcm_frames = 0; synthesize(); recovery_tts = s.pcm_frames > 0;
        if (!recovery_asr || !recovery_tts) throw std::runtime_error("Sequential recovery failed");
        ortts_asr_stream_free(s.asr); s.asr = nullptr; ortts_engine_free(s.tts); s.tts = nullptr;
        std::ofstream out(report);
        out << "{\"status\":\"passed\",\"simultaneous_inference_supported\":true,\"distinct_threads\":true,\"asr_during_tts_status\":" << s.asr_during_tts
            << ",\"tts_during_asr_status\":" << s.tts_during_asr
            << ",\"same_domain_busy\":true,\"parallel_repetitions\":3,\"overlap_ms_sum\":" << overlap_ms
            << ",\"parallel_pcm_equal\":true,\"parallel_transcript_equal\":true,\"independent_cancellation\":true,\"sequential_tts_recovery\":true,\"sequential_asr_recovery\":true,\"scope\":\"resident Q4 TTS and Paraformer; free-running overlap and callback-held domains; not background OS execution\"}\n";
        return out ? 0 : 1;
    } catch (const std::exception& e) {
        if (s.asr) ortts_asr_stream_free(s.asr);
        if (s.tts) ortts_engine_free(s.tts);
        std::ofstream(report) << "{\"status\":\"failed\"}\n";
        std::ofstream(std::string(report)+".error.txt") << e.what();
        return 1;
    }
}
