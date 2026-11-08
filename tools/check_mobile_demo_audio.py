#!/usr/bin/env python3
"""Check generated mobile Demo audio, not perceptual quality. No downloads."""
import argparse,hashlib,json,math,struct,subprocess
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);rows=[]
 for source in sorted(a.input.iterdir()):
  if source.suffix not in ('.wav','.caf'):continue
  file=source
  if source.suffix=='.caf':
   file=a.out/(source.stem+'.wav');subprocess.run(['afconvert',str(source),str(file),'-f','WAVE','-d','LEF32'],check=True,capture_output=True)
  blob=file.read_bytes();pos=12;fmt=None;data=None
  if blob[:4]!=b'RIFF' or blob[8:12]!=b'WAVE':raise ValueError('Expected WAVE: '+source.name)
  while pos+8<=len(blob):
   kind=blob[pos:pos+4];n=struct.unpack_from('<I',blob,pos+4)[0];chunk=blob[pos+8:pos+8+n];pos+=8+n+(n&1)
   if len(chunk)!=n:raise ValueError('Truncated WAVE')
   if kind==b'fmt ':fmt=struct.unpack_from('<HHIIHH',chunk)
   if kind==b'data':data=chunk
  if not fmt or not data or fmt[1]!=1 or fmt[5]!=32 or fmt[0] not in (3,65534):raise ValueError('Expected mono F32: '+source.name)
  samples=[x[0] for x in struct.iter_unpack('<f',data)]
  if not all(math.isfinite(x) for x in samples):raise ValueError('Nonfinite audio: '+source.name)
  rms=math.sqrt(sum(x*x for x in samples)/len(samples));peak=max(abs(x) for x in samples)
  if rms<=1e-5 or peak>=5:raise ValueError('Empty or exploded signal: '+source.name)
  expected=22050 if source.stem.startswith('piper-') else 24000
  if fmt[2]!=expected:raise ValueError('Native sample rate lost: '+source.name)
  rows.append({'case':source.stem,'rate':fmt[2],'frames':len(samples),'duration_s':len(samples)/fmt[2],'rms':rms,'peak':peak,'over_one_fraction':sum(abs(x)>1 for x in samples)/len(samples),'pcm_sha256':hashlib.sha256(data).hexdigest()})
 if not rows:raise ValueError('No generated audio')
 voices=[r for r in rows if r['case'] in ('kitten-bella','kitten-leo')]
 if len(voices)==2 and voices[0]['pcm_sha256']==voices[1]['pcm_sha256']:raise ValueError('Different Kitten presets produced identical PCM')
 report={'checks':rows,'scope':'format/finite/nonempty signal, native rate, distinct Kitten waveforms; no perceptual quality certification'}
 (a.out/'checks.json').write_text(json.dumps(report,indent=2)+'\n');print('audio checks passed:',len(rows))
if __name__=='__main__':main()
