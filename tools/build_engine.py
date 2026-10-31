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
           'android-arm64': ('arm64-baseline','arm64-dotprod','arm64-i8mm'),
           'macos-arm64': ('arm64-baseline','arm64-dotprod','arm64-i8mm'), 'macos-x86_64': ('x86_64-baseline','x86_64-avx2'),
           'ios-arm64': ('arm64-baseline','arm64-dotprod','arm64-i8mm'), 'ios-simulator-arm64': ('arm64-baseline',)}

def identity(source):
    lock = json.loads((ROOT/'vendor/runtime.lock.json').read_text())
    receipt = json.loads((source/'ORTTS_SOURCE_RECEIPT.json').read_text())
    for key in ('base_commit','patch_sha256'):
        if receipt[key] != lock[key]: raise ValueError('Source identity mismatch: '+key)
    if receipt.get('additional_patches',[]) != lock.get('additional_patches',[]):
        raise ValueError('Source patch list mismatch')
    for item in lock['selected_files']:
        if hashlib.sha256((source/item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Source modified: '+item['path'])
    return lock

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target',choices=TARGETS,required=True)
    p.add_argument('--profile',required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cmake',default='cmake');p.add_argument('--ninja',type=Path)
    p.add_argument('--ndk',type=Path);p.add_argument('--toolchain',type=Path)
    p.add_argument('--jobs',type=int,default=4);p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if a.profile not in TARGETS[a.target]:p.error('Profile does not match target')
    if not 1<=a.jobs<=8:p.error('Use 1..8 build workers')
    source=a.source.resolve();out=a.out.resolve();lock=identity(source)
    if out.exists():raise ValueError('Use a fresh build directory')
    apple=a.target.startswith(('macos','ios'))
    cmd=[a.cmake,'-S',str(ROOT),'-B',str(out),'-G','Ninja',
         '-DCMAKE_BUILD_TYPE=Release','-DORTTS_AUDIOCPP_SOURCE='+str(source),
         '-DORTTS_BUILD_ENGINE_PLUGIN=ON','-DORTTS_CPU_PROFILE='+a.profile,
         '-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
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
    files=[ROOT/'CMakeLists.txt',Path(__file__).resolve()]
    files += [f for f in (ROOT/'runtime').rglob('*') if f.is_file() and f.suffix in ('.h','.cpp','.c','.rs','.toml','.in','.apple','.map') and 'target' not in f.parts]
    receipt={'status':'PLAN_ONLY','target':a.target,'cpu_profile':a.profile,'backend':'CPU',
             'source_commit':lock['base_commit'],'integration_patch_sha256':lock['patch_sha256'],
             'additional_patches':lock.get('additional_patches',[]),
             'plugin_source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(files)},
             'argv':commands,'models_included':False}
    print(json.dumps(receipt,indent=2))
    if a.dry_run:return
    if apple and platform.system()!='Darwin':raise RuntimeError('Apple SDK builds require a Mac with Xcode')
    if a.target=='linux-x86_64' and platform.machine() not in ('x86_64','AMD64'):raise RuntimeError('Use an x86_64 host for this native target')
    out.mkdir(parents=True);receipt['status']='BUILDING'
    receipt_file=out/'ENGINE_BUILD_RECEIPT.json'
    receipt_file.write_text(json.dumps(receipt,indent=2)+'\n')
    try:
        for command in commands:subprocess.run(command,check=True)
        receipt['artifacts']=[{'path':str(f.relative_to(out)), 'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
                              for f in sorted((out/'install').rglob('*')) if f.is_file() and not f.is_symlink()]
        receipt['status']='BUILT_NOT_TARGET_TESTED'
    except Exception as e:
        receipt.update(status='FAILED',error=str(e));raise
    finally:receipt_file.write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':main()
