#!/usr/bin/env python3
"""Compile the shared iOS app icon for CMake bundles and merge actool's plist keys."""
import argparse
from pathlib import Path
import plistlib
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app',required=True,type=Path)
    p.add_argument('--platform',required=True,choices=['iphoneos','iphonesimulator'])
    a=p.parse_args();app=a.app.resolve();partial=app.parent/(app.stem+'-icons.plist')
    subprocess.run(['xcrun','actool','--compile',str(app),'--platform',a.platform,'--minimum-deployment-target','16.3','--app-icon','AppIcon','--target-device','iphone','--output-partial-info-plist',str(partial),str(ROOT/'apple/Assets.xcassets')],check=True)
    info=app/'Info.plist';data=plistlib.loads(info.read_bytes());data.update(plistlib.loads(partial.read_bytes()));info.write_bytes(plistlib.dumps(data))
if __name__=='__main__':main()
