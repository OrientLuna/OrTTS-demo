#include "model_pack.h"
#include <fstream>
#include <iostream>
namespace fs=std::filesystem;
void save(const fs::path&p,const std::string&s){fs::create_directories(p.parent_path());std::ofstream(p)<<s;}
int main(int argc,char**argv){try{
 if(argc!=2)throw std::runtime_error("fresh test directory required");fs::path root=argv[1];if(fs::exists(root))throw std::runtime_error("fresh directory required");fs::create_directories(root);
 if(ortts::pack::resolve(root.string()).liquid())throw std::runtime_error("legacy changed");
 save(root/"model.json","{}");if(ortts::pack::resolve(root.string()).liquid())throw std::runtime_error("old manifest changed");
 fs::rename(root/"model.json",root/"download-manifest.json");if(ortts::pack::resolve(root.string()).liquid())throw std::runtime_error("Apple manifest changed");fs::rename(root/"download-manifest.json",root/"model.json");
 save(root/"model.json",R"({"schema":"ortts-download-manifest-v1","runtime":"OrTTS-demo Android ARM64 CPU"})");if(ortts::pack::resolve(root.string()).liquid())throw std::runtime_error("legacy descriptive runtime changed");
 auto reject=[&](const std::string&s){save(root/"model.json",s);bool bad=false;try{ortts::pack::resolve(root.string());}catch(const std::exception&){bad=true;}if(!bad)throw std::runtime_error("invalid manifest accepted");};
 reject(R"({"runtime":"unknown"})");reject(R"({"runtime":{"schema":"wrong"}})");reject(R"({"runtime":{"schema":"ortts-runtime-v1","decoder":{"kind":"unknown"}}})");
 std::string cfg=R"({"schema":"ortts-liquidcodec-native-v1","source_RVQ_groups":16,"frame_samples":1920,"lookahead_frames":1})";save(root/"native/lc/runtime.json",cfg);auto h=ortts_sha256::file((root/"native/lc/runtime.json").string());
 auto manifest=[&](const std::string&kind,const std::string&v,const std::string&rel,const std::string&hash){return "{\"runtime\":{\"schema\":\"ortts-runtime-v1\",\"decoder\":{\"kind\":\""+kind+"\",\"variant\":\""+v+"\",\"manifest\":\""+rel+"\"}},\"files\":[{\"path\":\""+rel+"\",\"sha256\":\""+hash+"\"}]}";};
 auto valid=manifest("liquidcodec","base","native/lc/runtime.json",h);
#if ORTTS_WITH_LIQUIDCODEC
 save(root/"model.json",valid);auto d=ortts::pack::resolve(root.string());if(!d.liquid()||d.variant!="base"||d.identity!=h)throw std::runtime_error("valid pack failed");
 std::string runtime_variant;ortts::pack::environment(d,[&](const char*k,const char*v){if(std::string(k)=="ORTTS_LC_VARIANT")runtime_variant=v?v:"";});if(runtime_variant!="base100k")throw std::runtime_error("base100k runtime mapping");
 save(root/"model.json",manifest("liquidcodec","expanded","native/lc/runtime.json",h));if(ortts::pack::resolve(root.string()).variant!="expanded")throw std::runtime_error("expanded failed");
 reject(manifest("liquidcodec","base","native/lc/runtime.json",std::string(64,'0')));reject(manifest("liquidcodec","oops","native/lc/runtime.json",h));reject(manifest("liquidcodec","base","../runtime.json",h));
 save(root/"native/lc/runtime.json",R"({"schema":"ortts-liquidcodec-native-v1","source_RVQ_groups":8,"frame_samples":1920,"lookahead_frames":1})");auto badHash=ortts_sha256::file((root/"native/lc/runtime.json").string());reject(manifest("liquidcodec","base","native/lc/runtime.json",badHash));
#else
 reject(valid);
#endif
 // Legacy speaker default, new own-model 2048 config, malformed dimensions/SHA.
 fs::remove(root/"model.json");if(ortts::pack::speaker_dimension(root.string())!=1024)throw std::runtime_error("legacy dimension changed");
 auto speaker=root/"voice.f32";{std::ofstream out(speaker,std::ios::binary);std::vector<float>v(2048,.25f);out.write((char*)v.data(),8192);}
 ortts::pack::validate_speaker(speaker.string(),2048);bool rejected=false;try{ortts::pack::validate_speaker(speaker.string(),1024);}catch(...){rejected=true;}if(!rejected)throw std::runtime_error("wrong speaker dimension accepted");
 save(root/"native/config.json",R"({"speaker_encoder_config":{"enc_dim":2048},"talker_config":{"hidden_size":2048}})");
 auto cfghash=ortts_sha256::file((root/"native/config.json").string());
 auto own=[&](std::string hash){return "{\"files\":[{\"path\":\"native/config.json\",\"sha256\":\""+hash+"\"}]}";};
 save(root/"model.json",own(cfghash));if(ortts::pack::speaker_dimension(root.string())!=2048)throw std::runtime_error("2048 own-model config failed");
 save(root/"model.json",own(std::string(64,'0')));rejected=false;try{ortts::pack::speaker_dimension(root.string());}catch(...){rejected=true;}if(!rejected)throw std::runtime_error("wrong config SHA accepted");
 // The old safetensors path remains accepted without a new mandatory sidecar.
 save(root/"P3/predictor/config.json","{}");save(root/"P3/predictor/predictor.safetensors","fixture");if(!ortts::pack::native_predictor_hash(root.string(),"P3").empty())throw std::runtime_error("old P3 changed");
 save(root/"P3/predictor/predictor.gguf","fixture");rejected=false;try{ortts::pack::native_predictor_hash(root.string(),"P3");}catch(...){rejected=true;}if(!rejected)throw std::runtime_error("unbound native P3 accepted");
#if ORTTS_WITH_LIQUIDCODEC
 save(root/"native/dequant/MANIFEST.json","{}");auto dh=ortts_sha256::file((root/"native/dequant/MANIFEST.json").string());save(root/"native/lc/runtime.json",cfg);h=ortts_sha256::file((root/"native/lc/runtime.json").string());
 auto small=manifest("liquidcodec","base","native/lc/runtime.json",h);auto cut=small.find("\"manifest\":");small.insert(cut,"\"dequant_manifest\":\"native/dequant/MANIFEST.json\",");small.insert(small.size()-2,",{\"path\":\"native/dequant/MANIFEST.json\",\"sha256\":\""+dh+"\"}");save(root/"model.json",small);auto lightweight=ortts::pack::resolve(root.string());
 save(root/"native/model.gguf","fixture");ortts::pack::require_dependencies(root.string(),lightweight); // no old LFM files exist
 save(root/"native/dequant/MANIFEST.json","tampered");rejected=false;try{ortts::pack::resolve(root.string());}catch(...){rejected=true;}if(!rejected)throw std::runtime_error("wrong dequant SHA accepted");
#endif
 int clears=0;ortts::pack::environment(ortts::pack::Decoder{},[&](const char*,const char*v){if(!v)++clears;});if(clears!=4)throw std::runtime_error("stale decoder environment");
 std::cout<<"PASS model pack validation, compiled LiquidCodec="<<ORTTS_WITH_LIQUIDCODEC<<"\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
