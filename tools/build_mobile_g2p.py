#!/usr/bin/env python3
"""Build pinned eSpeak NG mobile libraries. Uses supplied sources/data, no downloads."""
import argparse,subprocess,shutil,json,hashlib,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PIN='4870adfa25b1a32b4361592f1be8a40337c58d6c'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--target',choices=['ios','sim','android'],required=True);p.add_argument('--ndk',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 source=a.source.resolve();out=a.out.resolve()
 if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=PIN:raise ValueError('Expected eSpeak NG 1.52.0 pinned commit')
 for name in ['phontab','phondata','phonindex','en_dict']:
  if not (a.data/name).is_file():raise ValueError('Missing compiled 1.52.0 data: '+name)
 subprocess.run(['cmake','-DSOURCE_DIR='+str(source),'-P',str(ROOT/'tools/g2p/espeak_patch.cmake')],check=True)
 changed=set(subprocess.check_output(['git','-C',str(source),'diff','HEAD','--name-only'],text=True).splitlines())
 if changed-{'cmake/deps.cmake','src/CMakeLists.txt'}:raise ValueError('Unexpected eSpeak source modifications')
 for name in ['cmake/deps.cmake','src/CMakeLists.txt']:
  original=subprocess.check_output(['git','-C',str(source),'show','HEAD:'+name]).decode()
  if name=='cmake/deps.cmake':expected=original.replace('else()\n  FetchContent_Declare(sonic-git','elseif(USE_LIBSONIC)\n  FetchContent_Declare(sonic-git')
  else:expected=original+'\n# Avoid colliding with the static espeak-ng library on MSVC.\nset_target_properties(espeak-ng-bin PROPERTIES ARCHIVE_OUTPUT_NAME espeak-ng-tool)\n'
  if (source/name).read_text()!=expected:raise ValueError('Unexpected patched source: '+name)
 flags=['-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_FLAGS=-DN_PATH_HOME=4096','-DBUILD_SHARED_LIBS=ON','-DUSE_ASYNC=OFF','-DUSE_LIBSONIC=OFF','-DUSE_LIBPCAUDIO=OFF','-DUSE_MBROLA=OFF','-DBUILD_TESTING=OFF','-DFETCHCONTENT_FULLY_DISCONNECTED=ON','-DCMAKE_POLICY_VERSION_MINIMUM=3.5']
 if a.target=='android':
  if not a.ndk:p.error('--ndk required')
  flags+=['-DCMAKE_TOOLCHAIN_FILE='+str(a.ndk.resolve()/'build/cmake/android.toolchain.cmake'),'-DANDROID_ABI=arm64-v8a','-DANDROID_PLATFORM=android-28','-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384']
 else:flags+=['-DCMAKE_SYSTEM_NAME=iOS','-DCMAKE_OSX_SYSROOT='+('iphoneos' if a.target=='ios' else 'iphonesimulator'),'-DCMAKE_OSX_ARCHITECTURES=arm64','-DCMAKE_OSX_DEPLOYMENT_TARGET=16.3','-DCMAKE_MACOSX_BUNDLE=OFF','-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO','-DCMAKE_C_FLAGS=-DN_PATH_HOME=4096 -include libkern/OSByteOrder.h -Dle16toh=OSSwapLittleToHostInt16 -Dle32toh=OSSwapLittleToHostInt32']
 subprocess.run(['cmake','-S',str(source),'-B',str(out),'-G','Ninja']+flags,check=True);subprocess.run(['cmake','--build',str(out),'--target','espeak-ng','-j','3'],check=True)
 stage=out/'mobile';stage.mkdir(exist_ok=True);shutil.copytree(a.data,stage/'espeak-ng-data',dirs_exist_ok=True)
 if a.target=='android':shutil.copyfile(out/'src/libespeak-ng/libespeak-ng.so',stage/'libespeak-ng.so')
 else:
  fw=stage/'espeak-ng.framework';fw.mkdir(exist_ok=True);shutil.copyfile(out/'src/libespeak-ng/libespeak-ng.1.52.0.dylib',fw/'espeak-ng');subprocess.run(['install_name_tool','-id','@rpath/espeak-ng.framework/espeak-ng',str(fw/'espeak-ng')],check=True)
  import plistlib
  (fw/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'org.espeak-ng.phonemizer','CFBundleExecutable':'espeak-ng','CFBundleName':'espeak-ng','CFBundlePackageType':'FMWK','CFBundleVersion':'1','CFBundleShortVersionString':'1.52.0','MinimumOSVersion':'16.3'}))
 with tarfile.open(out/'espeak-ng-corresponding-source.tar.gz','w:gz') as archive:
  for entry in source.iterdir():
   if entry.name!='.git':archive.add(entry,arcname='espeak-ng/'+entry.name)
  archive.add(ROOT/'tools/build_mobile_g2p.py',arcname='OrTTS/tools/build_mobile_g2p.py');archive.add(ROOT/'tools/g2p/espeak_patch.cmake',arcname='OrTTS/tools/g2p/espeak_patch.cmake')
 license_dir=stage/'licenses';license_dir.mkdir(exist_ok=True)
 for name in ['COPYING','COPYING.APACHE','COPYING.BSD2','COPYING.UCD']:shutil.copyfile(source/name,license_dir/name)
 (stage/'receipt.json').write_text(json.dumps({'source_commit':PIN,'target':a.target,'data_sha256':{str(f.relative_to(a.data)):hashlib.sha256(f.read_bytes()).hexdigest() for f in a.data.rglob('*') if f.is_file()},'license':'GPL-3.0-or-later; combined distribution must meet GPL obligations'},indent=2)+'\n')
if __name__=='__main__':main()
