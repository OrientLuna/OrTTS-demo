#!/usr/bin/env python3
"""Build the CPU plugin from verified local sources. Never download SDKs or models."""
import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {'linux-x86_64': ('x86_64-baseline','x86_64-avx2'),
           'linux-aarch64': ('arm64-baseline','arm64-dotprod','arm64-i8mm'),
           'android-arm64': ('arm64-baseline','arm64-dotprod','arm64-i8mm','arm64-auto'),
           'macos-arm64': ('arm64-baseline','arm64-dotprod','arm64-i8mm'), 'macos-x86_64': ('x86_64-baseline','x86_64-avx2'),
           'ios-arm64': ('arm64-baseline','arm64-dotprod','arm64-i8mm'), 'ios-simulator-arm64': ('arm64-baseline',)}

try:from source_identity import identity
except ModuleNotFoundError:from tools.source_identity import identity

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target',choices=TARGETS,required=True)
    p.add_argument('--profile',required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cmake',default='cmake');p.add_argument('--ninja',type=Path)
    p.add_argument('--ndk',type=Path);p.add_argument('--toolchain',type=Path)
    p.add_argument('--rebuild',action='store_true',help='Incrementally rebuild an existing matching completed/failed receipt');p.add_argument('--speech',action='store_true');p.add_argument('--liquidcodec',action='store_true');p.add_argument('--jobs',type=int,default=4);p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if a.profile not in TARGETS[a.target]:p.error('Profile does not match target')
    if not 1<=a.jobs<=8:p.error('Use 1..8 build workers')
    source=a.source.resolve();out=a.out.resolve();lock=identity(source,a.liquidcodec,a.speech)
    apple=a.target.startswith(('macos','ios'))
    cmd=[a.cmake,'-S',str(ROOT),'-B',str(out),'-G','Ninja',
         '-DCMAKE_BUILD_TYPE=Release','-DORTTS_AUDIOCPP_SOURCE='+str(source),
         '-DORTTS_BUILD_ENGINE_PLUGIN=ON','-DORTTS_CPU_PROFILE='+a.profile,
         '-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
    if a.speech:cmd+=['-DORTTS_ENABLE_SPEECH=ON']
    if a.liquidcodec:cmd+=['-DORTTS_ENABLE_LIQUIDCODEC=ON']
    if 'cpu_dispatch' in lock:
        ur=json.loads((source/'ORTTS_UNIFIED_SOURCE_RECEIPT.json').read_text())
        cmd+=['-DORTTS_LLAMA_SOURCE_DIR='+ur['llama_source_read_only']]
    if a.profile=='arm64-auto':
        if 'cpu_dispatch' not in lock:raise ValueError('Prepare sources with tools/prepare_cpu_dispatch.py first')
        cmd+=['-DORTTS_ANDROID_CPU_AUTO=ON']
    else:cmd+=['-DORTTS_ANDROID_CPU_AUTO=OFF']
    if a.ninja:cmd+=['-DCMAKE_MAKE_PROGRAM='+str(a.ninja.resolve())]
    if apple:
        cmd+=['-DCMAKE_OSX_ARCHITECTURES='+('x86_64' if a.target=='macos-x86_64' else 'arm64'),'-DGGML_ACCELERATE=OFF']
        if a.target.startswith('ios'):
            cmd+=['-DCMAKE_SYSTEM_NAME=iOS','-DCMAKE_OSX_SYSROOT='+('iphonesimulator' if 'simulator' in a.target else 'iphoneos'),'-DCMAKE_OSX_DEPLOYMENT_TARGET=16.3']
        else:cmd+=['-DCMAKE_OSX_DEPLOYMENT_TARGET=13.3']
    elif a.target=='android-arm64':
        if not a.ndk:p.error('--ndk is required; no SDK will be fetched')
        cmd+=['-DCMAKE_TOOLCHAIN_FILE='+str(a.ndk.resolve()/'build/cmake/android.toolchain.cmake'),'-DANDROID_ABI=arm64-v8a','-DANDROID_PLATFORM=android-28','-DANDROID_STL=c++_shared']
    elif a.target=='linux-aarch64' and platform.machine() not in ('arm64','aarch64'):
        if not a.toolchain:p.error('Cross-build requires --toolchain pointing at an existing Linux ARM64 toolchain file')
        cmd+=['-DCMAKE_TOOLCHAIN_FILE='+str(a.toolchain.resolve())]
    commands=[cmd,[a.cmake,'--build',str(out),'--config','Release','--target','ortts_engine','--parallel',str(a.jobs)],
              [a.cmake,'--install',str(out),'--config','Release','--component','Engine','--prefix',str(out/'install')]]
    if a.target=='android-arm64':commands[-1].append('--strip') # Keep debug symbols in build tree, ship stripped .so.
    if out.exists():
        if not a.rebuild:raise ValueError('Use a fresh build directory, or --rebuild for the same receipt')
        prior=json.loads((out/'ENGINE_BUILD_RECEIPT.json').read_text())
        if prior.get('status')=='BUILDING':raise ValueError('Build still marked active; do not race another builder')
        if prior.get('target')!=a.target or prior.get('cpu_profile')!=a.profile or prior.get('argv',[None])[0]!=cmd or prior.get('speech')!=lock.get('speech'):
            raise ValueError('Existing build receipt does not match requested configuration')
    elif a.rebuild:raise ValueError('--rebuild requires an existing matching receipt')
    files=[ROOT/'CMakeLists.txt',Path(__file__).resolve()]
    files += [f for f in (ROOT/'runtime').rglob('*') if f.is_file() and f.suffix in ('.h','.cpp','.c','.rs','.toml','.in','.apple','.map') and 'target' not in f.parts]
    receipt={'status':'PLAN_ONLY','target':a.target,'cpu_profile':a.profile,'backend':'CPU',
             'source_commit':lock['base_commit'],'integration_patch_sha256':lock['patch_sha256'],
             'additional_patches':lock.get('additional_patches',[]),'release_compat':lock.get('release_compat'),
             'plugin_source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(files)},
             'argv':commands,'speech':lock.get('speech'),'models_included':False,'liquidcodec':a.liquidcodec,
             'unified_source_receipt':json.loads((source/'ORTTS_UNIFIED_SOURCE_RECEIPT.json').read_text()) if a.liquidcodec else None}
    if 'cpu_dispatch' in lock:receipt['cpu_dispatch']=lock['cpu_dispatch']
    if 'cancellation' in lock:receipt['cancellation']=lock['cancellation']
    print(json.dumps(receipt,indent=2))
    if a.dry_run:return
    if apple and platform.system()!='Darwin':raise RuntimeError('Apple SDK builds require a Mac with Xcode')
    if a.target=='linux-x86_64' and platform.machine() not in ('x86_64','AMD64'):raise RuntimeError('Use an x86_64 host for this native target')
    out.mkdir(parents=True,exist_ok=a.rebuild);receipt['status']='BUILDING'
    receipt_file=out/'ENGINE_BUILD_RECEIPT.json'
    receipt_file.write_text(json.dumps(receipt,indent=2)+'\n')
    try:
        for command in commands:subprocess.run(command,check=True)
        receipt['artifacts']=[{'path':str(f.relative_to(out)), 'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
                              for f in sorted((out/'install').rglob('*')) if f.is_file() and not f.is_symlink()]
        receipt['cmake_cache_sha256']=hashlib.sha256((out/'CMakeCache.txt').read_bytes()).hexdigest()
        receipt['status']='BUILT_NOT_TARGET_TESTED'
    except Exception as e:
        receipt.update(status='FAILED',error=str(e));raise
    finally:receipt_file.write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':main()
