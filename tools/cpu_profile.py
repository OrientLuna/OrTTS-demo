#!/usr/bin/env python3
"""Recommend a CPU profile before loading any OrTTS native library."""
import json
import platform
from pathlib import Path

def choose(machine, system, per_core_features):
    features=set.intersection(*per_core_features) if per_core_features else set()
    if machine in ('x86_64','AMD64'):
        required={'sse4_2','avx','avx2','fma','f16c','bmi2'}
        return 'x86_64-avx2' if system=='Linux' and required<=features else 'x86_64-baseline'
    if machine in ('arm64','aarch64'):
        if system=='Linux' and {'fphp','asimdhp','asimddp'}<=features:
            return 'arm64-i8mm' if 'i8mm' in features else 'arm64-dotprod'
        return 'arm64-baseline'
    raise ValueError('Unsupported CPU architecture: '+machine)

if __name__=='__main__':
    system=platform.system();machine=platform.machine();cores=[]
    if system=='Linux':
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if ':' in line and line.split(':',1)[0].strip() in ('flags','Features'):
                cores.append(set(line.split(':',1)[1].split()))
    print(json.dumps({'machine':machine,'system':system,'profile':choose(machine,system,cores),
                      'automatic_library_loading':False,'feature_scope':'intersection of exposed CPU feature lists; baseline if unknown'},indent=2))
