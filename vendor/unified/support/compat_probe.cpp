#include "engine/framework/runtime/graph_optimizer.h"
#include "engine/framework/core/unified_ggml_compat.h"
#include "ggml-impl.h"
#include "ggml-cpu.h"
#include <cmath>
#include <cstdio>
#include <stdexcept>
int main(){try{
 for(int k=0;k<3;k++){
  auto*c=ggml_init({8ull<<20,nullptr,false});if(!c)throw std::runtime_error("alloc");
  auto*x=ggml_new_tensor_2d(c,GGML_TYPE_F32,8,4);auto*b=ggml_new_tensor_1d(c,GGML_TYPE_F32,8);
  for(int i=0;i<32;i++)((float*)x->data)[i]=i*.125f;for(int i=0;i<8;i++)((float*)b->data)[i]=i*.25f;
  auto*y=ggml_add(c,ggml_cont(c,x),ggml_repeat(c,b,x));ggml_set_output(y);
  auto*g=ggml_new_graph(c);ggml_build_forward_expand(g,y);
  auto options=engine::runtime::graph_optimization_options_for_backend(engine::runtime::GraphOptimizationBackend::Cpu,true);
  auto report=engine::runtime::optimize_graph(*g,options);
  for(int n=0;n<g->n_nodes;n++)for(auto*src:g->nodes[n]->src)if(src){auto slot=ggml_hash_find(&g->visited_hash_set,src);if(g->use_counts[slot]<1)throw std::runtime_error("stale use count");}
  if(ggml_graph_compute_with_ctx(c,g,4)!=GGML_STATUS_SUCCESS)throw std::runtime_error("compute");
  for(int i=0;i<32;i++)if(std::abs(((float*)y->data)[i]-(i*.125f+(i%8)*.25f))>1e-6)throw std::runtime_error("optimizer numeric");
  printf("optimizer pass before=%d after=%d\n",report.nodes_before,report.nodes_after);ggml_free(c);
 }
 {auto*c=ggml_init({8ull<<20,nullptr,false});auto*x=ggml_new_tensor_1d(c,GGML_TYPE_F32,32);for(int i=0;i<32;i++)((float*)x->data)[i]=(i-16)*.1234567f;auto*y=ggml_round_bf16(c,x);auto*g=ggml_new_graph(c);ggml_build_forward_expand(g,y);if(ggml_graph_compute_with_ctx(c,g,4)!=GGML_STATUS_SUCCESS)throw std::runtime_error("BF16 compute");for(int i=0;i<32;i++){float ref=ggml_bf16_to_fp32(ggml_fp32_to_bf16(((float*)x->data)[i]));if(((float*)y->data)[i]!=ref)throw std::runtime_error("BF16 rounding");}ggml_free(c);puts("BF16 storage roundtrip pass");}
 return 0;
}catch(const std::exception&e){fprintf(stderr,"%s\n",e.what());return 1;}}
