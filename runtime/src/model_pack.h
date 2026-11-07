#pragma once
#include "engine/framework/io/json.h"
#include "file_sha256.h"
#include <filesystem>
#include <stdexcept>
#include <string>
#include <cmath>
#include <fstream>
#include <vector>

namespace ortts::pack {
namespace fs=std::filesystem;
struct Decoder {
 std::string kind="qwen_lfm", variant, assets, identity="legacy", dequant_bundle, dequant_sha;
 bool liquid() const {return kind=="liquidcodec";}
 std::string cache_key() const {return kind+":"+variant+":"+identity;}
};
inline fs::path inside(const fs::path&root,const std::string&relative) {
 fs::path p(relative);
 if(relative.empty()||p.is_absolute()||relative.find('\\')!=std::string::npos)
  throw std::invalid_argument("Invalid model-pack path");
 for(const auto&part:p)if(part==".."||part==".")throw std::invalid_argument("Invalid model-pack path");
 auto base=fs::weakly_canonical(root),full=fs::weakly_canonical(base/p);
 auto a=base.begin(),b=full.begin();for(;a!=base.end()&&b!=full.end()&&*a==*b;++a,++b){}
 if(a!=base.end()||b==full.end())throw std::invalid_argument("Model-pack path escapes its root");
 return full;
}
inline Decoder resolve(const std::string&root) {
 Decoder d;auto path=fs::path(root)/"model.json";
 if(!fs::exists(path))path=fs::path(root)/"download-manifest.json"; // Existing Apple installer name.
 if(!fs::exists(path))path=fs::path(root)/"DOWNLOAD_MANIFEST.json";
 if(!fs::exists(path))return d;
 if(!fs::is_regular_file(path)||fs::file_size(path)>2*1024*1024)throw std::invalid_argument("Invalid model manifest");
 auto m=engine::io::json::parse_file(path);auto*r=m.find("runtime");if(!r)return d;
 // v0.1 download manifests used a descriptive string, not a decoder selector.
 if(r->is_string()) {
  auto*schema=m.find("schema");
  if(schema&&schema->is_string()&&schema->as_string()=="ortts-download-manifest-v1")return d;
  throw std::invalid_argument("Unrecognized legacy runtime descriptor");
 }
 if(r->require("schema").as_string()!="ortts-runtime-v1")throw std::invalid_argument("Unsupported runtime manifest schema");
 auto&spec=r->require("decoder");d.kind=spec.require("kind").as_string();
 if(d.kind=="qwen_lfm")return d;
 if(d.kind!="liquidcodec")throw std::invalid_argument("Unsupported acoustic decoder: "+d.kind);
#if !defined(ORTTS_WITH_LIQUIDCODEC) || !ORTTS_WITH_LIQUIDCODEC
 throw std::invalid_argument("This runtime was built without LiquidCodec support");
#else
 d.variant=spec.require("variant").as_string();
 if(d.variant!="base"&&d.variant!="expanded")throw std::invalid_argument("Unsupported LiquidCodec variant");
 auto rel=spec.require("manifest").as_string();auto config=inside(root,rel);
 if(config.filename()!="runtime.json"||!fs::is_regular_file(config)||fs::file_size(config)>65536)
  throw std::invalid_argument("Invalid LiquidCodec runtime manifest");
 std::string expected;int count=0;
 for(auto&entry:m.require("files").as_array())if(entry.require("path").as_string()==rel){expected=entry.require("sha256").as_string();++count;}
 if(count!=1||expected.size()!=64||expected.find_first_not_of("0123456789abcdef")!=std::string::npos||ortts_sha256::file(config.string())!=expected)
  throw std::invalid_argument("LiquidCodec manifest is missing or fails model-pack SHA binding");
 auto cfg=engine::io::json::parse_file(config);
 if(cfg.require("schema").as_string()!="ortts-liquidcodec-native-v1"||cfg.require("source_RVQ_groups").as_i64()!=16||cfg.require("frame_samples").as_i64()!=1920||cfg.require("lookahead_frames").as_i64()!=1)
  throw std::invalid_argument("Unsupported LiquidCodec geometry");
 d.assets=config.parent_path().string();d.identity=expected;
 if(auto*q=spec.find("dequant_manifest")) {
  auto relq=q->as_string();auto file=inside(root,relq);
  if(file.filename()!="MANIFEST.json"||!fs::is_regular_file(file)||fs::file_size(file)>262144)throw std::invalid_argument("Invalid dequant manifest");
  for(auto &entry:m.require("files").as_array())if(entry.require("path").as_string()==relq){if(!d.dequant_sha.empty())throw std::invalid_argument("Duplicate dequant manifest");d.dequant_sha=entry.require("sha256").as_string();}
  if(d.dequant_sha.size()!=64||ortts_sha256::file(file.string())!=d.dequant_sha)throw std::invalid_argument("Dequant manifest SHA binding");
  d.dequant_bundle=file.parent_path().string();d.identity+=":"+d.dequant_sha;
 }
 return d;
#endif
}
inline engine::io::json::Value manifest(const std::string&root) {
 for(auto n:{"model.json","download-manifest.json","DOWNLOAD_MANIFEST.json"}){auto p=fs::path(root)/n;if(fs::is_regular_file(p)){if(fs::file_size(p)>2*1024*1024)throw std::invalid_argument("Manifest too large");return engine::io::json::parse_file(p);}}
 throw std::invalid_argument("Model manifest required for native predictor/config");
}
inline std::string file_hash(const std::string&root,const std::string&rel) {
 auto m=manifest(root);std::string hash;int count=0;
 for(auto &e:m.require("files").as_array())if(e.require("path").as_string()==rel){hash=e.require("sha256").as_string();++count;}
 if(count!=1||hash.size()!=64||hash.find_first_not_of("0123456789abcdef")!=std::string::npos)throw std::invalid_argument("Missing/duplicate asset SHA: "+rel);
 return hash;
}
inline size_t speaker_dimension(const std::string&root) {
 // Legacy packs retain 1024. New packs bind the own-model configuration.
 fs::path cfg=fs::path(root)/"native/config.json";
 if(!fs::exists(cfg))return 1024;
 if(!fs::is_regular_file(cfg)||fs::file_size(cfg)>262144||ortts_sha256::file(cfg.string())!=file_hash(root,"native/config.json"))throw std::invalid_argument("Model config SHA");
 auto v=engine::io::json::parse_file(cfg);auto n=v.require("speaker_encoder_config").require("enc_dim").as_i64();
 if((n!=1024&&n!=2048)||n!=v.require("talker_config").require("hidden_size").as_i64())throw std::invalid_argument("Model speaker dimensions");
 return size_t(n);
}
inline void validate_speaker(const std::string&path,size_t n) {
 if((n!=1024&&n!=2048)||!fs::is_regular_file(path)||fs::file_size(path)!=n*sizeof(float))throw std::invalid_argument("Speaker must match own model dimensions");
 std::vector<float>v(n);std::ifstream in(path,std::ios::binary);if(!in.read(reinterpret_cast<char*>(v.data()),v.size()*sizeof(float)))throw std::invalid_argument("Cannot read speaker");
 for(float x:v)if(!std::isfinite(x))throw std::invalid_argument("Nonfinite speaker");
}
inline std::string native_predictor_hash(const std::string&root,const std::string&variant) {
 if(variant!="P3")return {};
 auto base=fs::path(root)/"P3/predictor";
 for(auto n:{"config.json"})if(!fs::is_regular_file(base/n))throw std::invalid_argument("Missing predictor configuration");
 if(fs::exists(base/"predictor.gguf")){if(!fs::is_regular_file(base/"talker_config.json"))throw std::invalid_argument("Native predictor requires own Talker config");return file_hash(root,"P3/predictor/predictor.gguf");}
 if(!fs::is_regular_file(base/"predictor.safetensors"))throw std::invalid_argument("Missing P3 predictor");
 return {};
}
inline void require_dependencies(const std::string&root,const Decoder&d) {
 std::vector<std::string>paths={"native/model.gguf"};
 if(d.dequant_bundle.empty())for(auto n:{"native/bridge/MANIFEST.json","native/tokenizer-b260k-MIXED_Q4_0.gguf","native/tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf","native/vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf"})paths.push_back(n);
 for(auto &rel:paths)if(!fs::is_regular_file(inside(root,rel)))throw std::invalid_argument("Missing decoder dependency: "+rel);
}
template<class Setter> inline void environment(const Decoder&d,Setter set) {
 set("ORTTS_LC_WORKER",nullptr);set("ORTTS_LC_LIBDIR",nullptr);
 set("ORTTS_LC_VARIANT",d.liquid()?(d.variant=="base"?"base100k":"expanded120k"):nullptr);
 set("ORTTS_LC_ASSETS",d.liquid()?d.assets.c_str():nullptr);
}
} // namespace ortts::pack
