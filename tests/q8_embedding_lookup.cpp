// Compile against the pinned prepared runtime to exercise its actual lookup.
#ifndef ORTTS_TEST_QWEN_TALKER_SOURCE
#error "Define ORTTS_TEST_QWEN_TALKER_SOURCE as the prepared talker.cpp path"
#endif
#include ORTTS_TEST_QWEN_TALKER_SOURCE
#include <cstdio>
namespace q = engine::models::qwen3_tts;
static void save(const std::string & p, const std::vector<float> & values) {
    std::ofstream f(p, std::ios::binary);
    f.write(reinterpret_cast<const char *>(values.data()), values.size() * sizeof(float));
    if (!f) throw std::runtime_error("Cannot save lookup fixture");
}
template<class F> static void rejects(F f, const char * expected) {
    try { f(); } catch (const std::runtime_error & e) {
        if (std::string(e.what()).find(expected) != std::string::npos) return;
        throw;
    }
    throw std::runtime_error("Malformed lookup input was accepted");
}
int main(int argc, char ** argv) { try {
    if (argc != 3) throw std::runtime_error("model.gguf output-directory");
    auto assets = q::load_qwen3_tts_assets(argv[1]);
    auto table = assets->model_weights->require_tensor("talker.model.text_embedding.weight",
        engine::assets::TensorStorageType::Native, {151936, 2048});
    auto prefix = q::lookup_rows(table, 2048, {0,1,100,77091,151644,151672,151673,151671});
    auto boundary = q::lookup_rows(table, 2048, {0,151935,1,1});
    for (float x : prefix) if (!std::isfinite(x)) throw std::runtime_error("Nonfinite prefix");
    for (float x : boundary) if (!std::isfinite(x)) throw std::runtime_error("Nonfinite boundary");
    for (int32_t id : {-1,151936,2147483647})
        rejects([&]{ (void)q::lookup_rows(table,2048,{id}); }, "id out of range");
    engine::assets::TensorData bad;
    bad.type = table.type; bad.shape = table.shape;
    rejects([&]{ (void)q::lookup_rows(bad,2048,{0}); }, "byte size mismatch");
    rejects([&]{ (void)q::lookup_rows(table,0,{0}); }, "shape mismatch");
    bad.shape.dims[0] = -1;
    rejects([&]{ (void)q::lookup_rows(bad,2048,{0}); }, "shape mismatch");
    bad.shape = table.shape; bad.shape.dims[0] = std::numeric_limits<int64_t>::max();
    rejects([&]{ (void)q::lookup_rows(bad,2048,{0}); }, "size overflow");
    bad.shape = table.shape; bad.type = GGML_TYPE_Q8_0; bad.shape.dims[1] = 31;
    rejects([&]{ (void)q::lookup_rows(bad,31,{0}); }, "block-aligned");
    bad.type = GGML_TYPE_Q4_0;
    rejects([&]{ (void)q::lookup_rows(bad,31,{0}); }, "must be f32");
    save(std::string(argv[2])+"/prefix.f32",prefix);
    save(std::string(argv[2])+"/boundary.f32",boundary);
    std::printf("{\"status\":\"PASS\",\"native_type\":%d,\"native_bytes\":%zu,\"negative_cases\":9,\"AR_requests\":0}\n", int(table.type), table.bytes.size());
    return 0;
} catch (const std::exception & e) { std::fprintf(stderr,"%s\n",e.what()); return 1; } }
