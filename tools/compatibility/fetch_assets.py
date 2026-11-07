#!/usr/bin/env python3
"""Explicit opt-in download of a pinned compatibility corpus (no credentials)."""
import argparse,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--manifest',type=Path,default=Path(__file__).with_name('assets.json'));a=p.parse_args()
for entry in json.loads(a.manifest.read_text())['assets']:
 dest=a.out/entry['path'];dest.parent.mkdir(parents=True,exist_ok=True)
 def valid():
  return dest.exists() and dest.stat().st_size==entry['bytes'] and hashlib.file_digest(dest.open('rb'),'sha256').hexdigest()==entry['sha256']
 if not valid():
  part=dest.with_name(dest.name+'.part')
  subprocess.run(['curl','-fL','--retry','2','--connect-timeout','30','-o',str(part),f"https://huggingface.co/{entry['repo']}/resolve/{entry['revision']}/{entry['path']}"],check=True)
  if part.stat().st_size!=entry['bytes'] or hashlib.file_digest(part.open('rb'),'sha256').hexdigest()!=entry['sha256']:raise ValueError('Asset identity mismatch: '+entry['path'])
  part.replace(dest)
 print('VERIFIED',dest)
