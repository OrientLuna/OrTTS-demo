#!/usr/bin/env python3
"""Serial CPU comparison using locally prepared model packages. No downloads."""
import argparse,hashlib,json,statistics,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['sherpa-lib-dir','sherpa-header','ggml-install','assets','int8-root','fp32-root','out']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--threads',type=int,default=4);a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);inc=out/'include';inc.mkdir(exist_ok=True);(inc/'c-api-macos.h').write_bytes(a.sherpa_header.read_bytes())
 common=['clang++','-O3','-std=c++17',str(ROOT/'experiments/kokoro-ab/bench.cpp')];lib=a.ggml_install.resolve()/'lib'
 commands=[common+['-I'+str(ROOT/'runtime/include'),'-L'+str(lib),'-lortts','-Wl,-rpath,'+str(lib),'-o',str(out/'bench-ggml')],common+['-DUSE_SHERPA','-I'+str(inc)]+[str(f) for f in sorted(a.sherpa_lib_dir.glob('*.a'))]+['-framework','Foundation','-framework','Accelerate','-framework','CoreML','-framework','CoreAudio','-framework','AudioToolbox','-liconv','-o',str(out/'bench-sherpa')]]
 for cmd in commands:subprocess.run(cmd,check=True)
 results=[]
 for backend,case in [('sherpa-int8','en'),('ggml-q8','en'),('ggml-q8','zh'),('sherpa-int8','zh'),('sherpa-int8','long'),('ggml-q8','long'),('sherpa-fp32','en'),('sherpa-fp32','zh'),('sherpa-fp32','long')]:
  exe=out/('bench-ggml' if backend=='ggml-q8' else 'bench-sherpa');root=a.assets if backend=='ggml-q8' else a.int8_root if backend=='sherpa-int8' else a.fp32_root
  with (out/f'{backend}-{case}.log').open('w') as log:r=subprocess.run([str(exe),str(root.resolve()),case,str(out/f'{backend}-{case}.wav'),str(a.threads)],capture_output=False,stdout=subprocess.PIPE,stderr=log,text=True,timeout=900)
  if r.returncode:raise RuntimeError('Failed: '+backend+' '+case)
  row=json.loads(r.stdout);row.update(backend=backend,case=case,warm_rtf_median=statistics.median(x['rtf'] for x in row['runs'][1:]));results.append(row);(out/f'{backend}-{case}.json').write_text(json.dumps(row,indent=2)+'\n');print(backend,case,row['warm_rtf_median'],flush=True)
 (out/'results.json').write_text(json.dumps({'results':results,'source_sha256':hashlib.sha256((ROOT/'experiments/kokoro-ab/bench.cpp').read_bytes()).hexdigest(),'limitations':['different quantization and frontend pipelines; not a pure tensor-backend ablation','3 warm samples per input; no thermal/power certification','no playback or audio callback in timed inference','not an iPhone result']},indent=2)+'\n')
if __name__=='__main__':main()
