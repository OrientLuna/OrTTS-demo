#!/usr/bin/env python3
"""Real-model incremental ASR acceptance on macOS; no downloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--report',type=Path,default=ROOT/'benchmarks/asr-stream-sdk-20261107.json')
    a=p.parse_args()
    if platform.system()!='Darwin':raise RuntimeError('This acceptance harness measures macOS RSS')
    build=a.build.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    lib=build/'install/lib';artifact=lib/'libortts.dylib';binary=out/'asr-stream-test'
    env={**os.environ,'ORTTS_LIB_DIR':str(lib),'DYLD_LIBRARY_PATH':str(lib)}
    commands=[['clang++','-std=c++17','-O2','-I'+str(ROOT/'runtime/include'),
               str(ROOT/'tests/asr_stream_integration.cpp'),'-L'+str(lib),'-lortts',
               '-Wl,-rpath,'+str(lib),'-o',str(binary)],
              [str(binary),str(a.model.resolve()),str(a.input.resolve())],
              [str(binary),str(a.model.resolve()),str(a.input.resolve()),'memory'],
              [str(binary),str(a.model.resolve()),str(a.input.resolve()),'memory-default'],
              ['cargo','run','--offline','--manifest-path',str(ROOT/'runtime/rust/Cargo.toml'),
               '--example','asr_stream','--',str(a.model.resolve()),str(a.input.resolve())]]
    results=[]
    for i,cmd in enumerate(commands):
        before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.monotonic()
        proc=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        (out/f'step-{i}.log').write_text(proc.stdout+proc.stderr)
        row={'step':i,'returncode':proc.returncode,'wall_s':time.monotonic()-start,
             'cpu_user_s':after.ru_utime-before.ru_utime,'cpu_system_s':after.ru_stime-before.ru_stime}
        if i in (1,2,3) and proc.returncode==0:row['result']=json.loads(proc.stdout)
        results.append(row);print('step',i,proc.returncode,flush=True)
        if proc.returncode:raise RuntimeError(f'ASR stream acceptance failed: {out}/step-{i}.log')
    symbols=subprocess.check_output(['nm','-gU',str(artifact)],text=True)
    names=[line.split()[-1] for line in symbols.splitlines() if line.strip()]
    if not names or any(not name.startswith('_ortts_') for name in names):
        raise RuntimeError('Unexpected ggml/C++ exports')
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    report={'schema':1,'date':'2026-11-07','host':platform.platform(),
            'artifact_sha256':sha(artifact),'artifact_bytes':artifact.stat().st_size,
            'model_sha256':sha(a.model),'fixture_sha256':sha(a.input),
            'public_header_sha256':sha(ROOT/'runtime/include/ortts_speech.h'),
            'test_source_sha256':sha(ROOT/'tests/asr_stream_integration.cpp'),
            'rust_sources_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in
                [ROOT/'runtime/rust/src/speech/streaming.rs',ROOT/'runtime/rust/examples/asr_stream.rs']},
            'exports':names,'checks':results,
            'limitations':['CPU macOS execution only; mobile cross-build is not device execution',
                           'bounded-overlap encoder with F16-expanded weights; decoder re-decodes hypotheses',
                           'English only; energy endpoint is not neural VAD',
                           'five-minute audio replay is accelerated, not five minutes of microphone/thermal measurement',
                           'repeated synthetic speech is not an ASR accuracy corpus']}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
