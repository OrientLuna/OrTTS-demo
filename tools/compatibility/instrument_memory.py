#!/usr/bin/env python3
"""Create an independent audio.cpp source copy with allocation diagnostics."""
import argparse,shutil
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():p.error('--out must be a new directory')
shutil.copytree(a.source,a.out)
root=a.out/'src/models/kokoro_tts';shutil.copyfile(Path(__file__).with_name('alloc_profile.h'),root/'compat_alloc_profile.h')
for name in ['decoder','predictor','plbert']:
 f=root/(name+'.cpp');s=f.read_text();s='#include "compat_alloc_profile.h"\n'+s;s=s.replace('ggml_gallocr_alloc_graph(gallocr, graph)','compat_graph_alloc(gallocr, graph,__FILE__,__LINE__)').replace('ggml_backend_alloc_ctx_tensors(ctx, backend)','compat_tensor_alloc(ctx, backend,__FILE__,__LINE__)');f.write_text(s)
f=a.out/'external/ggml/src/ggml-cpu/ggml-cpu.cpp';s=f.read_text().replace('if (cpu_ctx->work_size < cplan.work_size) {','if (cpu_ctx->work_size < cplan.work_size) {\n        fprintf(stderr,"ALLOC CPU_SCRATCH bytes=%zu\\n",cplan.work_size);');f.write_text(s)
