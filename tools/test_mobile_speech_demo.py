#!/usr/bin/env python3
"""Exercise foreground Demo UI pipelines with local models. Never records mic.

Use an already signed/installed app, or --install an appropriate app/APK.
--seed copies existing local assets into this app's test container, no downloads.
Physical device identifiers remain CLI arguments and are omitted from reports.
"""
import argparse
import io
import re
import struct
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import tarfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
IOS='com.orient.ortts.prototype';ANDROID='com.orient.ortts'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target',choices=['simulator','iphone','android'],required=True)
    p.add_argument('--device',required=True)
    p.add_argument('--install',type=Path)
    p.add_argument('--seed',action='store_true')
    p.add_argument('--case',action='append',help='Run only the named case(s)')
    p.add_argument('--assets',type=Path,default=Path('local/compat/assets'))
    p.add_argument('--fixtures',type=Path,default=Path('outputs/demo-0.4-fixtures'))
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--adb',type=Path,default=Path.home()/'Library/Android/sdk/platform-tools/adb')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    def run(cmd,check=True,**kwargs):
        result=subprocess.run(cmd,capture_output=True,**kwargs)
        if check and result.returncode:
            raise RuntimeError((result.stdout+result.stderr).decode(errors='replace'))
        return result
    adb=[str(a.adb),'-s',a.device]
    device=['xcrun','devicectl','device']
    if a.install:
        if a.target=='android':run(adb+['install','-r',str(a.install)])
        elif a.target=='simulator':run(['xcrun','simctl','install',a.device,str(a.install)])
        else:run(device+['install','app','--device',a.device,str(a.install)])
    container=None
    if a.target=='simulator':
        container=Path(run(['xcrun','simctl','get_app_container',a.device,IOS,'data']).stdout.decode().strip())/'Documents'
    if a.seed:
        catalog=json.loads((ROOT/'runtime/models/catalog.example.json').read_text())
        assets={asset['path'] for m in catalog['models'] if m['demo_enabled'] for asset in m['assets']}
        if a.target=='android':
            run(adb+['shell','run-as',ANDROID,'mkdir','-p','files'])
            process=subprocess.Popen(adb+['shell','-T','run-as',ANDROID,'tar','-C','files','-xf','-'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            with tarfile.open(fileobj=process.stdin,mode='w|',format=tarfile.USTAR_FORMAT) as archive:
                for asset in sorted(assets):archive.add(a.assets/asset,arcname='speech-models/'+asset)
                for name in ['speech-test-en.wav','speech-test-zh.wav']:archive.add(a.fixtures/name,arcname=name)
            process.stdin.close();process.stdin=None
            stdout,stderr=process.communicate(timeout=180)
            if process.returncode:raise RuntimeError(stderr.decode())
            run(adb+['shell','run-as',ANDROID,'test','-f','files/speech-test-en.wav'])
        else:
            for asset in sorted(assets):
                source=a.assets/asset
                if container:
                    target=container/'speech-models'/asset;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
                else:run(device+['copy','to','--device',a.device,'--domain-type','appDataContainer','--domain-identifier',IOS,'--source',str(source),'--destination','Documents/speech-models/'+asset,'--quiet'])
            for name in ['speech-test-en.wav','speech-test-zh.wav']:
                if container:shutil.copyfile(a.fixtures/name,container/name)
                else:run(device+['copy','to','--device',a.device,'--domain-type','appDataContainer','--domain-identifier',IOS,'--source',str(a.fixtures/name),'--destination','Documents/'+name,'--quiet'])
        print('seeded existing local models',flush=True)
    cases=[('kokoro-en','tts','kokoro-82m-q8','af_heart','',0),
           ('kokoro-zh','tts','kokoro-82m-q8','zf_xiaobei','',0),
           ('kitten-bella','tts','kitten-mini-0.8','Bella','',0),
           ('kitten-leo','tts','kitten-mini-0.8','Leo','',0),
           ('piper-lessac','tts','piper-lessac-medium','','',0),
           ('piper-long','tts','piper-lessac-medium','','',0),
           ('pocket-alba','tts','pocket-english-q8','alba','',0),
           ('pocket-cancel','tts','pocket-english-q8','alba','',500),
           ('pocket-anna','tts','pocket-english-q8','anna','',0),
           ('moonshine-en','asr','moonshine-tiny-q8','','speech-test-en.wav',0),
           ('sensevoice-zh','asr','sensevoice-small-q8','','speech-test-zh.wav',0),
           ('roundtrip','last','moonshine-tiny-q8','','',0),
           ('download-check','download','pocket-english-q8','','',0)]
    if a.case:
        unknown=set(a.case)-{case[0] for case in cases}
        if unknown:p.error('Unknown case(s): '+', '.join(sorted(unknown)))
        cases=[case for case in cases if case[0] in a.case]
    observations=[]
    for name,mode,model,voice,audio,cancel in cases:
        test_id=name+'-'+uuid.uuid4().hex[:8];start=time.monotonic()
        if a.target=='android':
            run(adb+['shell','am','force-stop',ANDROID])
            cmd=adb+['shell','am','start','-n',ANDROID+'/com.orient.ortts.demo.MainActivity','--ez','speech_qa','true',
                '--es','speech_action',mode,'--es','speech_model',model,'--es','speech_qa_id',test_id,
                '--es','speech_text',('今天上午九点半，请检查车票和随身行李。' if name=='kokoro-zh' else ('At nine thirty, please check the train ticket and call the station. '*5 if name=='piper-long' else 'At nine thirty, please check the train ticket and call the station.')),'--es','speech_voice',voice,'--es','speech_audio',audio,'--ei','speech_cancel_ms',str(cancel)]
            # adb shell joins argv; quote even empty strings to preserve extras.
            cmd=adb+['shell',shlex.join(cmd[len(adb)+1:])]
        else:
            args=['--speech-text',('今天上午九点半，请检查车票和随身行李。' if name=='kokoro-zh' else ('At nine thirty, please check the train ticket and call the station. '*5 if name=='piper-long' else 'At nine thirty, please check the train ticket and call the station.')),'--speech-smoke',mode,'--speech-model',model,'--speech-run-id',test_id,
                  '--speech-voice',voice or 'alba','--speech-audio',audio or 'speech-test-en.wav',
                  '--speech-cancel-ms',str(cancel)]
            if container:
                run(['xcrun','simctl','terminate',a.device,IOS],check=False)
                cmd=['xcrun','simctl','launch',a.device,IOS]+args
            else:cmd=device+['process','launch','--device',a.device,'--terminate-existing',IOS,'--']+args
        launched=run(cmd);(a.out/(name+'-launch.log')).write_bytes(launched.stdout+launched.stderr)
        record=None
        while time.monotonic()-start<180:
            try:
                if a.target=='android':
                    result=run(adb+['exec-out','run-as',ANDROID,'cat','files/qa/'+test_id+'.json'],check=False)
                    if result.returncode==0:record=json.loads(result.stdout)
                elif container:
                    record=json.loads((container/'speech-smoke-result.json').read_text())
                    if record.get('run_id')!=test_id:record=None
                else:
                    target=a.out/(name+'-result.json')
                    result=run(device+['copy','from','--device',a.device,'--domain-type','appDataContainer','--domain-identifier',IOS,'--source','Documents/speech-smoke-result.json','--destination',str(target),'--quiet'],check=False)
                    if result.returncode==0:
                        record=json.loads(target.read_text())
                        if record.get('run_id')!=test_id:record=None
            except (OSError,ValueError):record=None
            if record is not None:break
            time.sleep(1)
        if record is None:raise RuntimeError('Demo timeout: '+name)
        record['case']=name;record['process_wall_s']=time.monotonic()-start
        expected=not bool(cancel)
        if bool(record.get('ok'))!=expected:raise RuntimeError(json.dumps(record,ensure_ascii=False))
        text=record.get('text','')
        if (name=='moonshine-en' or (name=='roundtrip' and any(o['case']=='pocket-anna' for o in observations))) and 'station' not in text.lower():raise RuntimeError('English content missing: '+text)
        if name=='sensevoice-zh' and not ('车票' in text or '車票' in text):raise RuntimeError('Chinese content missing: '+text)
        if mode=='tts' and expected:
            if a.target=='android':
                data=run(adb+['exec-out','run-as',ANDROID,'cat','files/speech-last.wav']).stdout
                if data[:4]!=b'RIFF' or len(data)<44:raise RuntimeError('Missing generated WAV')
                record['audio_sample_rate']=struct.unpack_from('<I',data,24)[0]
                (a.out/(name+'.wav')).write_bytes(data)
            elif container:
                audio_path=a.out/(name+'.caf');shutil.copyfile(container/'speech-last.caf',audio_path)
                description=run(['/usr/bin/afinfo',str(audio_path)]).stdout.decode()
                match=re.search(r'(\d+) Hz',description)
                if not match:raise RuntimeError('Missing generated audio rate')
                record['audio_sample_rate']=int(match.group(1))
            if 'audio_sample_rate' in record and record['audio_sample_rate']!=(22050 if name.startswith('piper-') else 24000):raise RuntimeError('Native audio rate mismatch')
        observations.append(record);print(a.target,name,'PASS',flush=True)
        (a.out/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    if container:run(['xcrun','simctl','io',a.device,'screenshot',str(a.out/'screen.png')])
    elif a.target=='android':(a.out/'screen.png').write_bytes(run(adb+['exec-out','screencap','-p']).stdout)
    report={'schema':1,'version':'0.4.0','target':a.target,'cases':observations,
            'scope':'Foreground actual-model Demo pipelines; cached download SHA validation; no microphone recording or new large-model download',
            'limitations':['microphone permission/live capture needs separate interactive validation','cached model check does not certify CDN reachability or full download']}
    (a.out/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
