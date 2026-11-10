#pragma once
#include "model_pack.h"
#include <cstdlib>
namespace ortts::ptq {
struct PTQPolicy {bool present=false,lazy=false;int type=8;};
inline PTQPolicy policy(const std::string&root,const std::string&variant){
 PTQPolicy p;
 if(!pack::fs::exists(pack::fs::path(root)/"model.json")&&!pack::fs::exists(pack::fs::path(root)/"download-manifest.json")&&!pack::fs::exists(pack::fs::path(root)/"DOWNLOAD_MANIFEST.json"))return p;
 auto m=pack::manifest(root);
 if(auto*q=m.find("research_policy")){
  if(q->require("schema").as_string()!="ortts-ptq-lazy-qa-v1"||variant!="P3"||q->require("training_steps").as_i64()!=0||q->require("expected_talker_matrices").as_i64()!=196)throw std::invalid_argument("此低内存模型包仅支持0.6B P3，请选择P3或切换标准模型包");
  if(pack::speaker_dimension(root)!=1024 || !pack::resolve(root).liquid())throw std::invalid_argument("PTQ profile requires 0.6B P3 LiquidCodec");
  p.present=true;p.lazy=q->require("lazy_import_scratch").as_bool();p.type=int(q->require("expected_talker_type").as_i64());
  if((p.type!=2&&p.type!=8)||(p.type==2&&!p.lazy)||(p.type==8&&p.lazy))throw std::invalid_argument("PTQ policy precision/lazy mismatch");
 }return p;
}
inline void apply(const PTQPolicy&p){
 // Invoke only AFTER releasing the previous model/session. No active engines overlap.
 if(p.lazy)setenv("ORTTS_LAZY_IMPORT_SCRATCH","1",1);else unsetenv("ORTTS_LAZY_IMPORT_SCRATCH");
 if(p.present)setenv("ORTTS_QA_EXPECT_TALKER_TYPE",std::to_string(p.type).c_str(),1);else unsetenv("ORTTS_QA_EXPECT_TALKER_TYPE");
}
}
