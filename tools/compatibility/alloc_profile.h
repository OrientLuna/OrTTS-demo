#pragma once
#include <ggml.h>
#include <ggml-backend.h>
#include <ggml-alloc.h>
#include <mach/mach.h>
#include <cstdio>
inline size_t compat_rss(){mach_task_basic_info_data_t i{};mach_msg_type_number_t n=MACH_TASK_BASIC_INFO_COUNT;return task_info(mach_task_self(),MACH_TASK_BASIC_INFO,(task_info_t)&i,&n)==KERN_SUCCESS?i.resident_size:0;}
inline bool compat_graph_alloc(ggml_gallocr_t a,ggml_cgraph*g,const char*f,int line){bool ok=ggml_gallocr_alloc_graph(a,g);size_t biggest=0;ggml_tensor*large=nullptr;for(int i=0;i<ggml_graph_n_nodes(g);i++){auto*t=ggml_graph_node(g,i);if(ggml_nbytes(t)>biggest){biggest=ggml_nbytes(t);large=t;}}std::fprintf(stderr,"ALLOC graph file=%s line=%d bytes=%zu rss=%zu largest=%zu op=%s shape=%lld,%lld,%lld,%lld\n",f,line,ok?ggml_gallocr_get_buffer_size(a,0):0,compat_rss(),biggest,large?ggml_op_name(large->op):"none",large?(long long)large->ne[0]:0,large?(long long)large->ne[1]:0,large?(long long)large->ne[2]:0,large?(long long)large->ne[3]:0);return ok;}
inline ggml_backend_buffer_t compat_tensor_alloc(ggml_context*c,ggml_backend_t b,const char*f,int line){auto*buf=ggml_backend_alloc_ctx_tensors(c,b);std::fprintf(stderr,"ALLOC tensors file=%s line=%d bytes=%zu rss=%zu\n",f,line,buf?ggml_backend_buffer_get_size(buf):0,compat_rss());return buf;}
