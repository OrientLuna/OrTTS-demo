package com.orient.ortts.demo;
import android.content.*;
import android.net.Uri;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import java.util.zip.*;
final class ModelManager {
 interface Progress { void update(String s); }
 private final Context context;private final Progress progress;
 ModelManager(Context c,Progress p){context=c;progress=p;}
 static String sha(File f)throws Exception{MessageDigest d=MessageDigest.getInstance("SHA-256");try(InputStream in=new BufferedInputStream(new FileInputStream(f))){byte[] b=new byte[1<<20];int n;while((n=in.read(b))!=-1)d.update(b,0,n);}StringBuilder s=new StringBuilder();for(byte v:d.digest())s.append(String.format("%02x",v&255));return s.toString();}
 static File child(File root,String path)throws Exception{if(path.isEmpty()||path.startsWith("/")||path.contains("\\")||Arrays.asList(path.split("/")).contains(".."))throw new IOException("无效模型路径");File p=new File(root,path).getCanonicalFile();if(!p.toPath().startsWith(root.getCanonicalFile().toPath())||p.equals(root.getCanonicalFile()))throw new IOException("模型路径越界");return p;}
 File current(){String p=context.getSharedPreferences("models",0).getString("current",null);return p==null?null:new File(p);}
 private File staging()throws IOException{File p=new File(context.getFilesDir(),"models/.staging-"+UUID.randomUUID());if(!p.mkdirs())throw new IOException("无法准备模型目录");return p;}
 private static void discard(File p)throws IOException{if(!p.exists())return;try(java.util.stream.Stream<Path>w=Files.walk(p.toPath())){for(Path x:(Iterable<Path>)w.sorted(Comparator.reverseOrder())::iterator)Files.deleteIfExists(x);}}
 static JSONObject manifest(File dir)throws Exception{File f=new File(dir,"model.json");if(!f.isFile()||f.length()>2*1024*1024)throw new IOException("缺少模型清单");return new JSONObject(new String(Files.readAllBytes(f.toPath()),StandardCharsets.UTF_8));}
 private LinkedHashMap<String,JSONObject> entries(JSONObject m)throws Exception{if(!m.getString("schema").equals("ortts-download-manifest-v1"))throw new IOException("不支持的模型清单");JSONArray a=m.getJSONArray("files");if(a.length()<1||a.length()>256)throw new IOException("模型文件数量异常");LinkedHashMap<String,JSONObject> out=new LinkedHashMap<>();long total=0;for(int i=0;i<a.length();i++){JSONObject v=a.getJSONObject(i);String path=v.getString("path"),hash=v.getString("sha256");if(!hash.matches("[a-f0-9]{64}")||v.getLong("bytes")<0||out.put(path,v)!=null)throw new IOException("无效或重复模型文件");child(context.getFilesDir(),path);total+=v.getLong("bytes");}if(total>8L*1024*1024*1024)throw new IOException("模型包过大");return out;}
 private static final String[] CORE={"native/model.gguf","native/bridge/MANIFEST.json","native/tokenizer-b260k-MIXED_Q4_0.gguf","native/tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf","native/vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf","voices/female.f32","voices/male.f32"};
 private static final String[] P3={"P3/predictor/predictor.safetensors","P3/predictor/config.json","P3/predictor/talker_config.json"};
 boolean ready(String variant){try{File dir=current();if(dir==null)return false;Map<String,JSONObject> files=entries(manifest(dir));for(String path:CORE){JSONObject v=files.get(path);File f=child(dir,path);if(v==null||!f.isFile()||f.length()!=v.getLong("bytes"))return false;}if(variant.equals("P3"))for(String path:P3){JSONObject v=files.get(path);File f=child(dir,path);if(v==null||!f.isFile()||f.length()!=v.getLong("bytes"))return false;}return variant.equals("P3")||variant.equals("P5");}catch(Exception e){return false;}}
 private LinkedHashMap<String,JSONObject> selected(JSONObject m,String variant)throws Exception{LinkedHashMap<String,JSONObject> all=entries(m);JSONObject rules=m.getJSONObject("selection_rules");Map<String,List<String>> patterns=new LinkedHashMap<>();for(String key:new String[]{"common","P3","P5"}){JSONArray a=rules.getJSONArray(key);List<String> list=new ArrayList<>();for(int i=0;i<a.length();i++)list.add(a.getString(i));patterns.put(key,list);}LinkedHashMap<String,JSONObject> out=new LinkedHashMap<>();for(String path:DownloadSelection.select(all.keySet(),patterns,variant))out.put(path,all.get(path));return out;}
 private static JSONArray fileArray(Map<String,JSONObject> files){JSONArray a=new JSONArray();for(JSONObject v:files.values())a.put(v);return a;}
 private void requireCore(Map<String,JSONObject> files)throws Exception{for(String path:CORE)if(!files.containsKey(path))throw new IOException("模型缺少必需文件："+path);boolean any=false;for(String path:P3)any|=files.containsKey(path);if(any)for(String path:P3)if(!files.containsKey(path))throw new IOException("P3预测器不完整");}
 private File activate(File dir,JSONObject m)throws Exception{
  LinkedHashMap<String,JSONObject> files=entries(m);int i=0;for(Map.Entry<String,JSONObject> e:files.entrySet()){progress.update("校验模型 "+(++i)+"/"+files.size());File f=child(dir,e.getKey());JSONObject v=e.getValue();if(!f.isFile()||f.length()!=v.getLong("bytes")||!sha(f).equals(v.getString("sha256")))throw new IOException("文件校验失败："+e.getKey());}
  requireCore(files);
  File dest=new File(dir.getParentFile(),"release-"+UUID.randomUUID());if(!dir.renameTo(dest))throw new IOException("模型安装失败");context.getSharedPreferences("models",0).edit().putString("current",dest.getAbsolutePath()).apply();return dest;
 }
 File importUri(Uri uri)throws Exception{File zip=new File(context.getCacheDir(),"import-"+UUID.randomUUID()+".zip");try(InputStream in=context.getContentResolver().openInputStream(uri);OutputStream out=new BufferedOutputStream(new FileOutputStream(zip))){if(in==null)throw new IOException("无法打开文件");copy(in,out,6L*1024*1024*1024,null);}try{return importZip(zip);}finally{zip.delete();}}
 File importZip(File zip)throws Exception{File dir=staging();try(ZipFile z=new ZipFile(zip)){
  ZipEntry meta=z.getEntry("model.json");if(meta==null||meta.getSize()>2*1024*1024)throw new IOException("ZIP内缺少model.json");JSONObject m=new JSONObject(new String(readLimited(z.getInputStream(meta),2*1024*1024),StandardCharsets.UTF_8));LinkedHashMap<String,JSONObject> expected=entries(m);HashSet<String> seen=new HashSet<>();Enumeration<? extends ZipEntry> all=z.entries();long total=0;
  while(all.hasMoreElements()){ZipEntry e=all.nextElement();if(e.isDirectory())continue;String name=e.getName();File f=child(dir,name);if(!seen.add(name)||(!name.equals("model.json")&&!expected.containsKey(name)))throw new IOException("ZIP包含未登记文件");long limit=name.equals("model.json")?2*1024*1024:expected.get(name).getLong("bytes");f.getParentFile().mkdirs();progress.update("正在解包模型文件");try(InputStream in=z.getInputStream(e);OutputStream out=new BufferedOutputStream(new FileOutputStream(f))){total+=copy(in,out,limit,name);}if(total>8L*1024*1024*1024)throw new IOException("解包内容过大");}
  return activate(dir,m);
 }catch(Exception e){discard(dir);throw e;}}
 boolean hasBundled(){try(InputStream in=context.getAssets().open("bundled/model.json")){return true;}catch(IOException ignored){}try(InputStream in=context.getAssets().open("model.zip")){return true;}catch(IOException ignored){return false;}}
 File importBundled()throws Exception{
  byte[] metadata=null;try{metadata=readLimited(context.getAssets().open("bundled/model.json"),2*1024*1024);}catch(FileNotFoundException absent){}
  if(metadata!=null){JSONObject m=new JSONObject(new String(metadata,StandardCharsets.UTF_8));File dir=staging();try{for(Map.Entry<String,JSONObject> e:entries(m).entrySet()){File f=child(dir,e.getKey());f.getParentFile().mkdirs();progress.update("正在准备内置模型");try(InputStream in=context.getAssets().open("bundled/"+e.getKey());OutputStream out=new BufferedOutputStream(new FileOutputStream(f))){copy(in,out,e.getValue().getLong("bytes"),e.getKey());}}Files.write(new File(dir,"model.json").toPath(),metadata);return activate(dir,m);}catch(Exception e){discard(dir);throw e;}}
  return importBundledZip();
 }
 private File importBundledZip()throws Exception{File zip=new File(context.getCacheDir(),"bundled-model.zip");try(InputStream in=context.getAssets().open("model.zip");OutputStream out=new BufferedOutputStream(new FileOutputStream(zip))){copy(in,out,6L*1024*1024*1024,null);}try{return importZip(zip);}finally{zip.delete();}}
 File download(String manifestUrl)throws Exception{return download(manifestUrl,"P3");}
 File download(String manifestUrl,String variant)throws Exception{
  progress.update("获取模型清单");byte[] bytes=readLimited(open(manifestUrl),2*1024*1024);JSONObject m=new JSONObject(new String(bytes,StandardCharsets.UTF_8));LinkedHashMap<String,JSONObject> files=selected(m,variant);requireCore(files);File old=current();JSONObject oldMeta=null;
  if(old!=null)try{oldMeta=manifest(old);if(!oldMeta.getString("model_id").equals(m.getString("model_id"))||!oldMeta.getString("revision").equals(m.getString("revision"))){old=null;oldMeta=null;}}catch(Exception ignored){old=null;oldMeta=null;}
  File dir=staging();try{String base=m.getString("base_url");List<String> staged=new ArrayList<>();long total=0;for(JSONObject v:files.values())total+=v.getLong("bytes");long reused=0;int position=0;
   for(Map.Entry<String,JSONObject> e:files.entrySet()){position++;progress.update("准备模型 "+position+"/"+files.size());JSONObject v=e.getValue();File have=old==null?null:child(old,e.getKey());if(have!=null&&have.isFile()&&have.length()==v.getLong("bytes")&&sha(have).equals(v.getString("sha256"))){reused+=have.length();continue;}File f=child(dir,e.getKey());f.getParentFile().mkdirs();downloadFile(v.optString("url",base+e.getKey()),f,v.getLong("bytes"),v.getString("sha256"),"下载模型 "+position+"/"+files.size());staged.add(e.getKey());}
   m.put("files",fileArray(files));m.put("last_download",new JSONObject().put("variant",variant).put("selected_bytes",total).put("reused_bytes",reused).put("downloaded_bytes",total-reused));
   if(old==null){Files.write(new File(dir,"model.json").toPath(),m.toString().getBytes(StandardCharsets.UTF_8));return activate(dir,m);}
   // Same revision: add verified missing components to the existing shared root.
   LinkedHashMap<String,JSONObject> installed=entries(oldMeta);installed.putAll(files);requireCore(installed);
   for(String path:staged){File target=child(old,path);target.getParentFile().mkdirs();Files.move(child(dir,path).toPath(),target.toPath(),StandardCopyOption.REPLACE_EXISTING);}
   m.put("files",fileArray(installed));File temp=new File(old,"model.json.tmp");Files.write(temp.toPath(),m.toString().getBytes(StandardCharsets.UTF_8));Files.move(temp.toPath(),new File(old,"model.json").toPath(),StandardCopyOption.REPLACE_EXISTING);discard(dir);return old;
  }catch(Exception e){discard(dir);throw e;}
 }

