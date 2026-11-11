// Deterministic cancellation inside the Liquid codec CPU graph, not at a PCM boundary.
#include "clip.h"
#include "clip-impl.h"
#include <cmath>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <vector>

static void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
static bool abort_after_nodes(void *data) {
    return ++*static_cast<int *>(data) >= 3;
}
int main(int argc, char **argv) {
    if (argc != 2) { std::fprintf(stderr, "usage: codec-cancellation MODEL.gguf\n"); return 2; }
    try {
        clip_context_params config{};
        config.use_gpu = false;
        config.flash_attn_type = CLIP_FLASH_ATTN_TYPE_DISABLED;
        config.image_min_tokens = -1;
        config.image_max_tokens = -1;
        config.warmup = true;
        auto loaded = clip_init(argv[1], config);
        std::unique_ptr<clip_ctx, decltype(&clip_free)> codec(loaded.ctx_gen_a, clip_free);
        require(codec && !loaded.ctx_v && !loaded.ctx_a, "expected a codec-only model");
        std::unique_ptr<clip_gen_state, decltype(&clip_gen_state_free)> state(
            clip_gen_state_init(codec.get(), 7), clip_gen_state_free);
        require(bool(state), "missing codec state");
        std::vector<float> hidden(24 * 512, 0.01f);
        auto encode = [&](std::vector<float> &out) {
            clip_image_f32 dummy;
            dummy.set_size({1, 1}, false, true);
            dummy.cpy_buf(std::vector<float>{0});
            clip_image_f32_batch images;
            images.is_audio = true;
            images.entries.push_back(std::move(dummy));
            clip_encode_params params;
            params.imgs = &images;
            params.n_threads = 4;
            params.gen_process = CLIP_GEN_PROCESS_GEN_WAV;
            params.feats = &hidden;
            params.out_feats = &out;
            params.gen_state = state.get();
            return clip_encode(codec.get(), &params);
        };
        std::vector<float> baseline;
        require(encode(baseline) && !baseline.empty(), "baseline failed");
        for (int repeat = 0; repeat < 3; ++repeat) {
            clip_gen_state_reset(state.get());
            int callbacks = 0;
            clip_set_abort_callback(codec.get(), abort_after_nodes, &callbacks);
            std::vector<float> discarded;
            require(!encode(discarded) && callbacks >= 3, "codec graph did not abort");
            // Clear callback before stack data expires; retain the same codec weights.
            clip_set_abort_callback(codec.get(), nullptr, nullptr);
            clip_gen_state_reset(state.get());
            std::vector<float> recovery;
            require(encode(recovery), "codec did not recover after cancellation");
            require(recovery == baseline, "codec request state leaked into recovery");
            for (float value : recovery) require(std::isfinite(value), "nonfinite recovery");
            std::printf("codec graph abort/reuse %d: passed (callbacks=%d, samples=%zu)\n",
                        repeat + 1, callbacks, recovery.size());
        }
    } catch (const std::exception &error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
