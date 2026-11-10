package com.orient.ortts.demo;
import java.io.*;
import java.security.*;
import java.util.concurrent.atomic.AtomicBoolean;
/** Shared model/reference verifier; pure Java so integrity failures are host-testable. */
final class PinnedAsset {
 static boolean valid(File file,long bytes,String expected,AtomicBoolean cancelled)throws Exception {
  if(bytes<1||expected==null||!expected.matches("[0-9a-f]{64}"))throw new IOException("Invalid pinned asset identity");
  if(!file.isFile()||file.length()!=bytes)return false;
  MessageDigest hash=MessageDigest.getInstance("SHA-256");try(InputStream in=new FileInputStream(file)){
   byte[] b=new byte[262144];int n;while((n=in.read(b))!=-1){if(cancelled.get())throw new IOException("已停止");hash.update(b,0,n);}
  }
  StringBuilder out=new StringBuilder();for(byte b:hash.digest())out.append(String.format(java.util.Locale.ROOT,"%02x",b&255));return out.toString().equals(expected);
 }
}
