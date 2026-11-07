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
    _ = ortts_speech_audio_sample_rate
    _ = ortts_speech_audio_channels
}
