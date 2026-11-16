#pragma once
#include "file_sha256.h"
#include <sherpa-onnx/c-api/c-api.h>
#include <filesystem>
#include <memory>
#include <stdexcept>
#include <string>

// Only the last-row ASR consumer may use the head-slice compatibility graph.
class OrTTSQwenAsr {
 struct Asset {const char* name;uint64_t bytes;const char* sha;};
 const SherpaOnnxOfflineRecognizer* recognizer_=nullptr;
 static void verify(const std::filesystem::path& base,const Asset& a){
  auto p=std::filesystem::canonical(base/a.name);auto rel=p.lexically_relative(base);
  if(rel.empty()||rel.is_absolute()||*rel.begin()==".."||!std::filesystem::is_regular_file(p)||std::filesystem::file_size(p)!=a.bytes||ortts_sha256::file(p.string())!=a.sha)
   throw std::invalid_argument("Qwen ASR asset identity mismatch: "+std::string(a.name));
  if(std::string(a.name).find('/')==std::string::npos&&p.parent_path()!=base)
   throw std::invalid_argument("Qwen external graph and weights must share their real directory");
 }
public:
 OrTTSQwenAsr(const std::string& root,const std::string& profile,int threads){
  if(threads!=2)throw std::invalid_argument("Verified Qwen ASR profile requires CPU2");
  if(profile!="headslice-compat"&&profile!="original-int8")throw std::invalid_argument("Unknown Qwen decoder profile");
#if defined(__ANDROID__)
  if(std::string(SherpaOnnxGetVersionStr())!="1.13.8"||std::string(SherpaOnnxGetGitSha1())!=ORTTS_SHERPA_ANDROID_GIT||std::string(SherpaOnnxGetOnnxruntimeVersionStr())!=ORTTS_SHERPA_ANDROID_ORT)
   throw std::runtime_error("Qwen ASR platform SDK identity mismatch");
#endif
  auto base=std::filesystem::canonical(root);
  const Asset common[]={
   {"conv_frontend.onnx",44148281,"d22dc4423e0940e49884e903d2ea2f7e5567c14fc1aed97e4e26d6b8f208ef9e"},
   {"encoder.int8.onnx",182491662,"60748d3e6744a57c9c91e1b17424a6c2990567e8adceb0783940c03ed98fa9d9"},
   {"tokenizer/merges.txt",1671853,"8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5"},
   {"tokenizer/tokenizer_config.json",12487,"4942d005604266809309cabc9f4e9cb89ce855d59b14681fdc0e1cc62ea26c4c"},
   {"tokenizer/vocab.json",2776833,"ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910"}
  };
  for(const auto& a:common)verify(base,a);
  bool sliced=profile=="headslice-compat";
  const Asset decoder=sliced?Asset{"decoder.last_head.compat.int8.onnx",4106983,"a4c03aa745627a70d8fc8fd6667fd677af201cf2129f58a33166abd076550985"}:Asset{"decoder.int8.onnx",755914231,"4f6885be5959ae26af3089d38ee7972c5fafbeeb1cf8d5e76eab6d8b61ca5771"};
  verify(base,decoder);
  if(sliced)verify(base,{"decoder.weights.bin",751828992,"f7779d10fe7e42e9bbb4ac184dd6bfdf80590248d5c7183c26e0ca67207c1e3e"});
  auto front=(base/"conv_frontend.onnx").string(),encoder=(base/"encoder.int8.onnx").string(),dec=(base/decoder.name).string(),tokens=(base/"tokenizer").string();
  SherpaOnnxOfflineRecognizerConfig c{};c.feat_config.sample_rate=16000;c.feat_config.feature_dim=80;c.model_config.num_threads=2;c.model_config.provider="cpu";
  auto& q=c.model_config.qwen3_asr;q.conv_frontend=front.c_str();q.encoder=encoder.c_str();q.decoder=dec.c_str();q.tokenizer=tokens.c_str();q.max_total_len=1024;q.max_new_tokens=256;q.temperature=1e-6f;q.top_p=1;q.seed=42;c.decoding_method="greedy_search";
  recognizer_=SherpaOnnxCreateOfflineRecognizer(&c);if(!recognizer_)throw std::runtime_error("Cannot create pinned Qwen ASR recognizer");
 }
 ~OrTTSQwenAsr(){if(recognizer_)SherpaOnnxDestroyOfflineRecognizer(recognizer_);}
 OrTTSQwenAsr(const OrTTSQwenAsr&)=delete;OrTTSQwenAsr&operator=(const OrTTSQwenAsr&)=delete;
 std::string run(const float* pcm,size_t frames){
  std::unique_ptr<const SherpaOnnxOfflineStream,decltype(&SherpaOnnxDestroyOfflineStream)> stream(SherpaOnnxCreateOfflineStream(recognizer_),SherpaOnnxDestroyOfflineStream);
  if(!stream)throw std::runtime_error("Cannot create Qwen ASR stream");
  SherpaOnnxAcceptWaveformOffline(stream.get(),16000,pcm,static_cast<int32_t>(frames));SherpaOnnxDecodeOfflineStream(recognizer_,stream.get());
  std::unique_ptr<const SherpaOnnxOfflineRecognizerResult,decltype(&SherpaOnnxDestroyOfflineRecognizerResult)> result(SherpaOnnxGetOfflineStreamResult(stream.get()),SherpaOnnxDestroyOfflineRecognizerResult);
  if(!result)throw std::runtime_error("Missing Qwen ASR result");
  return result->text?result->text:""; // Preserve SDK output, including any erroneous headers.
 }
};
