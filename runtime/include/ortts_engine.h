#ifndef ORTTS_ENGINE_H
#define ORTTS_ENGINE_H
#include <stddef.h>
#include <stdint.h>
#if defined(_WIN32)
#define ORTTS_API __declspec(dllexport)
#else
#define ORTTS_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif
#define ORTTS_ABI_VERSION 1u
typedef struct ortts_engine ortts_engine;
typedef struct ortts_audio ortts_audio;
typedef struct ortts_cancel_token ortts_cancel_token;
typedef enum ortts_status {
 ORTTS_OK=0, ORTTS_INVALID=1, ORTTS_RUNTIME_ERROR=2, ORTTS_BUSY=3, ORTTS_CANCELLED=4
} ortts_status;
typedef struct ortts_config {
 uint32_t struct_size;
 const char *asset_root; /* Installed native pack; caller verifies its download manifest. */
 const char *variant; /* P3 or P5. */
 const char *speaker_f32; /* Own-model 1024/2048 finite F32 values; NULL selects voices/female.f32. */
 const char *bridge_manifest_sha256; /* Trusted bridge/dequant manifest SHA (64 digits), not a self-computed trust root. */
 int32_t threads; /* 1..8. */
 int32_t streaming; /* 0 offline, 1 incremental PCM. Fixed for this engine. */
} ortts_config;
typedef struct ortts_request {
 uint32_t struct_size;
 const char *text; /* UTF-8, nonempty. */
 uint64_t seed;
 int32_t max_tokens; /* 1..513. */
} ortts_request;
typedef struct ortts_metrics {
 double api_ms; /* Includes client callback time. */
 double callback_ms;
 double generation_ms; /* API minus callbacks; not isolated kernel time. */
 double first_pcm_ms; /* -1 if not observed; ready at callback, not audible onset. */
 size_t chunks;
} ortts_metrics;
/* Called synchronously on the synthesize thread. PCM is borrowed for this call.
 * Copy/enqueue quickly. Return nonzero to cancel. Never unwind/reenter/free here.
 * No playback, filesystem writes or network operations are performed by the API. */
typedef int (*ortts_pcm_callback)(void *user, const float *pcm, size_t samples, int32_t sample_rate);
ORTTS_API uint32_t ortts_abi_version(void);
ORTTS_API const char *ortts_last_error(void); /* Borrowed, thread-local. */
ORTTS_API ortts_status ortts_engine_create(const ortts_config*, ortts_engine**);
/* Additive capability: 1 means cooperative Qwen CPU graph/step cancellation.
 * 0 retains legacy compute-then-discard behavior. ABI1 structs are unchanged. */
ORTTS_API uint32_t ortts_cooperative_cancel_version(void);
/* Sticky token for synchronous creation. Caller owns it until create returns;
 * request is thread-safe. Never free concurrently with request/create. */
ORTTS_API ortts_cancel_token *ortts_cancel_token_create(void);
ORTTS_API void ortts_cancel_token_request(ortts_cancel_token*);
ORTTS_API void ortts_cancel_token_free(ortts_cancel_token*);
ORTTS_API ortts_status ortts_engine_create_cancellable(const ortts_config*, ortts_cancel_token*, ortts_engine**);
ORTTS_API ortts_status ortts_engine_synthesize(ortts_engine*, const ortts_request*, ortts_pcm_callback, void*, ortts_audio**);
/* Per-operation sticky cancellation, including before execution starts. Use a
 * fresh token for every invocation; do not reset/reuse or free it while in use.
 * Older libraries may lack this additive symbol. The execution gate is unchanged. */
ORTTS_API ortts_status ortts_engine_synthesize_cancellable(ortts_engine*, const ortts_request*, ortts_cancel_token*, ortts_pcm_callback, void*, ortts_audio**);
/* Thread-safe while handle is alive. Cooperative builds stop at CPU graph/step
 * checkpoints; a running kernel or blocking read may still need to return.
 * Legacy builds may only discard the result after offline compute returns.
 * Cancellation resets request state, keeping loaded weights/session resident.
 * Calling cancel while idle has no effect. */
ORTTS_API void ortts_engine_cancel(ortts_engine*);
/* Do not free a handle concurrently with synthesis/cancel. */
ORTTS_API void ortts_engine_free(ortts_engine*);
ORTTS_API const float *ortts_audio_samples(const ortts_audio*);
ORTTS_API size_t ortts_audio_sample_count(const ortts_audio*);
ORTTS_API int32_t ortts_audio_sample_rate(const ortts_audio*);
ORTTS_API ortts_status ortts_audio_metrics(const ortts_audio*, ortts_metrics*);
ORTTS_API void ortts_audio_free(ortts_audio*);
#ifdef __cplusplus
}
#endif
#endif