 void downloadFile(String url,File dest,long bytes,String expected,String title)throws Exception{File part=new File(dest.getPath()+".part");try(InputStream in=open(url);OutputStream out=new BufferedOutputStream(new FileOutputStream(part))){long actual=copy(in,out,bytes,title);if(actual!=bytes)throw new IOException("下载长度不符");}catch(Exception e){part.delete();throw e;}if(!sha(part).equals(expected)){part.delete();throw new IOException("下载校验失败");}if(dest.exists()||!part.renameTo(dest))throw new IOException("无法保存下载文件");}
 private static InputStream open(String address)throws IOException{URL url=new URL(address);if(url.getUserInfo()!=null||(!url.getProtocol().equals("https")&&!url.getProtocol().equals("http")))throw new IOException("仅支持HTTP/HTTPS下载地址");for(int i=0;i<6;i++){HttpURLConnection c=(HttpURLConnection)url.openConnection();c.setConnectTimeout(20000);c.setReadTimeout(60000);c.setInstanceFollowRedirects(false);c.setRequestProperty("User-Agent","OrTTS-Android/0.2");int code=c.getResponseCode();if(code>=300&&code<400){String next=c.getHeaderField("Location");c.disconnect();if(next==null)throw new IOException("无效下载跳转");url=new URL(url,next);if(url.getUserInfo()!=null||(!url.getProtocol().equals("https")&&!url.getProtocol().equals("http")))throw new IOException("无效下载跳转");continue;}if(code!=200){c.disconnect();throw new IOException("下载失败 HTTP "+code);}InputStream in=c.getInputStream();return new FilterInputStream(in){public void close()throws IOException{try{super.close();}finally{c.disconnect();}}};}throw new IOException("下载跳转次数过多");}
 private static byte[] readLimited(InputStream in,int max)throws IOException{try(InputStream input=in;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[8192];int n;while((n=input.read(b))!=-1){if(out.size()+n>max)throw new IOException("清单过大");out.write(b,0,n);}return out.toByteArray();}}
 private long copy(InputStream in,OutputStream out,long max,String title)throws IOException{byte[] b=new byte[1<<20];int n;long total=0,last=0;while((n=in.read(b))!=-1){total+=n;if(total>max)throw new IOException("文件超过清单大小");out.write(b,0,n);long now=System.currentTimeMillis();if(title!=null&&now-last>600){progress.update(title+" · "+(total>>20)+" MB");last=now;}}return total;}
}
