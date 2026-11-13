import copy
import importlib.util
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def module(name):
 s=importlib.util.spec_from_file_location(name,ROOT/'tools'/f'{name}.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
policy=module('asr_device_policy');score=module('evaluate_asr_acceptance')
class Acceptance(unittest.TestCase):
 def test_unknown_never_defaults(self):
  self.assertEqual(policy.select({'approved':[]},{'os':'ios'},'a'*64,'b'*64,'v1')['status'],'unverified')
 def test_identity_and_rejection_precedence(self):
  d={'os':'android','hardware':'test','os_build':'build','ram_mib':2048,'cpu':'A53'};e={'device':d,'runtime_sha256':'a'*64,'model_identity':'b'*64,'protocol':'v1','recipe_id':'lite'}
  self.assertEqual(policy.select({'approved':[e]},d,'a'*64,'b'*64,'v1')['status'],'recommended')
  self.assertEqual(policy.select({'approved':[e]},d,'c'*64,'b'*64,'v1')['status'],'unverified')
  self.assertEqual(policy.select({'approved':[e],'rejected':[e]},d,'a'*64,'b'*64,'v1')['status'],'not-recommended')
 def test_mixed_tokenization_and_errors(self):
  self.assertEqual(score.tokens('你好，Hello WORLD！'),['你','好','hello','world'])
  q=score.quality([{'human_verified':True,'source_kind':'human-recording','language':'mixed','reference':'今天是 Monday','hypothesis':'今天是 Sunday'}]);self.assertEqual(q['mixed_mer'],.25);self.assertEqual(q['mixed_english_wer'],1)
 def fixture(self):
  p=json.loads((ROOT/'runtime/models/asr-acceptance-policy.json').read_text());trials=[]
  for lang,ref in [('zh','今天很好'),('en','hello world'),('mixed','你好 hello')]:
   for i in range(20):trials.append({'language':lang,'reference':ref,'hypothesis':ref,'human_verified':True,'source_kind':'human-recording','input_sha256':f'{i:064x}','audio_s':10,'native_api_ms':5000,'final_latency_ms':300})
  r={'schema':'ortts-asr-device-report-v1','protocol':p['protocol'],'device':{'os':'android','physical':True,'hardware':'test','ram_mib':2048,'os_build':'test','cpu':'A53'},'runtime_sha256':'a'*64,'model_identity':'b'*64,'fixtures_sha256':'c'*64,'evidence':{'native_target':True,'assets_verified':True,'input_pacing':'realtime','rtf_numerator':'active-native-api-time-excluding-load-and-pacing','tts_asr_task_switch_tested':True,'stability_minutes':10},'trials':trials,'recipe_settings':{'threads':2,'chunk_encoder':32,'max_segment_ms':15000,'silence_ms':0},'cold_load_ms':[1000,1100,1200],'cancellation':{**{k:True for k in p['gates']['cancel_cases_required']},'latency_ms':[10,20]},'memory':{'metric':'peak-pss-sampled','peak_app_mib':600,'sampling_ms':50}}
  return r,p
 def test_pinned_assets_match_native_loader(self):
  import re,hashlib
  r=json.loads((ROOT/'runtime/models/asr-recipes.json').read_text())['profiles'][0]
  h=(ROOT/'runtime/src/zipformer_assets.h').read_text()
  actual=[(p,int(n),sha) for p,n,sha in re.findall(r'\{"([^"]+)",(\d+),"([a-f0-9]{64})"\}',h)]
  self.assertEqual(actual,[(a['path'],a['bytes'],a['sha256']) for a in r['model']['assets']])
  identity=hashlib.sha256(json.dumps({k:r[k] for k in ['id','executor','model','capabilities','settings']},sort_keys=True,separators=(',',':')).encode()).hexdigest()
  self.assertEqual(identity,r['identity_sha256'])
 def test_gate_boundary_and_missing_evidence(self):
  r,p=self.fixture();self.assertEqual(score.evaluate(r,p)['status'],'accepted')
  r['trials'][0]['native_api_ms']=float('nan');self.assertEqual(score.evaluate(r,p)['status'],'not-recommended')
  r,p=self.fixture()
  for t in r['trials']:t['native_api_ms']=t['audio_s']*1000
  self.assertEqual(score.evaluate(r,p)['status'],'not-recommended')
  r,p=self.fixture();r['cold_load_ms']=None;self.assertEqual(score.evaluate(r,p)['status'],'not-recommended')
  r,p=self.fixture();r['device']['physical']=False;self.assertEqual(score.evaluate(r,p)['status'],'not-recommended')
  r,p=self.fixture();r['memory']['peak_app_mib']=701;self.assertEqual(score.evaluate(r,p)['status'],'not-recommended')
  r,p=self.fixture();r['trials']*=3
  for t in r['trials']:t['source_kind']='synthesized'
  self.assertEqual(score.evaluate(r,p)['status'],'not-recommended')
if __name__=='__main__':unittest.main()
