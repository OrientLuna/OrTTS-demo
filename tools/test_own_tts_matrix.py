#!/usr/bin/env python3
"""iPhone P3/P5 warm matrix (explicit LiquidCodec or legacy pack); uses existing verified app-container assets."""
import argparse,json,subprocess,time,uuid
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--install',type=Path);p.add_argument('--voice',choices=['female','male'],default='female');p.add_argument('--cooldown',type=int,default=0,choices=range(0,181));p.add_argument('--text');p.add_argument('--pack',choices=['liquid','legacy'],default='liquid');p.add_argument('--case',action='append',choices=[f'{v}-{l}-{n}' for v in ['P3','P5'] for l in ['zh','en'] for n in ['short','long']],help='Restrict to P3-zh-short etc.');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 def run(args,check=True):
  r=subprocess.run(args,capture_output=True,text=True)
  if check and r.returncode:raise RuntimeError(r.stdout+r.stderr)
  return r
 base=['xcrun','devicectl','device']
 if a.install:run(base+['install','app','--device',a.device,str(a.install)])
 texts={'en_short':'At nine thirty, please check the train ticket and call the station.','en_long':'At nine thirty, please check the train ticket and call the station. Before leaving home, make sure you have your keys, wallet, and phone. If the train is delayed, send a message to your family and wait near the information desk.','zh_short':'今天上午九点半，请检查车票和随身行李。','zh_long':'今天上午九点半，我们准备乘坐高铁去参加会议。出发前，请仔细检查车票、身份证和随身行李，确认手机已经充满电。如果途中遇到列车晚点，请及时联系同事，并在车站服务台附近耐心等候。'}
 rows=[]
 for variant in ['P3','P5']:
  for lang in ['zh','en']:
   for length in ['short','long']:
    key=f'{variant}-{lang}-{length}'
    if a.case and key not in a.case:continue
    directory=a.out/key;directory.mkdir(exist_ok=True);token=key+'-'+uuid.uuid4().hex[:8]
    args=['--synthesis-smoke','--benchmark-repeat','4','--benchmark-run-id',token,'--benchmark-text',a.text or texts[lang+'_'+length],'--benchmark-cooldown',str(a.cooldown)]
    if variant=='P5':args+=['--benchmark-p5']
    if a.voice=='male':args+=['--benchmark-male']
    if a.pack=='legacy':args+=['--benchmark-legacy']
    run(base+['process','launch','--device',a.device,'--terminate-existing','com.orient.ortts.prototype','--']+args)
    start=time.monotonic();record=None;file=directory/'result.json'
    while time.monotonic()-start<600:
     r=run(base+['copy','from','--device',a.device,'--domain-type','appDataContainer','--domain-identifier','com.orient.ortts.prototype','--source','Documents/own-benchmark-result.json','--destination',str(file),'--quiet'],check=False)
     if not r.returncode:
      try:
       candidate=json.loads(file.read_text())
       if candidate.get('run_id')==token:record=candidate;break
      except (ValueError,OSError):pass
     time.sleep(1)
    if record is None:raise RuntimeError('Own benchmark timeout: '+key)
    expected='liquidcodec' if a.pack=='liquid' else 'qwen_lfm'
    if record.get('decoder')!=expected:raise RuntimeError('Wrong decoder selected: '+str(record.get('decoder')))
    if record['ok']:
     if len(record['runs'])!=4 or [r['engine_reused'] for r in record['runs']]!=[False,True,True,True]:raise RuntimeError('Invalid warm sequence')
     run(base+['copy','from','--device',a.device,'--domain-type','appDataContainer','--domain-identifier','com.orient.ortts.prototype','--source','Documents/own-benchmark.caf','--destination',str(directory/'sample.caf'),'--quiet'])
    rows.append({'variant':variant,'language':lang,'length':length,'text':a.text or texts[lang+'_'+length],'result':record});(a.out/'results.json').write_text(json.dumps({'cases':rows},ensure_ascii=False,indent=2)+'\n');print(key,'PASS' if record['ok'] else 'FAILED: '+record['error'],flush=True)
if __name__=='__main__':main()
