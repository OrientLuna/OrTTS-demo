#!/usr/bin/env python3
"""Package two already-built iOS framework slices; never signs or installs apps."""
import argparse
import json
import platform
import subprocess
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device',type=Path,required=True)
    p.add_argument('--simulator',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    device=a.device.resolve();simulator=a.simulator.resolve();out=a.out.resolve()
    if out.exists():raise ValueError('Use a new XCFramework path')
    cmd=['xcodebuild','-create-xcframework','-framework',str(device),'-framework',str(simulator),'-output',str(out)]
    print(json.dumps({'argv':cmd,'status':'PLAN_ONLY' if a.dry_run else 'PACKAGING'},indent=2))
    if a.dry_run:return
    if platform.system()!='Darwin':raise RuntimeError('Requires Xcode on a Mac')
    for path in (device,simulator):
        if not (path/'Headers/ortts_engine.h').is_file():raise ValueError('Missing public engine header: '+str(path))
        if not (path/'Modules/module.modulemap').is_file():raise ValueError('Missing Swift module map: '+str(path))
    subprocess.run(cmd,check=True)
    sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    subprocess.run(['xcrun','swiftc','-typecheck','-target','arm64-apple-ios16.0',
                    '-sdk',sdk,'-F',str(device.parent),
                    str(Path(__file__).resolve().parents[1]/'runtime/examples/ImportSmoke.swift')],check=True)

if __name__=='__main__':main()
