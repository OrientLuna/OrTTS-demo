#pragma once
#include "ortts_speech.h"
#include "file_sha256.h"
#include "zipformer_assets.h"
#include <sherpa-onnx/c-api/c-api.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <functional>
#include <memory>
#include <limits>
#include <stdexcept>
#include <string>
#ifdef __APPLE__
#include <TargetConditionals.h>
#endif

// Optional compatibility executor. This does not pretend ONNX executes on ggml.
class OrTTSZipformerStream {
 using Clock=std::chrono::steady_clock;
 const SherpaOnnxOnlineRecognizer*recognizer_=nullptr;
 const SherpaOnnxOnlineStream*stream_=nullptr;
 uint64_t received_=0,start_=0,segment_=0,revision_=0,updates_=0,limit_,last_emit_=0,update_frames_,min_partial_frames_;
 std::string last_;
 bool voiced_=false;
 double decode_ms_=0;
 void new_stream(){auto*s=SherpaOnnxCreateOnlineStream(recognizer_);if(!s)throw std::runtime_error("Cannot allocate ASR stream");if(stream_)SherpaOnnxDestroyOnlineStream(stream_);stream_=s;last_.clear();voiced_=false;revision_=0;last_emit_=received_;}
 std::string text(){auto*r=SherpaOnnxGetOnlineStreamResult(recognizer_,stream_);if(!r)throw std::runtime_error("Missing ASR result");std::string t=r->text?r->text:"";SherpaOnnxDestroyOnlineRecognizerResult(r);return t;}
 bool drain(const std::function<bool()>&cancel){while(SherpaOnnxIsOnlineStreamReady(recognizer_,stream_)){if(cancel())return false;auto t=Clock::now();SherpaOnnxDecodeOnlineStream(recognizer_,stream_);decode_ms_+=std::chrono::duration<double,std::milli>(Clock::now()-t).count();++updates_;if(cancel())return false;}return true;}
 bool emit(int endpoint,const std::function<bool(const ortts_asr_stream_event&)>&sink){std::string t=voiced_?text():"";if(endpoint==ORTTS_ASR_PARTIAL&&(t.empty()||t==last_||received_-start_<min_partial_frames_||received_-last_emit_<update_frames_))return true;last_=t;last_emit_=received_;ortts_asr_stream_event e{sizeof(e),endpoint,segment_,start_,received_,++revision_,t.c_str(),"und"};return !sink(e);}
 bool end(int reason,const std::function<bool(const ortts_asr_stream_event&)>&sink,const std::function<bool()>&cancel){if(received_==start_)return true;if(voiced_){float tail[10560]={};SherpaOnnxOnlineStreamAcceptWaveform(stream_,16000,tail,10560);SherpaOnnxOnlineStreamInputFinished(stream_);if(!drain(cancel))return false;}if(cancel()||!emit(reason,sink))return false;new_stream();start_=received_;++segment_;return true;}
 public:
 OrTTSZipformerStream(const std::string&root,int threads,uint32_t max_ms,uint32_t update_ms=400,uint32_t min_partial_ms=1000):limit_(uint64_t(max_ms)*16),update_frames_(uint64_t(update_ms)*16),min_partial_frames_(uint64_t(min_partial_ms)*16){
  // Official iOS and desktop 1.13.8 artifacts were built from different commits.
#if defined(__APPLE__) && TARGET_OS_IPHONE
  const char* expected_git="793c2405";
#else
  const char* expected_git="11afbd00";
#endif
  if(std::string(SherpaOnnxGetVersionStr())!="1.13.8"||std::string(SherpaOnnxGetGitSha1())!=expected_git||std::string(SherpaOnnxGetOnnxruntimeVersionStr())!="1.28.2")throw std::runtime_error(std::string("Sherpa executor version mismatch: ")+SherpaOnnxGetVersionStr()+" git="+SherpaOnnxGetGitSha1()+" ort="+SherpaOnnxGetOnnxruntimeVersionStr());
  if(threads<1||threads>8||max_ms<1000||max_ms>30000||max_ms%20)throw std::invalid_argument("Invalid ASR recipe configuration");
  auto base=std::filesystem::canonical(root);
  for(const auto&a:ortts_zipformer_assets){auto p=std::filesystem::canonical(base/a.path);auto rel=p.lexically_relative(base);if(rel.empty()||rel.is_absolute()||*rel.begin()==".."||!std::filesystem::is_regular_file(p)||std::filesystem::file_size(p)!=a.bytes||ortts_sha256::file(p.string())!=a.sha256)throw std::invalid_argument("ASR asset identity mismatch: "+std::string(a.path));}
  auto enc=(base/"exp/32/encoder-epoch-99-avg-1.int8.onnx").string();auto dec=(base/"exp/32/decoder-epoch-99-avg-1.onnx").string();auto join=(base/"exp/32/joiner-epoch-99-avg-1.int8.onnx").string();auto tokens=(base/"data/lang_char_bpe/tokens.txt").string();
  SherpaOnnxOnlineRecognizerConfig c{};c.feat_config.sample_rate=16000;c.feat_config.feature_dim=80;c.model_config.transducer.encoder=enc.c_str();c.model_config.transducer.decoder=dec.c_str();c.model_config.transducer.joiner=join.c_str();c.model_config.tokens=tokens.c_str();c.model_config.num_threads=threads;c.model_config.provider="cpu";c.decoding_method="greedy_search";c.max_active_paths=4;c.enable_endpoint=0;
  recognizer_=SherpaOnnxCreateOnlineRecognizer(&c);if(!recognizer_)throw std::runtime_error("ASR recognizer creation failed");try{new_stream();}catch(...){SherpaOnnxDestroyOnlineRecognizer(recognizer_);recognizer_=nullptr;throw;}
 }
 ~OrTTSZipformerStream(){if(stream_)SherpaOnnxDestroyOnlineStream(stream_);if(recognizer_)SherpaOnnxDestroyOnlineRecognizer(recognizer_);}
 OrTTSZipformerStream(const OrTTSZipformerStream&)=delete;OrTTSZipformerStream&operator=(const OrTTSZipformerStream&)=delete;
 bool accept(const float*p,size_t n,const std::function<bool(const ortts_asr_stream_event&)>&sink,const std::function<bool()>&cancel){
  if(!p||!n||n>32000)throw std::invalid_argument("ASR input must contain 1..32000 samples");for(size_t i=0;i<n;i++)if(!std::isfinite(p[i]))throw std::invalid_argument("Nonfinite ASR input");
  for(size_t off=0;off<n;){if(cancel())return false;size_t count=std::min({size_t(320),n-off,size_t(limit_-(received_-start_))});for(size_t i=0;i<count;i++)voiced_|=p[off+i]!=0;SherpaOnnxOnlineStreamAcceptWaveform(stream_,16000,p+off,int32_t(count));received_+=count;off+=count;if(!drain(cancel)||!emit(ORTTS_ASR_PARTIAL,sink))return false;if(received_-start_==limit_&&!end(ORTTS_ASR_LIMIT,sink,cancel))return false;}return true;
 }
 bool finish(const std::function<bool(const ortts_asr_stream_event&)>&sink,const std::function<bool()>&cancel){return !cancel()&&end(ORTTS_ASR_FLUSH,sink,cancel);}
 void reset(){new_stream();received_=start_=segment_=revision_=updates_=0;decode_ms_=0;last_emit_=0;}
 void stats(ortts_asr_stream_stats*out)const{*out={sizeof(*out),received_,UINT64_MAX,UINT64_MAX,updates_,UINT64_MAX,UINT64_MAX,received_-start_,UINT64_MAX,UINT64_MAX,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::quiet_NaN()};}
};
