package com.orient.ortts.demo;
import java.util.*;
public class DownloadRouteTest {
 public static void main(String[] args)throws Exception{
  String hf="https://huggingface.co/a/b/resolve/pinned/model.gguf",ms="https://modelscope.cn/models/x/y/resolve/pinned/model.gguf",mirror=hf.replace("huggingface.co","hf-mirror.com");
  check(DownloadRoute.candidates(hf,Arrays.asList(ms),"auto","").equals(Arrays.asList(ms,mirror,hf)));
  check(DownloadRoute.candidates(hf,Arrays.asList(ms),"auto","hf").equals(Arrays.asList(hf,ms,mirror)));
  check(DownloadRoute.candidates(hf,Arrays.asList(ms),"hfmirror","").equals(Arrays.asList(mirror)));
  check(DownloadRoute.candidates(ms,Collections.emptyList(),"auto","hf").equals(Arrays.asList(ms)));
  check(DownloadRoute.candidates("http://127.0.0.1/file",Collections.emptyList(),"auto","").size()==1);
  reject(ms,"hf");reject("https://user:secret@huggingface.co/a/b","auto");reject("http://huggingface.co/a/b","auto");reject("file:///tmp/model","auto");
  check(DownloadRoute.channel("https://evil-huggingface.co/a").equals("custom"));System.out.println("DOWNLOAD_ROUTE_10_PASS");
 }
 static void check(boolean x){if(!x)throw new AssertionError();}
 static void reject(String url,String mode)throws Exception{try{DownloadRoute.candidates(url,Collections.emptyList(),mode,"");throw new AssertionError();}catch(java.io.IOException expected){}}
}
