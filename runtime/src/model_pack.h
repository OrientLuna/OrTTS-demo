#pragma once
#include "engine/framework/io/json.h"
#include "file_sha256.h"
#include <filesystem>
#include <stdexcept>
#include <string>

namespace ortts::pack {
namespace fs=std::filesystem;
struct Decoder {
 std::string kind="qwen_lfm", variant, assets, identity="legacy";
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
 if(!fs::exists(path))return d;
 if(!fs::is_regular_file(path)||fs::file_size(path)>2*1024*1024)throw std::invalid_argument("Invalid model manifest");
 auto m=engine::io::json::parse_file(path);auto*r=m.find("runtime");if(!r)return d;
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
 d.assets=config.parent_path().string();d.identity=expected;return d;
#endif
}
template<class Setter> inline void environment(const Decoder&d,Setter set) {
 set("ORTTS_LC_WORKER",nullptr);set("ORTTS_LC_LIBDIR",nullptr);
 set("ORTTS_LC_VARIANT",d.liquid()?d.variant.c_str():nullptr);
 set("ORTTS_LC_ASSETS",d.liquid()?d.assets.c_str():nullptr);
}
} // namespace ortts::pack
