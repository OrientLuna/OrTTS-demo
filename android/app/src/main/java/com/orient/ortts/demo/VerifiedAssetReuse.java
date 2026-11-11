package com.orient.ortts.demo;

import org.json.*;
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Reuses identical bytes, never trusts filenames or changes an installed source. */
final class VerifiedAssetReuse {
 private final Map<String,List<File>> candidates=new HashMap<>();
 private static String key(JSONObject e)throws Exception{return e.getLong("bytes")+":"+e.getString("sha256");}
 VerifiedAssetReuse(List<File> roots){int count=0;for(File root:roots){if(++count>64)break;try{
  File metadata=new File(root,"model.json");if(!metadata.isFile()||metadata.length()>2*1024*1024)continue;
  JSONArray entries=new JSONObject(new String(Files.readAllBytes(metadata.toPath()),"UTF-8")).getJSONArray("files");if(entries.length()>256)continue;
  for(int i=0;i<entries.length();i++){JSONObject e=entries.getJSONObject(i);File f=new File(root,e.getString("path")).getCanonicalFile();if(!f.toPath().startsWith(root.getCanonicalFile().toPath())||f.equals(root.getCanonicalFile())||!e.getString("sha256").matches("[a-f0-9]{64}"))continue;candidates.computeIfAbsent(key(e),k->new ArrayList<>()).add(f);}
 }catch(Exception ignored){/* Invalid or incomplete old packages cannot supply assets. */}}}
 static String sha(File file)throws Exception{MessageDigest digest=MessageDigest.getInstance("SHA-256");try(InputStream in=new BufferedInputStream(new FileInputStream(file))){byte[] b=new byte[1<<20];int n;while((n=in.read(b))!=-1)digest.update(b,0,n);}StringBuilder s=new StringBuilder();for(byte v:digest.digest())s.append(String.format(Locale.ROOT,"%02x",v&255));return s.toString();}
 boolean materialize(JSONObject entry,File target)throws Exception{
  List<File> sources=candidates.get(key(entry));if(sources==null)return false;
  for(File source:sources){boolean valid;try{valid=source.isFile()&&source.length()==entry.getLong("bytes")&&sha(source).equals(entry.getString("sha256"));}catch(Exception e){continue;}if(!valid)continue;
   target.getParentFile().mkdirs();File temp=new File(target.getParentFile(),".reuse-"+UUID.randomUUID());
   try{Files.copy(source.toPath(),temp.toPath());if(!sha(temp).equals(entry.getString("sha256")))throw new IOException("本地复用文件校验失败");Files.move(temp.toPath(),target.toPath(),StandardCopyOption.REPLACE_EXISTING);return true;}finally{Files.deleteIfExists(temp.toPath());}
  }return false;
 }
}
