#!/usr/bin/env python3
"""Score human-reference zh/en/code-switch trials and evaluate a physical-device report.
Never writes the production whitelist; missing evidence fails closed.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
ROOT=Path(__file__).resolve().parents[1]

def han(c):
    return '\u3400'<=c<='\u9fff' or '\U00020000'<=c<='\U0002fa1f'

def tokens(text):
    text=unicodedata.normalize('NFKC',text).casefold().replace('’',"'")
    out=[];word=''
    for i,c in enumerate(text):
        if c.isascii() and c.isalnum():word+=c
        elif c=="'" and word and i+1<len(text) and text[i+1].isascii() and text[i+1].isalpha():word+=c
        else:
            if word:out.append(word);word=''
            if han(c) or unicodedata.category(c)[0] in ('L','M','N'):out.append(c)
    if word:out.append(word)
    return out

def edits(ref,hyp):
    row=list(range(len(hyp)+1))
    for i,a in enumerate(ref,1):
        new=[i]
        for j,b in enumerate(hyp,1):new.append(min(new[-1]+1,row[j]+1,row[j-1]+(a!=b)))
        row=new
    return row[-1]

def quality(trials):
    totals={k:[0,0] for k in ['zh_cer','en_wer','mixed_mer','mixed_english_wer']}
    for t in trials:
        if not t.get('human_verified') or t.get('source_kind')!='human-recording' or not isinstance(t.get('reference'),str):continue
        ref=tokens(t['reference']);hyp=tokens(t.get('hypothesis') if isinstance(t.get('hypothesis'),str) else '');language=t.get('language')
        if language=='zh':pairs=[('zh_cer',list(''.join(ref)),list(''.join(hyp)))]
        elif language=='en':pairs=[('en_wer',ref,hyp)]
        elif language=='mixed':pairs=[('mixed_mer',ref,hyp),('mixed_english_wer',[x for x in ref if not all(han(c) for c in x)],[x for x in hyp if not all(han(c) for c in x)])]
        else:continue
        for key,a,b in pairs:totals[key][0]+=edits(a,b);totals[key][1]+=len(a)
    return {k:(e/n if n else None) for k,(e,n) in totals.items()}

def percentile95(values):
    if not isinstance(values,list) or not values or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) or x<0 for x in values):return None
    return sorted(values)[math.ceil(len(values)*.95)-1]

def evaluate(report,policy):
    errors=[];g=policy['gates'];device=report.get('device',{});trials=report.get('trials',[])
    if not isinstance(device,dict) or not isinstance(trials,list) or any(not isinstance(t,dict) for t in trials):return {'status':'not-recommended','reasons':['invalid device/trial report shape'],'metrics':{},'whitelist_write':False}
    def need(ok,why):
        if not ok:errors.append(why)
    need(report.get('schema')=='ortts-asr-device-report-v1','missing report schema')
    need(report.get('protocol')==policy['protocol'],'protocol mismatch')
    need(device.get('physical') is True and device.get('os') in ('android','ios'),'physical Android/iOS evidence required')
    need(all(isinstance(device.get(k),str) and device[k].strip() for k in ['hardware','os_build','cpu']) and type(device.get('ram_mib')) is int and device['ram_mib']>0,'missing exact device identity')
    for key in ['runtime_sha256','model_identity','fixtures_sha256']:
        need(isinstance(report.get(key),str) and bool(re.fullmatch('[a-f0-9]{64}',report[key])),f'missing {key}')
    evidence=report.get('evidence',{})
    need(report.get('recipe_settings')=={'threads':2,'chunk_encoder':32,'max_segment_ms':15000,'silence_ms':0},'recipe settings mismatch')
    need(evidence.get('native_target') is True and evidence.get('assets_verified') is True,'native execution and asset SHA verification required')
    need(evidence.get('input_pacing')=='realtime' and evidence.get('rtf_numerator')=='active-native-api-time-excluding-load-and-pacing','RTF timing/pacing mismatch')
    need(evidence.get('tts_asr_task_switch_tested') is True,'low-memory task switching not tested')
    need(evidence.get('stability_minutes',0)>=g['stability_minutes_min'],'insufficient stability run')
    for language in policy['languages']:
        group=[t for t in trials if t.get('language')==language and t.get('human_verified') is True and t.get('source_kind')=='human-recording' and t.get('reference')]
        hashes={t.get('input_sha256') for t in group if re.fullmatch('[a-f0-9]{64}',t.get('input_sha256',''))}
        if language=='mixed':need(all(any(han(c) for c in t['reference']) and any(c.isascii() and c.isalpha() for c in t['reference']) for t in group),'mixed references must contain Chinese and English')
        need(len(hashes)>=policy['minimum_human_reference_samples_per_language'],f'insufficient unique human references for {language}')
    scores=quality(trials)
    for key,value in scores.items():need(value is not None and value<=g[key+'_max'],f'{key} missing or above threshold')
    def bound(name,values,limit,strict=False):
        value=percentile95(values);need(value is not None and (value<limit if strict else value<=limit),name+' missing or above threshold');return value
    rtf=[];latency=[]
    for t in trials:
        need(t.get('human_verified') is True and t.get('source_kind')=='human-recording' and isinstance(t.get('reference'),str) and bool(t['reference']) and isinstance(t.get('hypothesis'),str),'unreviewed/synthetic trial cannot enter physical acceptance')
        duration=t.get('audio_s');ms=t.get('native_api_ms')
        if type(duration) in (int,float) and math.isfinite(duration) and duration>0 and type(ms) in (int,float) and math.isfinite(ms) and ms>=0:rtf.append(ms/1000/duration)
        else:errors.append('invalid trial duration or compute time')
        latency.append(t.get('final_latency_ms'))
    metrics={'quality':scores,'warm_rtf_p95':bound('warm RTF',rtf,g['warm_rtf_p95_exclusive_max'],True),'final_latency_ms_p95':bound('final latency',latency,g['final_latency_ms_p95_max'])}
    cold=report.get('cold_load_ms',[]);need(isinstance(cold,list) and len(cold)>=3,'at least three fresh-process cold loads required');metrics['cold_load_ms_p95']=bound('cold load',cold,g['cold_load_ms_p95_max'])
    cancel=report.get('cancellation',{});need(all(cancel.get(k) is True for k in g['cancel_cases_required']),'missing cancellation/recovery cases');metrics['cancel_ms_p95']=bound('cancel latency',cancel.get('latency_ms',[]),g['cancel_ms_p95_max'])
    memory=report.get('memory',{});need(memory.get('metric')==('peak-pss-sampled' if device.get('os')=='android' else 'peak-phys-footprint-sampled'),'wrong memory metric')
    ram=device.get('ram_mib',0);limits=g['peak_app_memory_mib_max_by_ram'];limit=next((limits[k] for k in sorted(limits,key=int) if isinstance(ram,(int,float)) and ram<=int(k)),limits['4096'])
    peak=memory.get('peak_app_mib');need(type(peak) in (int,float) and math.isfinite(peak) and peak>0 and peak<=limit,'memory missing or above budget')
    interval=memory.get('sampling_ms');need(type(interval) in (int,float) and math.isfinite(interval) and 0<interval<=50,'memory sampling interval missing/too slow')
    metrics['peak_app_mib']=peak
    return {'status':'accepted' if not errors else 'not-recommended','reasons':errors,'metrics':metrics,'whitelist_write':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True,type=Path);p.add_argument('--policy',type=Path,default=ROOT/'runtime/models/asr-acceptance-policy.json');p.add_argument('--out',type=Path);a=p.parse_args()
    r=evaluate(json.loads(a.report.read_text()),json.loads(a.policy.read_text()));text=json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if a.out:a.out.write_text(text)
    print(text,end='');raise SystemExit(0 if r['status']=='accepted' else 2)
if __name__=='__main__':main()
