#!/usr/bin/env python3
"""Build native CPU libraries and the Android application using installed tools."""
import argparse,os,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--ndk',required=True,type=Path);p.add_argument('--sdk',required=True,type=Path);p.add_argument('--java',required=True,type=Path);p.add_argument('--gradle',required=True);p.add_argument('--ninja',type=Path);p.add_argument('--cmake',default='cmake');p.add_argument('--jobs',type=int,default=4);p.add_argument('--model-assets',type=Path);p.add_argument('--release',action='store_true');a=p.parse_args();out=ROOT/'build/android-app-native';libs=ROOT/'build/android-app-libs/arm64-v8a';cmd=['python3',str(ROOT/'tools/build.py'),'--platform','android-arm64','--source',str(a.source.resolve()),'--out',str(out),'--ndk',str(a.ndk.resolve()),'--android-jni','--jobs',str(a.jobs),'--cmake',a.cmake]
 if a.ninja:cmd+=['--ninja',str(a.ninja.resolve())]
 subprocess.run(cmd,check=True);libs.mkdir(parents=True,exist_ok=True)
 for n in ['libaudiocpp.so','libortts_jni.so','libortts_device.so']:shutil.copyfile(out/n,libs/n)
 prebuilt=next(p for p in (a.ndk/'toolchains/llvm/prebuilt').iterdir() if (p/'sysroot/usr/lib/aarch64-linux-android/libc++_shared.so').is_file())
 shutil.copyfile(prebuilt/'sysroot/usr/lib/aarch64-linux-android/libc++_shared.so',libs/'libc++_shared.so')
 gradle=[a.gradle,'--offline','--no-daemon','-p',str(ROOT/'android'),':app:assembleRelease' if a.release else ':app:assembleDebug','-PnativeLibsDir='+str(libs.parent)]
 if a.model_assets:gradle+=['-PmodelAssetsDir='+str(a.model_assets.resolve())]
 subprocess.run(gradle,check=True,env={**os.environ,'JAVA_HOME':str(a.java.resolve()),'ANDROID_HOME':str(a.sdk.resolve())});print(ROOT/('android/app/build/outputs/apk/release/app-release-unsigned.apk' if a.release else 'android/app/build/outputs/apk/debug/app-debug.apk'))
