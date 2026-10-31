package com.orient.ortts.demo;
import org.json.*;
import java.io.IOException;
import java.util.*;
/** Decoder choice belongs to the model pack; P3/P5 remains an independent choice. */
final class DecoderSelection {
 final String kind,variant,manifest;
 private DecoderSelection(String k,String v,String m){kind=k;variant=v;manifest=m;}
 static DecoderSelection from(JSONObject pack)throws Exception{
  if(!pack.has("runtime"))return new DecoderSelection("qwen_lfm","","");
  JSONObject runtime=pack.getJSONObject("runtime");
  if(!runtime.getString("schema").equals("ortts-runtime-v1"))throw new IOException("不支持的运行时清单");
  JSONObject decoder=runtime.getJSONObject("decoder");String kind=decoder.getString("kind");
  if(kind.equals("qwen_lfm"))return new DecoderSelection(kind,"","");
  if(!kind.equals("liquidcodec"))throw new IOException("不支持的解码器："+kind);
  String variant=decoder.getString("variant"),manifest=decoder.getString("manifest");
  if(!variant.equals("base")&&!variant.equals("expanded"))throw new IOException("不支持的 LiquidCodec 类型");
  if(!manifest.endsWith("/runtime.json")||manifest.startsWith("/")||manifest.contains("\\")||Arrays.asList(manifest.split("/")).contains("..")||Arrays.asList(manifest.split("/")).contains("."))throw new IOException("无效的解码器清单路径");
  return new DecoderSelection(kind,variant,manifest);
 }
 boolean liquid(){return kind.equals("liquidcodec");}
 String label(){return liquid()?"LiquidCodec":"Qwen–LFM";}
 void requireSelected(Map<String,JSONObject> all,Map<String,JSONObject> selected)throws Exception{
  if(!liquid())return;
  if(!all.containsKey(manifest)||!selected.containsKey(manifest))throw new IOException("模型缺少解码器清单");
  String prefix=manifest.substring(0,manifest.lastIndexOf('/')+1);int count=0;
  for(String path:all.keySet())if(path.startsWith(prefix)){count++;if(!selected.containsKey(path))throw new IOException("模型下载分组缺少解码器文件："+path);}
  if(count<2)throw new IOException("解码器权重不完整");
 }
 void requireSupported()throws java.io.IOException{if(liquid()&&!NativeBridge.supportsLiquidCodec())throw new IllegalStateException("此版本未包含 LiquidCodec，请使用支持该解码器的构建。");}
}
