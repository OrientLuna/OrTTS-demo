#!/usr/bin/env python3
"""Conservative ASR preset selection; identity-specific evidence, never CPU-tier guesses."""
import argparse
import json
import re
from pathlib import Path

def select(whitelist, device, runtime_sha256, model_identity, protocol):
    keys=('os','hardware','os_build','ram_mib','cpu')
    if not all(isinstance(x,str) and re.fullmatch('[a-f0-9]{64}',x) for x in (runtime_sha256,model_identity)):
        return {'status':'unverified','recipe_id':None,'reason':'Missing fixed runtime/recipe identity'}
    for disposition in ('rejected','approved'):
        for entry in whitelist.get(disposition,[]):
            if (all(entry.get('device',{}).get(k)==device.get(k) for k in keys)
                and all(device.get(k) is not None for k in keys)
                and entry.get('runtime_sha256')==runtime_sha256
                and entry.get('model_identity')==model_identity
                and entry.get('protocol')==protocol):
                return {'status':'recommended' if disposition=='approved' else 'not-recommended',
                        'recipe_id':entry.get('recipe_id') if disposition=='approved' else None,
                        'evidence':entry.get('evidence'),'reason':entry.get('reason')}
    return {'status':'unverified','recipe_id':None,'reason':'No matching physical-device acceptance; no automatic low-end default'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--whitelist',type=Path,default=Path(__file__).resolve().parents[1]/'runtime/models/asr-device-whitelist.json')
    p.add_argument('--device',type=Path,required=True)
    p.add_argument('--runtime-sha256',required=True)
    p.add_argument('--model-identity',required=True)
    p.add_argument('--protocol',default='ortts-asr-low-end-v1')
    a=p.parse_args();print(json.dumps(select(json.loads(a.whitelist.read_text()),json.loads(a.device.read_text()),a.runtime_sha256,a.model_identity,a.protocol),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
