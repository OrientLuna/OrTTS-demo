#!/usr/bin/env python3
"""Read tensor metadata without mmap, loading weights, or allocating tokenizer arrays."""
import argparse,collections,json,math,struct
from pathlib import Path

def inspect(path):
 with Path(path).open('rb') as f:
  def unpack(fmt):
   n=struct.calcsize('<'+fmt);b=f.read(n)
   if len(b)!=n:raise ValueError('Truncated GGUF')
   return struct.unpack('<'+fmt,b)[0]
  def string():
   n=unpack('Q')
   if n>16*1024*1024:raise ValueError('Oversized metadata string')
   return f.read(n).decode('utf-8')
  sizes={0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}
  def skip(t):
   if t in sizes:f.seek(sizes[t],1)
   elif t==8:f.seek(unpack('Q'),1)
   elif t==9:
    inner=unpack('I');n=unpack('Q')
    if inner in sizes:f.seek(n*sizes[inner],1)
    else:
     for _ in range(n):skip(inner)
   else:raise ValueError('Unknown metadata type')
  if f.read(4)!=b'GGUF' or unpack('I')!=3:raise ValueError('Expected GGUFv3')
  tensors=unpack('Q');metadata=unpack('Q')
  for _ in range(metadata):string();skip(unpack('I'))
  hist=collections.defaultdict(lambda:{'tensors':0,'elements':0});selected=[]
  for _ in range(tensors):
   name=string();rank=unpack('I');shape=[unpack('Q') for _ in range(rank)];kind=unpack('I');offset=unpack('Q');hist[kind]['tensors']+=1;hist[kind]['elements']+=math.prod(shape)
   if any(v in name for v in ['text_embedding','text_embd','token_embd','embed_tokens']):selected.append({'name':name,'shape':shape,'ggml_type':kind})
 return {'file':str(path),'bytes':Path(path).stat().st_size,'types':hist,'embedding_tensors':selected,'type_key':{'0':'F32','1':'F16','2':'Q4_0','8':'Q8_0'}}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('files',nargs='+');a=p.parse_args();print(json.dumps([inspect(f) for f in a.files],indent=2))
