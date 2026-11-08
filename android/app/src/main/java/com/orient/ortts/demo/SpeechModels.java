package com.orient.ortts.demo;

import android.content.Context;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.zip.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Pinned application catalog; no remote manifest or implicit model download. */
final class SpeechModels {
 interface Progress {void update(String message);}
 private File preparedG2p;final JSONArray models;final File root;private final Progress progress;
 final AtomicBoolean cancelled=new AtomicBoolean();private volatile HttpURLConnection connection;
 SpeechModels(Context context,Progress progress)throws Exception {
  this.progress=progress;root=new File(context.getFilesDir(),"speech-models");
  try(InputStream in=context.getAssets().open("SpeechModels.json")){
   ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] data=new byte[8192];int count;while((count=in.read(data))!=-1)bytes.write(data,0,count);
   JSONObject doc=new JSONObject(new String(bytes.toByteArray(),java.nio.charset.StandardCharsets.UTF_8));
   if(!"ortts-speech-catalog-v1".equals(doc.getString("schema")))throw new IOException("模型目录版本不支持");models=doc.getJSONArray("models");
  }
 }
 File child(String path)throws IOException {
  if(path.startsWith("/")||path.contains("\\"))throw new IOException("模型路径无效");
  File file=new File(root,path);String parent=root.getCanonicalPath()+File.separator;
  if(!file.getCanonicalPath().startsWith(parent)||path.contains("../"))throw new IOException("模型路径越界");return file;
 }
 private boolean valid(File file,JSONObject asset)throws Exception {
  if(!file.isFile()||file.length()!=asset.getLong("bytes"))return false;
  MessageDigest hash=MessageDigest.getInstance("SHA-256");try(InputStream in=new FileInputStream(file)){
   byte[] b=new byte[262144];int n;while((n=in.read(b))!=-1){if(cancelled.get())throw new IOException("已停止");hash.update(b,0,n);}
  }
  StringBuilder value=new StringBuilder();for(byte b:hash.digest())value.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
  return value.toString().equals(asset.getString("sha256"));
 }
 void cancel(){cancelled.set(true);HttpURLConnection c=connection;if(c!=null)c.disconnect();}
 void prepare(){cancelled.set(false);}
 String identity(JSONObject model)throws Exception {
  StringBuilder key=new StringBuilder(model.getString("id"));JSONArray assets=model.getJSONArray("assets");
  for(int i=0;i<assets.length();i++){JSONObject asset=assets.getJSONObject(i);File file=child(asset.getString("path"));java.nio.file.attribute.BasicFileAttributes attrs=Files.readAttributes(file.toPath(),java.nio.file.attribute.BasicFileAttributes.class);key.append('|').append(asset.getString("sha256")).append(':').append(attrs.size()).append(':').append(attrs.lastModifiedTime()).append(':').append(attrs.fileKey());}
  return key.toString();
 }
 File requireReady(JSONObject model)throws Exception {
  JSONArray assets=model.getJSONArray("assets");for(int i=0;i<assets.length();i++){
   JSONObject a=assets.getJSONObject(i);if(!valid(child(a.getString("path")),a))throw new IOException("请先下载 / 检查所选模型");
  }return child(model.getString("model_path"));
 }
 void download(JSONObject model)throws Exception {
  JSONArray assets=model.getJSONArray("assets");long total=0,done=0;
  for(int i=0;i<assets.length();i++)total+=assets.getJSONObject(i).getLong("bytes");
  for(int i=0;i<assets.length();i++){
   JSONObject a=assets.getJSONObject(i);File target=child(a.getString("path"));
   if(cancelled.get())throw new IOException("已停止");
   progress.update("检查 "+target.getName());if(valid(target,a)){done+=a.getLong("bytes");continue;}
   if(!target.getParentFile().isDirectory()&&!target.getParentFile().mkdirs())throw new IOException("无法建立模型目录");
   File partial=File.createTempFile("ortts-",".part",target.getParentFile());
   try {
    URL url=new URL(a.getString("url"));if(!"https".equals(url.getProtocol()))throw new IOException("模型下载需要HTTPS");
    HttpURLConnection c=(HttpURLConnection)url.openConnection();connection=c;c.setConnectTimeout(20000);c.setReadTimeout(30000);c.setInstanceFollowRedirects(true);
    long count=0,last=0;int code=c.getResponseCode();if(code!=200)throw new IOException("模型下载 HTTP "+code);
    try(InputStream in=c.getInputStream();OutputStream out=new FileOutputStream(partial)){
     byte[] b=new byte[262144];int n;while((n=in.read(b))!=-1){
      if(cancelled.get())throw new IOException("已停止");count+=n;if(count>a.getLong("bytes"))throw new IOException("模型下载超过预期大小");out.write(b,0,n);
      long now=System.currentTimeMillis();if(now-last>250){progress.update(String.format(java.util.Locale.ROOT,"下载 %.1f / %.1f MB",(done+count)/1e6,total/1e6));last=now;}
     }
    }finally{c.disconnect();connection=null;}
    progress.update("校验 SHA256 · "+target.getName());if(!valid(partial,a))throw new IOException("模型大小或SHA256不匹配，未安装");
    Files.move(partial.toPath(),target.toPath(),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);done+=a.getLong("bytes");
   }finally{partial.delete();connection=null;}
  }
  requireReady(model);progress.update("模型已就绪，文件大小与SHA256均通过");
 }
 void importZip(InputStream source,JSONObject model)throws Exception {
  if(!root.isDirectory())root.mkdirs();File stage=new File(root,"import-"+UUID.randomUUID());if(!stage.mkdir())throw new IOException("无法创建导入目录");
  Map<String,JSONObject> expected=new HashMap<>();JSONArray assets=model.getJSONArray("assets");for(int i=0;i<assets.length();i++){JSONObject a=assets.getJSONObject(i);child(a.getString("path"));expected.put(a.getString("path"),a);}
  try {
   Set<String>seen=new HashSet<>();int entryCount=0;try(ZipInputStream zip=new ZipInputStream(source)){ZipEntry entry;while((entry=zip.getNextEntry())!=null){
    String path=entry.getName();if(path.startsWith("speech-models/"))path=path.substring(14);if(++entryCount>expected.size()+64)throw new IOException("ZIP entries exceed limit");if(entry.isDirectory()){if(entry.getSize()!=0)throw new IOException("Directory entry has data");continue;}
    JSONObject asset=expected.get(path);if(asset==null||!seen.add(path))throw new IOException("ZIP应仅包含所选模型，保留目录且不重复文件");
    File output=new File(stage,path);output.getParentFile().mkdirs();long total=0;
    try(OutputStream out=new FileOutputStream(output)){byte[] buffer=new byte[131072];int n;while((n=zip.read(buffer))!=-1){if(cancelled.get())throw new IOException("已停止");total+=n;if(total>asset.getLong("bytes"))throw new IOException("ZIP文件大小超过模型清单");out.write(buffer,0,n);}}
    if(!valid(output,asset))throw new IOException("导入文件大小或SHA256不匹配");progress.update("已校验 "+output.getName());
   }}
   for(Map.Entry<String,JSONObject> entry:expected.entrySet())if(!valid(new File(stage,entry.getKey()),entry.getValue())&&!valid(child(entry.getKey()),entry.getValue()))throw new IOException("ZIP缺少模型文件："+entry.getKey());
   for(String path:seen){File target=child(path);target.getParentFile().mkdirs();Files.move(new File(stage,path).toPath(),target.toPath(),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}
   requireReady(model);progress.update("模型导入完成，大小及SHA256均通过");
  }finally{removeStage(stage);}
 }
 File prepareG2p(Context context)throws IOException {
  if(preparedG2p!=null&&new File(preparedG2p,"phontab").isFile())return preparedG2p;File target=new File(context.getFilesDir(),"espeak-ng-data");copyData(context,"espeak-ng-data",target);preparedG2p=target;return target;
 }
 private void copyData(Context context,String path,File target)throws IOException {
  if(cancelled.get())throw new IOException("Cancelled");String[] entries=context.getAssets().list(path);
  if(entries!=null&&entries.length>0){if(!target.isDirectory()&&!target.mkdirs())throw new IOException("Cannot create G2P directory");for(String name:entries)copyData(context,path+"/"+name,new File(target,name));}
  else{try(InputStream in=context.getAssets().open(path)){if(target.isFile())return;File partial=File.createTempFile("g2p-",".part",target.getParentFile());try{try(OutputStream out=new FileOutputStream(partial)){byte[] bytes=new byte[65536];int n;while((n=in.read(bytes))!=-1){if(cancelled.get())throw new IOException("Cancelled");out.write(bytes,0,n);}}Files.move(partial.toPath(),target.toPath(),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}finally{partial.delete();}}}
 }
 private void removeStage(File file){File[] children=file.listFiles();if(children!=null)for(File child:children)removeStage(child);file.delete();}
}
