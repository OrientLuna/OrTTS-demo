package com.orient.ortts.demo;
import java.net.*;
import java.io.IOException;
import java.util.*;

/** Transport selection only. Callers must verify the same expected bytes/SHA. */
final class DownloadRoute {
 static String channel(String address){try{String h=new URI(address).getHost();if("huggingface.co".equals(h))return "hf";if("hf-mirror.com".equals(h))return "hfmirror";if("modelscope.cn".equals(h)||"www.modelscope.cn".equals(h))return "modelscope";}catch(Exception ignored){}return "custom";}
 static List<String> candidates(String primary,List<String> alternatives,String mode,String last)throws IOException{
  LinkedHashSet<String> urls=new LinkedHashSet<>();urls.add(primary);urls.addAll(alternatives);
  for(String u:new ArrayList<>(urls))try{URI uri=new URI(u);if(uri.getUserInfo()!=null||uri.getHost()==null||!("https".equals(uri.getScheme())||("custom".equals(channel(u))&&"http".equals(uri.getScheme()))))throw new Exception();}catch(Exception e){throw new IOException("下载地址无效");}
  if("hf".equals(channel(primary)))urls.add(primary.replaceFirst("https://huggingface\\.co/","https://hf-mirror.com/"));
  if("hfmirror".equals(channel(primary)))urls.add(primary.replaceFirst("https://hf-mirror\\.com/","https://huggingface.co/"));
  List<String> result=new ArrayList<>();String[] order="auto".equals(mode)?new String[]{last,"modelscope","hfmirror","hf","custom"}:new String[]{mode};
  for(String c:order)for(String u:urls)if(channel(u).equals(c)&&!result.contains(u))result.add(u);
  if(result.isEmpty())throw new IOException("该模型没有所选下载通道，请选择自动或其他通道");return result;
 }
}
