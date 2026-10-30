#!/usr/bin/env python3
"""Configure/build CPU runtime using explicitly supplied local toolchains. No downloads."""
import argparse,json,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def commands(a):
    source=a.source.resolve();receipt=json.loads((source/'ORTTS_SOURCE_RECEIPT.json').read_text());lock=json.loads((ROOT/'vendor/runtime.lock.json').read_text())
    if receipt['base_commit']!=lock['base_commit'] or receipt['patch_sha256']!=lock['patch_sha256']:raise ValueError('Wrong prepared source identity')
    if receipt.get('additional_patches',[])!=lock.get('additional_patches',[]):raise ValueError('Wrong additional patch identity')
    for item in lock['selected_files']:
        if hashlib.sha256((source/item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Prepared integration source modified: '+item['path'])
    out=a.out.resolve() if a.out else ROOT/'build'/a.platform
    cmd=[a.cmake,'-S',str(ROOT),'-B',str(out),'-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DORTTS_AUDIOCPP_SOURCE='+str(source)]
    if getattr(a,'android_jni',False):cmd+=['-DORTTS_BUILD_ANDROID_JNI=ON']
    if a.ninja:cmd+=['-DCMAKE_MAKE_PROGRAM='+str(a.ninja.resolve())]
    if a.platform=='android-arm64':
        if not a.ndk:raise ValueError('--ndk is required; no SDK is downloaded')
        cmd+=['-DCMAKE_TOOLCHAIN_FILE='+str(a.ndk.resolve()/'build/cmake/android.toolchain.cmake'),'-DANDROID_ABI=arm64-v8a','-DANDROID_PLATFORM=android-28','-DANDROID_STL=c++_shared','-DGGML_CPU_ARM_ARCH='+a.android_isa]
    elif a.platform=='linux-aarch64':
        cmd+=['-DCMAKE_TOOLCHAIN_FILE='+str(ROOT/'platforms/linux-aarch64/toolchain.cmake'),'-DORTTS_C_COMPILER='+a.cc,'-DORTTS_CXX_COMPILER='+a.cxx,'-DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16']
        if a.sysroot:cmd+=['-DORTTS_TARGET_SYSROOT='+str(a.sysroot.resolve())]
    targets=['ortts_jni','ortts_device'] if getattr(a,'android_jni',False) else ['ortts-tts']
    return out,[cmd,[a.cmake,'--build',str(out),'--target',*targets,'--parallel',str(a.jobs)]]
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cmake',default='cmake');p.add_argument('--ninja',type=Path);p.add_argument('--platform',choices=['android-arm64','linux-aarch64','linux-x86_64'],required=True);p.add_argument('--source',type=Path,default=ROOT/'_work/audio.cpp');p.add_argument('--out',type=Path);p.add_argument('--ndk',type=Path);p.add_argument('--android-isa',default='armv8.2-a+dotprod+i8mm+fp16',choices=['armv8-a','armv8.2-a+dotprod+i8mm+fp16']);p.add_argument('--sysroot',type=Path);p.add_argument('--cc',default='aarch64-linux-gnu-gcc');p.add_argument('--cxx',default='aarch64-linux-gnu-g++');p.add_argument('--jobs',type=int,default=4);p.add_argument('--dry-run',action='store_true');p.add_argument('--configure-only',action='store_true');p.add_argument('--android-jni',action='store_true');a=p.parse_args()
    if not 1<=a.jobs<=16:p.error('jobs must be1..16')
    out,cmds=commands(a);print(json.dumps({'platform':a.platform,'argv':cmds},indent=2))
    if not a.dry_run:
        out.mkdir(parents=True,exist_ok=True)
        for cmd in cmds[:1] if a.configure_only else cmds:subprocess.run(cmd,check=True)
        (out/'ORTTS_BUILD_RECEIPT.json').write_text(json.dumps({'platform':a.platform,'configure_only':a.configure_only,'argv':cmds},indent=2)+'\n')
