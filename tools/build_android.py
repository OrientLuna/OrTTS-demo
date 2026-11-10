#!/usr/bin/env python3
"""Build native CPU libraries and the Android application using installed tools."""
import argparse,os,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--ndk',required=True,type=Path);p.add_argument('--sdk',required=True,type=Path);p.add_argument('--java',required=True,type=Path);p.add_argument('--gradle',required=True);p.add_argument('--ninja',type=Path);p.add_argument('--cmake',default='cmake');p.add_argument('--jobs',type=int,default=4);p.add_argument('--model-assets',type=Path);p.add_argument('--release',action='store_true');p.add_argument('--cpu-auto',action='store_true',help='Package baseline, DotProd and I8MM CPU modules together');p.add_argument('--liquidcodec',action='store_true');p.add_argument('--speech',action='store_true');p.add_argument('--g2p-install',type=Path);a=p.parse_args();
 if a.speech and not a.g2p_install:p.error('--speech mobile Demo requires --g2p-install from build_mobile_g2p.py')
 out=ROOT/'build/android-app-native';libs=ROOT/'build/android-app-libs/arm64-v8a';cmd=['python3',str(ROOT/'tools/build.py'),'--platform','android-arm64','--source',str(a.source.resolve()),'--out',str(out),'--ndk',str(a.ndk.resolve()),'--android-jni','--jobs',str(a.jobs),'--cmake',a.cmake]
 if a.cpu_auto:cmd+=['--cpu-auto']
 if a.liquidcodec:cmd+=['--liquidcodec']
 if a.speech:cmd+=['--speech']
 if a.ninja:cmd+=['--ninja',str(a.ninja.resolve())]
 subprocess.run(cmd,check=True);libs.mkdir(parents=True,exist_ok=True)
 for n in ['libaudiocpp.so','libortts_jni.so','libortts_device.so']:shutil.copyfile(out/n,libs/n)
 cpu_libs=['libggml.so','libggml-base.so','libggml-cpu-android_armv8.0_1.so','libggml-cpu-android_armv8.2_2.so','libggml-cpu-android_armv8.6_1.so']
 for n in cpu_libs:
  if a.cpu_auto:shutil.copyfile(out/'bin'/n,libs/n)
  elif (libs/n).exists():(libs/n).unlink()
 prebuilt=next(p for p in (a.ndk/'toolchains/llvm/prebuilt').iterdir() if (p/'sysroot/usr/lib/aarch64-linux-android/libc++_shared.so').is_file())
 shutil.copyfile(prebuilt/'sysroot/usr/lib/aarch64-linux-android/libc++_shared.so',libs/'libc++_shared.so')
 if a.g2p_install:
  shutil.copyfile(a.g2p_install/'libespeak-ng.so',libs/'libespeak-ng.so')
  assets=ROOT/'build/android-g2p-assets';assets.mkdir(parents=True,exist_ok=True)
  for name in ['espeak-ng-data','licenses']:shutil.copytree(a.g2p_install/name,assets/name,dirs_exist_ok=True)
 gradle=[a.gradle,'--offline','--no-daemon','-p',str(ROOT/'android'),':app:assembleRelease' if a.release else ':app:assembleDebug','-PnativeLibsDir='+str(libs.parent)]
 gradle+=['-PnativeCpuProfile='+('arm64-auto' if a.cpu_auto else 'arm64-baseline' if a.speech else 'arm64-i8mm')]
 if a.speech:gradle+=['-Pg2pAssetsDir='+str(assets)]
 if a.model_assets:gradle+=['-PmodelAssetsDir='+str(a.model_assets.resolve())]
 subprocess.run(gradle,check=True,env={**os.environ,'JAVA_HOME':str(a.java.resolve()),'ANDROID_HOME':str(a.sdk.resolve())});print(ROOT/('android/app/build/outputs/apk/release/app-release-unsigned.apk' if a.release else 'android/app/build/outputs/apk/debug/app-debug.apk'))
