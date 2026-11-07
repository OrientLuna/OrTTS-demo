#!/usr/bin/env python3
"""Fixed-voice and natural-long ASR comparison through the actual C ABI.

Needs existing local WAV fixtures (no synthesis or downloads in this script).
Synthetic readback checks are regression evidence, not a human-speech benchmark.
"""
import argparse
import array
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

class Pair(C.Structure):_fields_=[('key',C.c_char_p),('value',C.c_char_p)]
class Config(C.Structure):
    _fields_=[('size',C.c_uint32),('family',C.c_char_p),('path',C.c_char_p),('threads',C.c_int32),
              ('streaming',C.c_int32),('options',C.POINTER(Pair)),('count',C.c_size_t),
              ('library',C.c_char_p),('data',C.c_char_p),('limit',C.c_size_t)]
class Settings(C.Structure):
    _fields_=[('size',C.c_uint32),('update',C.c_uint32),('minimum',C.c_uint32),
              ('maximum',C.c_uint32),('silence',C.c_uint32),('threshold',C.c_float)]
class Event(C.Structure):
    _fields_=[('size',C.c_uint32),('endpoint',C.c_int32),('segment',C.c_uint64),
              ('start',C.c_uint64),('end',C.c_uint64),('revision',C.c_uint64),
              ('text',C.c_char_p),('language',C.c_char_p)]
Callback=C.CFUNCTYPE(C.c_int,C.c_void_p,C.POINTER(Event))
Float=C.POINTER(C.c_float)
SHORT='At nine thirty, please check the train ticket and call the station.'
LONG=('Before you leave the house, check that the windows are closed and the back door is locked. '
      'If the weather changes during the afternoon, take the blue umbrella from the hallway and bring a warm jacket. '
      'Please call me when you reach the station so we can decide where to meet for dinner.')

def words(text):
    text=re.sub(r'9[.:]?30','nine thirty',text.lower())
    return re.findall(r'[a-z]+',text)

def wer(reference,text):
    r,h=words(reference),words(text);previous=list(range(len(h)+1))
    for i,a in enumerate(r,1):
        row=[i]
        for j,b in enumerate(h,1):row.append(min(row[-1]+1,previous[j]+1,previous[j-1]+(a!=b)))
        previous=row
    return previous[-1]/len(r)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--library',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--fixtures',type=Path,default=Path('outputs/voices-2026-11-07'))
    p.add_argument('--long',type=Path,default=Path('outputs/asr-stream-2026-11-07/natural-long-alba.wav'))
    p.add_argument('--report',type=Path,default=Path('benchmarks/asr-stream-quality-20261107.json'))
    a=p.parse_args();lib=C.CDLL(str(a.library.resolve()))
    def bind(name,args,result=C.c_int):
        f=getattr(lib,name);f.argtypes=args;f.restype=result;return f
    error=bind('ortts_last_error',[],C.c_char_p)
    create=bind('ortts_asr_stream_create',[C.POINTER(Config),C.POINTER(Settings),C.POINTER(C.c_void_p)])
    accept=bind('ortts_asr_stream_accept',[C.c_void_p,Float,C.c_size_t,Callback,C.c_void_p])
    finish=bind('ortts_asr_stream_finish',[C.c_void_p,Callback,C.c_void_p])
    free=bind('ortts_asr_stream_free',[C.c_void_p],None)
    offline_create=bind('ortts_asr_create',[C.POINTER(Config),C.POINTER(C.c_void_p)])
    run=bind('ortts_asr_run',[C.c_void_p,Float,C.c_size_t,C.c_char_p,C.POINTER(C.c_void_p)])
    offline_free=bind('ortts_asr_free',[C.c_void_p],None)
    text=bind('ortts_transcript_text',[C.c_void_p],C.c_char_p)
    text_free=bind('ortts_transcript_free',[C.c_void_p],None)
    def check(status):
        if status:raise RuntimeError(error().decode())
    cfg=Config();cfg.size=C.sizeof(cfg);cfg.family=b'moonshine_asr';cfg.path=str(a.model.resolve()).encode();cfg.threads=4
    settings=Settings(C.sizeof(Settings),400,1000,30000,0,0.003)
    # Match the stream's F16 encoder and Native decoder rather than comparing
    # a different numerical precision silently.
    options=(Pair*2)(Pair(b'moonshine_asr.weight_type',b'f16'),Pair(b'moonshine_asr.decoder_weight_type',b'native'))
    rows=[]
    for wav,reference in [(a.fixtures/'kokoro-af_heart.wav',SHORT),(a.fixtures/'kokoro-am_adam.wav',SHORT),
                          (a.fixtures/'pocket-anna.wav',SHORT),(a.long,LONG)]:
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(wav),'-ar','16000','-ac','1','-f','f32le','-'])
        audio=array.array('f');audio.frombytes(raw);buffer=(C.c_float*len(audio)).from_buffer(audio)
        cfg.streaming=0;cfg.options=options;cfg.count=2;offline=C.c_void_p();result=C.c_void_p()
        check(offline_create(C.byref(cfg),C.byref(offline)))
        try:
            start=time.monotonic();check(run(offline,buffer,len(audio),b'en',C.byref(result)))
            offline_s=time.monotonic()-start
            try:baseline=text(result).decode()
            finally:text_free(result)
        finally:offline_free(offline)
        cfg.streaming=1;cfg.options=C.POINTER(Pair)();cfg.count=0;stream=C.c_void_p();events=[]
        @Callback
        def receive(_,pointer):
            event=pointer.contents
            events.append({'endpoint':event.endpoint,'start':event.start,'end':event.end,
                           'revision':event.revision,'text':event.text.decode()})
            return 0
        check(create(C.byref(cfg),C.byref(settings),C.byref(stream)))
        try:
            start=time.monotonic()
            for offset in range(0,len(audio),1600):
                pointer=C.cast(C.byref(buffer,offset*4),Float)
                check(accept(stream,pointer,min(1600,len(audio)-offset),receive,None))
            check(finish(stream,receive,None));stream_s=time.monotonic()-start
        finally:free(stream)
        final=' '.join(e['text'] for e in events if e['endpoint'])
        baseline_wer,stream_wer=wer(reference,baseline),wer(reference,final)
        row={'fixture':wav.name,'fixture_sha256':hashlib.sha256(wav.read_bytes()).hexdigest(),
             'reference':reference,'audio_s':len(audio)/16000,'offline':baseline,'stream_final':final,
             'exact_final_match':baseline==final,'offline_wer':baseline_wer,'stream_wer':stream_wer,
             'offline_s':offline_s,'stream_s':stream_s,'stream_compute_rtf':stream_s/(len(audio)/16000),
             'events':events,'passed':stream_wer<=0.15 and stream_wer<=baseline_wer+0.03 and any(not e['endpoint'] for e in events)}
        rows.append(row);print(wav.name,'WER',stream_wer,'offline_equal',baseline==final,'pass',row['passed'],flush=True)
    report={'schema':1,'date':'2026-11-07','scope':'synthetic fixed voices; no natural human-speech or mobile certification',
            'gate':'normalized WER <= 15% and no more than 3 percentage points worse than matched offline; partial before final',
            'library_sha256':hashlib.sha256(a.library.read_bytes()).hexdigest(),
            'model_sha256':hashlib.sha256(a.model.read_bytes()).hexdigest(),'cases':rows}
    a.report.write_text(json.dumps(report,indent=2)+'\n')
    if not all(r['passed'] for r in rows):raise SystemExit(1)

if __name__=='__main__':main()
