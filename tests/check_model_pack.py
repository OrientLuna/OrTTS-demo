#!/usr/bin/env python3
"""Exercise manifest dispatch without loading a model or accessing a device."""
from pathlib import Path
import argparse,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);a=p.parse_args();s=a.source.resolve()
 with tempfile.TemporaryDirectory(prefix='ortts-pack-test-')as tmp:
  d=Path(tmp);subprocess.run(['cc','-c',str(s/'external/cJSON/cJSON.c'),'-o',str(d/'cjson.o')],check=True)
  for mode in [0,1]:
   binary=d/('pack-'+str(mode));cmd=['c++','-std=c++17','-DORTTS_WITH_LIQUIDCODEC='+str(mode),'-I'+str(ROOT/'runtime/src'),'-I'+str(s/'include'),'-I'+str(s/'external/cJSON'),str(ROOT/'tests/model_pack.cpp'),str(s/'src/framework/io/json.cpp'),str(s/'src/framework/io/filesystem.cpp'),str(d/'cjson.o'),'-o',str(binary)]
   subprocess.run(cmd,check=True);subprocess.run([str(binary),str(d/('fixture-'+str(mode)))],check=True)
if __name__=='__main__':main()
