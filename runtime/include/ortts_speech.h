#ifndef ORTTS_SPEECH_H
#define ORTTS_SPEECH_H
#include "ortts_engine.h"
#ifdef __cplusplus
extern "C" {
#endif
#define ORTTS_SPEECH_ABI_VERSION 1u
/* Additive ABI; the existing P3/P5 ABI remains version 1. No ONNX executor. */
typedef struct ortts_tts ortts_tts;
typedef struct ortts_asr ortts_asr;
typedef struct ortts_speech_audio ortts_speech_audio;
typedef struct ortts_transcript ortts_transcript;
typedef struct ortts_speech_option { const char *key; const char *value; } ortts_speech_option;
typedef struct ortts_speech_config {
 uint32_t struct_size;
 const char *family; /* Explicit catalog family. Never auto-detect or silently fallback. */
 const char *model_path; /* Verified local audio.cpp package; files outlive handle. */
 int32_t threads; /* 1..8 */
 int32_t streaming; /* TTS: 0 offline, 1 PCM callback. ASR: must be 0. */
 /* SenseVoice: setting sense_asr.vad_model_path explicitly enables offline Silero
  * speech segmentation; absent means no internal VAD. Not automatic endpointing. */
 const ortts_speech_option *session_options;
 size_t session_option_count;
 const char *espeak_library; /* Optional absolute external eSpeak-ng library path. */
 const char *espeak_data; /* Optional external eSpeak-ng data directory. */
 size_t max_input_frames; /* ASR: 0 = 60s, max 120s at 16kHz. Ignored for TTS. */
} ortts_speech_config;
typedef struct ortts_tts_request {
 uint32_t struct_size;
 const char *text;
 const char *language; /* NULL/auto = model default; explicit unsupported language fails. */
 const char *voice_id; /* Named preset, NULL = package default. */
 int32_t seed_set; /* 0 omitted, 1 set. No seed is sent to ASR. */
 uint64_t seed;
 const ortts_speech_option *options; /* Model-specific request options. */
 size_t option_count;
 const float *reference_pcm; /* ZipVoice: required mono F32 reference, normalized externally. */
 size_t reference_frames;
 int32_t reference_sample_rate;
 int32_t reference_channels;
 const char *reference_text;
} ortts_tts_request;
/* Synchronous on generating thread. Frames are per channel, PCM interleaved.
 * Never reenter/free any engine from callback. Return nonzero to cancel. */
typedef int (*ortts_speech_pcm_callback)(void*,const float*,size_t,int32_t,int32_t);
ORTTS_API uint32_t ortts_speech_abi_version(void); /* 0 when speech build disabled. */
ORTTS_API const char *ortts_speech_catalog_json(void); /* Static; declarations, not device certification. */
ORTTS_API ortts_status ortts_tts_create(const ortts_speech_config*,ortts_tts**);
ORTTS_API ortts_status ortts_tts_synthesize(ortts_tts*,const ortts_tts_request*,ortts_speech_pcm_callback,void*,ortts_speech_audio**);
ORTTS_API void ortts_tts_cancel(ortts_tts*); /* Active operation only; boundary cancellation, not kernel interruption. */
ORTTS_API void ortts_tts_free(ortts_tts*); /* Do not race free with any operation/cancel. */
ORTTS_API const float *ortts_speech_audio_samples(const ortts_speech_audio*);
ORTTS_API size_t ortts_speech_audio_frames(const ortts_speech_audio*);
ORTTS_API int32_t ortts_speech_audio_sample_rate(const ortts_speech_audio*);
ORTTS_API int32_t ortts_speech_audio_channels(const ortts_speech_audio*);
ORTTS_API ortts_status ortts_speech_audio_metrics(const ortts_speech_audio*,ortts_metrics*);
ORTTS_API void ortts_speech_audio_free(ortts_speech_audio*);
/* Independent ASR API. Input must be finite 16kHz mono F32. No implicit resample.
 * run() is offline. accept()/finish() is BOUNDED BUFFERED INPUT + FINAL ONLY,
 * with explicit finish as endpoint. There are NO partials or automatic endpoints.
 * Do not call run while buffered input is pending; finish/reset first. */
ORTTS_API ortts_status ortts_asr_create(const ortts_speech_config*,ortts_asr**);
ORTTS_API ortts_status ortts_asr_run(ortts_asr*,const float*,size_t,const char *language,ortts_transcript**);
ORTTS_API ortts_status ortts_asr_accept(ortts_asr*,const float*,size_t);
ORTTS_API ortts_status ortts_asr_finish(ortts_asr*,const char *language,ortts_transcript**);
ORTTS_API ortts_status ortts_asr_reset(ortts_asr*);
ORTTS_API void ortts_asr_cancel(ortts_asr*); /* Discards result after offline computation returns. */
ORTTS_API void ortts_asr_free(ortts_asr*);
ORTTS_API const char *ortts_transcript_text(const ortts_transcript*);
ORTTS_API const char *ortts_transcript_language(const ortts_transcript*);
ORTTS_API double ortts_transcript_api_ms(const ortts_transcript*);
ORTTS_API void ortts_transcript_free(ortts_transcript*);
/* All errors use ortts_last_error(), borrowed thread-local. Same-process inference
 * including legacy OrTTS is serialized (BUSY). No internal download/cache/playback.
 * Model handles own sessions; host owns eviction and must free them explicitly. */
#ifdef __cplusplus
}
#endif
#endif
