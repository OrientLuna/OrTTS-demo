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
typedef struct ortts_asr_stream ortts_asr_stream;
typedef struct ortts_speech_option { const char *key; const char *value; } ortts_speech_option;
typedef struct ortts_speech_config {
 uint32_t struct_size;
 const char *family; /* Explicit catalog family. Never auto-detect or silently fallback. */
 const char *model_path; /* Verified local audio.cpp package; files outlive handle. */
 int32_t threads; /* 1..8 */
 int32_t streaming; /* TTS: 0 offline, 1 callback; legacy ASR: 0; ASR stream API: 1. */
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
/* Additive, separately versioned incremental ASR API. Moonshine English only.
 * bounded-overlap encoder + revisable decoder; not per-layer KV streaming.
 * Existing ortts_asr_* retains buffered-final semantics. */
#define ORTTS_ASR_STREAM_ABI_VERSION 1u
typedef struct ortts_asr_stream_config {
 uint32_t struct_size;
 uint32_t update_ms;       /* 100..2000, multiple of 20; default 400 */
 uint32_t min_partial_ms;  /* 400..3000, multiple of 20; default 1000 */
 uint32_t max_segment_ms;  /* 1000..30000, multiple of 20; default 15000 */
 uint32_t silence_ms;      /* 0=manual/limit only; 200..3000, multiple of 20 */
 float energy_threshold;  /* RMS amplitude 0..1, >0. Energy gate, NOT neural VAD */
} ortts_asr_stream_config;
typedef enum ortts_asr_endpoint {
 ORTTS_ASR_PARTIAL=0, ORTTS_ASR_FLUSH=1, ORTTS_ASR_SILENCE=2, ORTTS_ASR_LIMIT=3
} ortts_asr_endpoint;
typedef struct ortts_asr_stream_event {
 uint32_t struct_size;
 int32_t endpoint; /* 0=partial; otherwise final. Partials replace the whole hypothesis. */
 uint64_t segment_id, start_frame, end_frame, revision; /* 16kHz input timeline */
 const char *text; /* Borrowed UTF-8; valid only during callback. */
 const char *language; /* "en" for Moonshine; "und" for bilingual recipe (no language-ID claim). */
} ortts_asr_stream_event;
typedef struct ortts_asr_stream_stats {
 uint32_t struct_size;
 uint64_t received_frames, processed_frames, encoded_samples, updates;
 uint64_t buffered_pcm_frames, cached_encoder_frames, segment_frames;
 uint64_t peak_buffered_pcm_frames, peak_cached_encoder_frames;
 double encoder_ms, decoder_ms;
} ortts_asr_stream_stats;
/* Synchronous worker callback. Copy/enqueue; never reenter/free an engine here.
 * Nonzero cancels the stream; reset is required before reuse. */
typedef int (*ortts_asr_stream_callback)(void*,const ortts_asr_stream_event*);
ORTTS_API uint32_t ortts_asr_stream_abi_version(void); /* 0 if --speech disabled */
/* NULL stream config uses 400/1000/15000ms, 800ms silence, RMS 0.003.
 * Base config normally selects moonshine_asr, streaming=1, threads=1..8.
 * Optional Sherpa builds also accept internal family zipformer_bilingual for the
 * pinned Chinese/English recipe; set silence_ms=0 (explicit/limit endpoints).
 * For this compatibility path UINT64_MAX cache/buffer counts mean unavailable,
 * not zero memory usage; unobservable encoder/decoder timings are NaN; this does not imply low-end-device certification.
 * No session_options/eSpeak/max_input_frames: use typed stream settings. */
ORTTS_API ortts_status ortts_asr_stream_create(const ortts_speech_config*,const ortts_asr_stream_config*,ortts_asr_stream**);
/* Finite 16kHz mono F32; each call 1..32000 frames. No implicit resampling.
 * Callback is required on every accept/finish; emitted events are not retained. */
ORTTS_API ortts_status ortts_asr_stream_accept(ortts_asr_stream*,const float*,size_t,ortts_asr_stream_callback,void*);
/* Flush current utterance; session continues with a new segment. Repeated flush
 * without new input emits nothing. Exact/energy silence does not invoke ASR. */
ORTTS_API ortts_status ortts_asr_stream_finish(ortts_asr_stream*,ortts_asr_stream_callback,void*);
ORTTS_API ortts_status ortts_asr_stream_reset(ortts_asr_stream*);
/* Can be called from another thread, including between accept calls. Cancel is
 * sticky until reset. Checked at ticks, encode boundaries and decoder tokens;
 * no interruption inside a tensor kernel. Do not race free with any operation. */
ORTTS_API void ortts_asr_stream_cancel(ortts_asr_stream*);
ORTTS_API ortts_status ortts_asr_stream_get_stats(ortts_asr_stream*,ortts_asr_stream_stats*);
ORTTS_API void ortts_asr_stream_free(ortts_asr_stream*);
/* All errors use ortts_last_error(), borrowed thread-local. Same-process inference
 * including legacy OrTTS is serialized (BUSY). No internal download/cache/playback.
 * Model handles own sessions; host owns eviction and must free them explicitly. */
#ifdef __cplusplus
}
#endif
#endif
