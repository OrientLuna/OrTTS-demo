#!/usr/bin/env python3
from pathlib import Path
import argparse
import subprocess,json,sys
p=argparse.ArgumentParser(description='Warm TTS matrix: four calls per supported cell, no playback or downloads');p.add_argument('--target',choices=['iphone','simulator','android'],default='iphone');p.add_argument('--device',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--install',type=Path);a=p.parse_args();out=a.out;out.mkdir(parents=True,exist_ok=True)
texts={'en_short':'At nine thirty, please check the train ticket and call the station.','en_long':'At nine thirty, please check the train ticket and call the station. Before leaving home, make sure you have your keys, wallet, and phone. If the train is delayed, send a message to your family and wait near the information desk.','zh_short':'今天上午九点半，请检查车票和随身行李。','zh_long':'今天上午九点半，我们准备乘坐高铁去参加会议。出发前，请仔细检查车票、身份证和随身行李，确认手机已经充满电。如果途中遇到列车晚点，请及时联系同事，并在车站服务台附近耐心等候。'}
rows=[];index=0
for model,case,languages in [('kokoro','kokoro-en',['en','zh']),('pocket','pocket-alba',['en']),('kitten','kitten-bella',['en']),('piper','piper-lessac',['en'])]:
 for language in languages:
  for length in ['short','long']:
   case_name='kokoro-zh' if model=='kokoro' and language=='zh' else case
   label=f'{model}-{language}-{length}';cmd=[sys.executable,'tools/test_mobile_speech_demo.py','--target',a.target,'--device',a.device,'--no-playback','--repeat','4','--case',case_name,'--text',texts[language+'_'+length],'--out',str(out/label)]
   if index==0 and a.install:cmd+=['--install',str(a.install)]
   subprocess.run(cmd,check=True);row=json.loads((out/label/(case_name+'.json')).read_text());rows.append({'model':model,'language':language,'length':length,'text':texts[language+'_'+length],'result':row});(out/'results.json').write_text(json.dumps({'cases':rows},ensure_ascii=False,indent=2)+'\n');print(label,'COMPLETE',flush=True);index+=1
