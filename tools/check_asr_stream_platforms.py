#!/usr/bin/env python3
"""Verify already-built ASR artifacts/FFI on macOS. Never downloads or signs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from source_identity import identity

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--macos',type=Path,default=Path('build/speech-incremental-macos'))
    p.add_argument('--ios',type=Path,default=Path('build/speech-incremental-ios'))
    p.add_argument('--android',type=Path,default=Path('build/speech-incremental-android'))
    p.add_argument('--ndk',type=Path,default=Path.home()/'Library/Android/sdk/ndk/27.0.12077973')
    p.add_argument('--prepared-source',type=Path,default=Path('_work/runtime-speech-streaming-clean'))
    p.add_argument('--report',type=Path,default=Path('benchmarks/asr-stream-platforms-20261107.json'))
    p.add_argument('--acceptance-report',type=Path,default=Path('benchmarks/asr-stream-sdk-20261107.json'))
    a=p.parse_args();identity(a.prepared_source,speech=True)
    acceptance=json.loads(a.acceptance_report.read_text())
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    expected_header=sha(ROOT/'runtime/include/ortts_speech.h')
    rows=[]
    paths=[('macos-arm64',a.macos/'install/lib/libortts.dylib',a.macos/'install/include/ortts_speech.h'),
           ('ios-arm64',a.ios/'install/OrTTS.framework/OrTTS',a.ios/'install/OrTTS.framework/Headers/ortts_speech.h'),
           ('android-arm64',a.android/'install/lib/libortts.so',a.android/'install/include/ortts_speech.h')]
    for target,artifact,header in paths:
        if target=='macos-arm64' and (sha(artifact)!=acceptance['artifact_sha256'] or
                any(check['returncode'] for check in acceptance['checks'])):
            raise RuntimeError('macOS artifact lacks matching real-model acceptance')
        if sha(header)!=expected_header:raise RuntimeError('Stale installed header: '+str(header))
        receipt=json.loads((artifact.parents[2]/'ENGINE_BUILD_RECEIPT.json').read_text())
        # The iOS framework has the same depth as install/lib artifacts.
        if receipt['target']!=target or receipt['cpu_profile']!='arm64-baseline':
            raise RuntimeError('Unexpected build target/profile')
        for path,digest in receipt['plugin_source_sha256'].items():
            if sha(ROOT/path)!=digest:raise RuntimeError('Stale build source fingerprint: '+path)
        row={'platform':target,'artifact':str(artifact),'bytes':artifact.stat().st_size,
             'sha256':sha(artifact),'public_header_sha256':expected_header,'model_execution':target=='macos-arm64',
             'cpu_profile':'arm64-baseline'}
        if target=='android-arm64':
            llvm=a.ndk/'toolchains/llvm/prebuilt/darwin-x86_64/bin'
            symbols=subprocess.check_output([str(llvm/'llvm-nm'),'-D','--defined-only',str(artifact)],text=True)
            names=[line.split()[-1] for line in symbols.splitlines() if line.strip()]
            elf=subprocess.check_output([str(llvm/'llvm-readelf'),'-l','-d',str(artifact)],text=True)
            loads=[line.strip() for line in elf.splitlines() if line.strip().startswith('LOAD')]
            if not loads or not all(int(line.split()[-1],16)>=0x4000 for line in loads):
                raise RuntimeError('Missing Android 16KiB LOAD alignment')
            row['elf_load_segments']=loads;row['needed']=[line.strip() for line in elf.splitlines() if '(NEEDED)' in line]
        else:
            symbols=subprocess.check_output(['nm','-gU',str(artifact)],text=True)
            names=[line.split()[-1].removeprefix('_') for line in symbols.splitlines() if line.strip()]
            row['dependencies']=subprocess.check_output(['otool','-L',str(artifact)],text=True).splitlines()[1:]
        expected=['ortts_asr_stream_'+s for s in ['abi_version','create','accept','finish','reset','cancel','get_stats','free']]
        if not names or any(not n.startswith('ortts_') for n in names) or any(n not in names for n in expected):
            raise RuntimeError('Unexpected/missing exports: '+target)
        row['ortts_exports']=len(names);row['incremental_exports']=expected;rows.append(row)
    sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    with tempfile.TemporaryDirectory(prefix='ortts-stream-ffi-') as directory:
        subprocess.run(['xcrun','swiftc','-typecheck','-target','arm64-apple-ios16.3','-sdk',sdk,
                        '-module-cache-path',directory,'-F',str((a.ios/'install').resolve()),
                        str(ROOT/'runtime/examples/ImportSpeech.swift')],check=True)
        subprocess.run(['clang++','-std=c++17','-DORTTS_WITH_SPEECH=0','-I'+str(ROOT/'runtime/include'),
                        '-I'+str(a.prepared_source.resolve()/'include'),'-c',str(ROOT/'runtime/src/ortts_speech.cpp'),
                        '-o',str(Path(directory)/'disabled.o')],check=True)
        subprocess.run(['clang','-x','c','-fsyntax-only','-I'+str(ROOT/'runtime/include'),
                        '-include','ortts_speech.h','/dev/null'],check=True)
    report={'schema':1,'date':'2026-11-07','source_prepare_reproduced':True,
            'speech_patch_sha256':json.loads((ROOT/'vendor/speech/lock.json').read_text())['patch_sha256'],
            'swift_ios_typecheck':'passed; ARM64 iOS16.3, SDK iphoneos, ImportSpeech.swift',
            'disabled_feature_compile':'passed; ORTTS_WITH_SPEECH=0',
            'c_header_syntax':'passed','platforms':rows,
            'limitations':['mobile cross-build and symbol/type checks only; no new model device execution',
                           'Linux and Windows not validated this round','Apple simulator slice not built this round']}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print([(r['platform'],r['bytes'],r['ortts_exports']) for r in rows])

if __name__=='__main__':main()
