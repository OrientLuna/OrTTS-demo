#!/usr/bin/env python3
"""Exercise the Apple own-TTS button path and wait for its playback queue to drain.

Uses already installed, verified model assets; no downloads or microphone input.
Device IDs and app-console logs are kept only in the caller's local output folder.
"""
import argparse,json,os,selectors,subprocess,time
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--target',choices=['iphone','simulator'],required=True);p.add_argument('--device',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--pack',choices=['liquid','legacy'],default='liquid');p.add_argument('--variant',choices=['P3','P5'],default='P3');p.add_argument('--voice',choices=['female','male'],default='female');p.add_argument('--text',default='你好，欢迎使用本地语音合成。');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 bundle='com.orient.ortts.prototype'
 cmd=['xcrun','devicectl','device','process','launch','--device',a.device,'--terminate-existing','--console',bundle,'--'] if a.target=='iphone' else ['xcrun','simctl','launch','--console','--terminate-running-process',a.device,bundle]
 cmd+=['--synthesis-smoke','--benchmark-text',a.text]
 if a.pack=='legacy':cmd+=['--benchmark-legacy']
 if a.variant=='P5':cmd+=['--benchmark-p5']
 if a.voice=='male':cmd+=['--benchmark-male']
 proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);selector=selectors.DefaultSelector();selector.register(proc.stdout,selectors.EVENT_READ);data=b'';start=time.monotonic();complete=False;drained=False;error=''
 try:
  while time.monotonic()-start<120:
   if selector.select(1):
    chunk=os.read(proc.stdout.fileno(),65536)
    if not chunk:break
    data+=chunk;decoded=data.decode(errors='replace')
    complete='OrTTS result: 完成' in decoded;drained='OrTTS stream drained' in decoded
    if complete and drained:break
    if 'OrTTS result:' in decoded and not complete:error='Synthesis reported an error';break
   if proc.poll() is not None:break
 finally:
  proc.terminate()
  try:proc.wait(timeout=5)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
  selector.close();(a.out/'console.log').write_bytes(data)
 report={'target':a.target,'pack':a.pack,'variant':a.variant,'voice':a.voice,'text':a.text,'synthesis_completed':complete,'playback_drained':drained,'ok':complete and drained,'error':error,'scope':'normal UI synthesis and CoreAudio queue drain; no acoustic listening certificate'}
 (a.out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if not report['ok']:raise RuntimeError('Normal playback failed; inspect local console.log')
 print(a.target,a.pack,a.variant,a.voice,'normal playback PASS')
if __name__=='__main__':main()
