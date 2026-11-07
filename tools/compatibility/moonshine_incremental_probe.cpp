// Experimental bounded-overlap encoder, NOT the shipped speech ABI.
// The runner prepends the pinned runtime.cpp plus a position-offset extension.
#include <fstream>
#include <iostream>
#include <iomanip>
#include <sys/resource.h>

using namespace engine::models::moonshine_asr;
static double milliseconds(std::chrono::steady_clock::time_point t) {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now()-t).count();
}
int main(int argc, char **argv) {
    try {
        if (argc != 5) throw std::runtime_error("MODEL INPUT_16K_MONO_F32 CHUNK_SAMPLES native|f16|f32");
        std::string storage=argv[4];
        if(storage!="native" && storage!="f32" && storage!="f16") throw std::runtime_error("unknown storage");
        const size_t chunk = std::stoul(argv[3]);
        if (chunk < 80 || chunk > 32000) throw std::runtime_error("chunk outside 80..32000");
        std::ifstream f(argv[2], std::ios::binary | std::ios::ate);
        if (!f) throw std::runtime_error("missing input");
        auto bytes = f.tellg();
        if (bytes < 80*4 || bytes % 4 || bytes > 30*16000*4) throw std::runtime_error("input must be 5ms..30s F32");
        f.seekg(0); std::vector<float> input(size_t(bytes)/4);
        f.read(reinterpret_cast<char*>(input.data()), bytes);
        for (float x: input) if (!std::isfinite(x)) throw std::runtime_error("nonfinite input");
        engine::core::ExecutionContext context({engine::core::BackendType::Cpu, 0, 4});
        auto assets = load_moonshine_asr_assets(argv[1]);
        if(assets->config.encoder.frame_length!=80 || assets->config.encoder.sample_rate!=16000)
            throw std::runtime_error("probe supports only the verified 16kHz/80-sample frontend");
        auto config = make_moonshine_runtime_config(assets->config, context.backend_type(), {});
        if(storage=="f32") config.encoder_weight_storage_type = engine::assets::TensorStorageType::F32;
        if(storage=="f16") config.encoder_weight_storage_type = engine::assets::TensorStorageType::F16;
        auto weights = load_moonshine_asr_weights(*assets, context.backend(), context.backend_type(),
            config.encoder_weight_storage_type, config.decoder_weight_storage_type,
            config.conv_weight_storage_type, config.weight_context_bytes);
        // Two stride-2 causal convolutions: 4 raw 5ms frames/output, 12-frame past.
        int64_t left = 4, right = 0;
        for (auto w: assets->config.encoder.sliding_windows) {
            if (w.past < 0 || w.future < 0) throw std::runtime_error("unbounded attention unsupported");
            left += w.past; right += w.future;
        }
        const int64_t stride = assets->config.encoder.frame_length * 4;
        const int64_t hidden = assets->config.decoder.hidden_size;
        auto encode = [&](const std::vector<float>& pcm, int64_t offset) {
            auto frames = prepare_compressed_frames(pcm, assets->config.encoder.frame_length,
                weights->encoder.frontend.log_k);
            EncoderGraph graph(*assets, *weights, context,
                frames.size()/assets->config.encoder.frame_length, config.encoder_gelu,
                config.cpu_blas_scheduler, config.graph_arena_bytes, offset);
            return graph.run(frames, context);
        };
        auto begin = std::chrono::steady_clock::now();
        auto reference = encode(input, 0);
        auto baseline_text = probe_decode_memory(*assets, *weights, context, reference, config);
        double baseline_ms = milliseconds(begin);
        std::vector<float> ring, memory;
        size_t received=0, ring_start=0, encoded_samples=0, max_ring=0;
        int64_t committed=0; double encode_ms=0, decode_ms=0;
        std::cout << std::setprecision(9) << "{\"experimental\":true,\"encoder_storage\":\"" << storage
                  << "\",\"chunk_samples\":" << chunk
                  << ",\"left_context_frames\":" << left << ",\"right_context_frames\":" << right
                  << ",\"updates\":[";
        bool comma=false; std::string final_text;
        while (received < input.size()) {
            size_t end=std::min(input.size(), received+chunk);
            ring.insert(ring.end(), input.begin()+received, input.begin()+end); received=end;
            max_ring=std::max(max_ring,ring.size());
            bool final=received==input.size();
            // One extra frame conservatively protects incomplete convolution input.
            int64_t stable=final ? int64_t(reference.size()/hidden)
                : std::max<int64_t>(0, int64_t(received/stride)-right-1);
            if (stable<=committed) continue;
            begin=std::chrono::steady_clock::now();
            auto output=encode(ring, ring_start/stride);
            encode_ms+=milliseconds(begin); encoded_samples+=ring.size();
            size_t from=size_t(committed-ring_start/stride)*hidden;
            size_t count=size_t(stable-committed)*hidden;
            if (from+count>output.size()) throw std::runtime_error("commit exceeds available encoder output");
            memory.insert(memory.end(), output.begin()+from, output.begin()+from+count);
            double local_error=0, local_energy=0;
            for(size_t k=0;k<count;++k){ double d=output[from+k]-reference[size_t(committed)*hidden+k];
                local_error+=d*d;local_energy+=double(reference[size_t(committed)*hidden+k])*reference[size_t(committed)*hidden+k];}
            committed=stable;
            begin=std::chrono::steady_clock::now();
            final_text=probe_decode_memory(*assets, *weights, context, memory, config);
            double elapsed=milliseconds(begin); decode_ms+=elapsed;
            if(comma) std::cout << ','; comma=true;
            // JSON escape without extra serialization dependencies.
            auto quote=[](const std::string& s){std::string o="\"";for(unsigned char c:s){
                if(c=='"'||c=='\\')o+='\\'; if(c<32)throw std::runtime_error("control byte in transcript");o+=c;}return o+'"';};
            std::cout << "{\"audio_s\":" << received/16000.0 << ",\"final\":" << (final?"true":"false")
                << ",\"slice_relative_l2\":" << std::sqrt(local_error/std::max(local_energy,1e-30))
                << ",\"committed_frames\":" << committed << ",\"text\":" << quote(final_text) << '}';
            size_t keep_start=size_t(std::max<int64_t>(0,committed-left))*stride;
            if(keep_start>ring_start){ring.erase(ring.begin(),ring.begin()+(keep_start-ring_start));ring_start=keep_start;}
        }
        if(memory.size()!=reference.size()) throw std::runtime_error("encoder length differs");
        double maximum=0, squared=0, energy=0;
        for(size_t i=0;i<memory.size();++i){
            if(!std::isfinite(memory[i]) || !std::isfinite(reference[i])) throw std::runtime_error("nonfinite encoder output");
            double d=memory[i]-reference[i];
            maximum=std::max(maximum,std::abs(d));squared+=d*d;energy+=double(reference[i])*reference[i];}
        struct rusage usage{};getrusage(RUSAGE_SELF,&usage);
        // This process retains the full-input baseline for numerical verification.
        // Its peak RSS is NOT streaming-only memory.
        std::cout << "],\"input_samples\":" << input.size() << ",\"max_ring_samples\":" << max_ring
            << ",\"encoded_samples_with_overlap\":" << encoded_samples << ",\"encoder_max_abs\":" << maximum
            << ",\"encoder_relative_l2\":" << std::sqrt(squared/std::max(energy,1e-30))
            << ",\"final_matches_offline\":" << (final_text==baseline_text?"true":"false")
            << ",\"baseline_ms\":" << baseline_ms << ",\"encoder_ms\":" << encode_ms
            << ",\"decoder_ms\":" << decode_ms << ",\"process_peak_rss_bytes\":" << usage.ru_maxrss << "}\n";
        // Screening tolerance, not bitwise parity or corpus-level accuracy.
        return std::sqrt(squared/std::max(energy,1e-30))<5e-4 && final_text==baseline_text ? 0:1;
    }catch(const std::exception& e){std::cerr << e.what() << '\n';return 2;}
}
