import OrTTS

func checkSpeechABI() {
    var config = ortts_speech_config()
    config.struct_size = UInt32(MemoryLayout<ortts_speech_config>.size)
    var request = ortts_tts_request()
    request.struct_size = UInt32(MemoryLayout<ortts_tts_request>.size)
    _ = ortts_speech_abi_version
    _ = ortts_tts_create
    _ = ortts_asr_create
    _ = ortts_asr_accept
    _ = ortts_asr_finish
    _ = ortts_asr_reset
    var streaming = ortts_asr_stream_config()
    streaming.struct_size = UInt32(MemoryLayout<ortts_asr_stream_config>.size)
    streaming.update_ms = 400
    streaming.min_partial_ms = 1000
    streaming.max_segment_ms = 15000
    streaming.silence_ms = 800
    streaming.energy_threshold = 0.003
    var stats = ortts_asr_stream_stats()
    stats.struct_size = UInt32(MemoryLayout<ortts_asr_stream_stats>.size)
    _ = ortts_asr_stream_abi_version
    _ = ortts_asr_stream_create
    _ = ortts_asr_stream_accept
    _ = ortts_asr_stream_finish
    _ = ortts_asr_stream_reset
    _ = ortts_asr_stream_cancel
    _ = ortts_asr_stream_get_stats
    _ = ortts_asr_stream_free
    _ = ortts_speech_audio_sample_rate
    _ = ortts_speech_audio_channels
}
