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
 private static String shaBytes(byte[] bytes)throws Exception{byte[] hash=MessageDigest.getInstance("SHA-256").digest(bytes);StringBuilder s=new StringBuilder();for(byte b:hash)s.append(String.format("%02x",b&255));return s.toString();}
 static String sha(File f)throws Exception{MessageDigest d=MessageDigest.getInstance("SHA-256");try(InputStream in=new BufferedInputStream(new FileInputStream(f))){byte[] b=new byte[1<<20];int n;while((n=in.read(b))!=-1)d.update(b,0,n);}StringBuilder s=new StringBuilder();for(byte v:d.digest())s.append(String.format("%02x",v&255));return s.toString();}
 static File child(File root,String path)throws Exception{if(path.isEmpty()||path.startsWith("/")||path.contains("\\")||Arrays.asList(path.split("/")).contains(".."))throw new IOException("无效模型路径");File p=new File(root,path).getCanonicalFile();if(!p.toPath().startsWith(root.getCanonicalFile().toPath())||p.equals(root.getCanonicalFile()))throw new IOException("模型路径越界");return p;}
 File current(){String p=context.getSharedPreferences("models",0).getString("current",null);return p==null?null:new File(p);}
 boolean matchesCurrent(String id,String revision){try{File dir=current();if(dir==null)return false;JSONObject m=manifest(dir);return id.equals(m.getString("model_id"))&&revision.equals(m.getString("revision"));}catch(Exception e){return false;}}
 private File findInstalled(String id,String revision){File home=new File(context.getFilesDir(),"models");File[] roots=home.listFiles();if(roots==null)return null;File best=null;int count=-1;for(File root:roots)try{if(!root.isDirectory()||!root.getName().startsWith("release-")||!root.getCanonicalFile().getParentFile().equals(home.getCanonicalFile()))continue;JSONObject m=manifest(root);if(id.equals(m.getString("model_id"))&&revision.equals(m.getString("revision"))&&m.getJSONArray("files").length()>count){best=root;count=m.getJSONArray("files").length();}}catch(Exception ignored){}return best;}
 void selectInstalled(String id,String revision){File root=findInstalled(id,revision);android.content.SharedPreferences.Editor e=context.getSharedPreferences("models",0).edit();if(root==null)e.remove("current");else e.putString("current",root.getAbsolutePath());e.apply();}
 String downloadSummary(){try{JSONObject d=manifest(current()).getJSONObject("last_download");return String.format(Locale.ROOT,"复用本地 %.2f GB，下载 %.2f GB",d.getLong("reused_bytes")/1e9,d.getLong("downloaded_bytes")/1e9);}catch(Exception e){return "";}}
 String modelLabel(){try{JSONObject m=manifest(current());return m.optString("display_name",m.getString("model_id"))+" · "+m.getString("revision");}catch(Exception e){return "尚未准备";}}
 private File staging()throws IOException{File p=new File(context.getFilesDir(),"models/.staging-"+UUID.randomUUID());if(!p.mkdirs())throw new IOException("无法准备模型目录");return p;}
 private static void discard(File p)throws IOException{if(!p.exists())return;try(java.util.stream.Stream<Path>w=Files.walk(p.toPath())){for(Path x:(Iterable<Path>)w.sorted(Comparator.reverseOrder())::iterator)Files.deleteIfExists(x);}}
 static JSONObject manifest(File dir)throws Exception{File f=new File(dir,"model.json");if(!f.isFile()||f.length()>2*1024*1024)throw new IOException("缺少模型清单");return new JSONObject(new String(Files.readAllBytes(f.toPath()),StandardCharsets.UTF_8));}
 private LinkedHashMap<String,JSONObject> entries(JSONObject m)throws Exception{if(!m.getString("schema").equals("ortts-download-manifest-v1"))throw new IOException("不支持的模型清单");JSONArray a=m.getJSONArray("files");if(a.length()<1||a.length()>256)throw new IOException("模型文件数量异常");LinkedHashMap<String,JSONObject> out=new LinkedHashMap<>();long total=0;for(int i=0;i<a.length();i++){JSONObject v=a.getJSONObject(i);String path=v.getString("path"),hash=v.getString("sha256");if(!hash.matches("[a-f0-9]{64}")||v.getLong("bytes")<0||out.put(path,v)!=null)throw new IOException("无效或重复模型文件");child(context.getFilesDir(),path);total+=v.getLong("bytes");}if(total>8L*1024*1024*1024)throw new IOException("模型包过大");return out;}
 private static final String[] CORE={"native/model.gguf","native/bridge/MANIFEST.json","native/tokenizer-b260k-MIXED_Q4_0.gguf","native/tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf","native/vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf","voices/female.f32","voices/male.f32"};
 private static List<String> core(JSONObject manifest)throws Exception {
  DecoderSelection decoder=DecoderSelection.from(manifest);List<String> out=new ArrayList<>(Arrays.asList(CORE));
  if(decoder.liquid()&&manifest.getJSONObject("runtime").getJSONObject("decoder").has("dequant_manifest")){
   out=new ArrayList<>(Arrays.asList("native/model.gguf","voices/female.f32","voices/male.f32"));
   out.add(manifest.getJSONObject("runtime").getJSONObject("decoder").getString("dequant_manifest"));
  }
  return out;
 }
 private static List<String> predictor(Map<String,JSONObject> files)throws Exception {
  List<String> out=new ArrayList<>(Arrays.asList("P3/predictor/config.json","P3/predictor/talker_config.json"));
  out.add(files.containsKey("P3/predictor/predictor.gguf")?"P3/predictor/predictor.gguf":"P3/predictor/predictor.safetensors");return out;
 }
 static String acousticIdentity(File root)throws Exception {
  JSONObject m=manifest(root);DecoderSelection d=DecoderSelection.from(m);String path="native/bridge/MANIFEST.json";
  if(d.liquid())path=m.getJSONObject("runtime").getJSONObject("decoder").optString("dequant_manifest",path);
  return sha(child(root,path));
 }
 void requireCompatibleDecoder()throws Exception{File dir=current();if(dir!=null)DecoderSelection.from(manifest(dir)).requireSupported();}
 String decoderLabel(){try{File dir=current();return dir==null?"自动":DecoderSelection.from(manifest(dir)).label();}catch(Exception e){return "未知";}}
 boolean ready(String variant){try{File dir=current();if(dir==null)return false;JSONObject metadata=manifest(dir);Map<String,JSONObject> files=entries(metadata);DecoderSelection decoder=DecoderSelection.from(metadata);decoder.requireSelected(files,files);if(decoder.liquid()){String prefix=decoder.manifest.substring(0,decoder.manifest.lastIndexOf('/')+1);for(Map.Entry<String,JSONObject> entry:files.entrySet())if(entry.getKey().startsWith(prefix)){File f=child(dir,entry.getKey());if(!f.isFile()||f.length()!=entry.getValue().getLong("bytes"))return false;}}for(String path:core(metadata)){JSONObject v=files.get(path);File f=child(dir,path);if(v==null||!f.isFile()||f.length()!=v.getLong("bytes"))return false;}if(variant.equals("P3"))for(String path:predictor(files)){JSONObject v=files.get(path);File f=child(dir,path);if(v==null||!f.isFile()||f.length()!=v.getLong("bytes"))return false;}return variant.equals("P3")||variant.equals("P5");}catch(Exception e){return false;}}
 private LinkedHashMap<String,JSONObject> selected(JSONObject m,String variant)throws Exception{LinkedHashMap<String,JSONObject> all=entries(m);JSONObject rules=m.getJSONObject("selection_rules");Map<String,List<String>> patterns=new LinkedHashMap<>();for(String key:new String[]{"common","P3","P5"}){JSONArray a=rules.getJSONArray(key);List<String> list=new ArrayList<>();for(int i=0;i<a.length();i++)list.add(a.getString(i));patterns.put(key,list);}LinkedHashMap<String,JSONObject> out=new LinkedHashMap<>();for(String path:DownloadSelection.select(all.keySet(),patterns,variant))out.put(path,all.get(path));DecoderSelection.from(m).requireSelected(all,out);return out;}
 private static JSONArray fileArray(Map<String,JSONObject> files){JSONArray a=new JSONArray();for(JSONObject v:files.values())a.put(v);return a;}
 private void requireCore(JSONObject manifest,Map<String,JSONObject> files)throws Exception{DecoderSelection decoder=DecoderSelection.from(manifest);decoder.requireSelected(files,files);decoder.requireSupported();for(String path:core(manifest))if(!files.containsKey(path))throw new IOException("模型缺少必需文件："+path);boolean any=false;for(String path:files.keySet())any|=path.startsWith("P3/predictor/");if(any)for(String path:predictor(files))if(!files.containsKey(path))throw new IOException("P3预测器不完整");}
 private File activate(File dir,JSONObject m)throws Exception{
  LinkedHashMap<String,JSONObject> files=entries(m);int i=0;for(Map.Entry<String,JSONObject> e:files.entrySet()){progress.update("校验模型 "+(++i)+"/"+files.size());File f=child(dir,e.getKey());JSONObject v=e.getValue();if(!f.isFile()||f.length()!=v.getLong("bytes")||!sha(f).equals(v.getString("sha256")))throw new IOException("文件校验失败："+e.getKey());}
  requireCore(m,files);
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
 File download(String manifestUrl,String variant)throws Exception{return download(manifestUrl,variant,null);}
 File download(String manifestUrl,String variant,JSONObject expected)throws Exception{
  progress.update("获取模型清单");byte[] bytes=readManifest(manifestUrl,expected);JSONObject m=new JSONObject(new String(bytes,StandardCharsets.UTF_8));if(expected!=null&&(!shaBytes(bytes).equals(expected.getString("manifest_sha256"))||!m.getString("model_id").equals(expected.getString("id"))||!m.getString("revision").equals(expected.getString("revision"))))throw new IOException("模型清单与目录固定版本不匹配");LinkedHashMap<String,JSONObject> files=selected(m,variant);requireCore(m,files);File old=findInstalled(m.getString("model_id"),m.getString("revision"));JSONObject oldMeta=null;
  if(old!=null)try{oldMeta=manifest(old);if(!oldMeta.getString("model_id").equals(m.getString("model_id"))||!oldMeta.getString("revision").equals(m.getString("revision"))){old=null;oldMeta=null;}}catch(Exception ignored){old=null;oldMeta=null;}
  File[] installedRoots=new File(context.getFilesDir(),"models").listFiles(f->f.isDirectory()&&f.getName().startsWith("release-"));VerifiedAssetReuse shared=new VerifiedAssetReuse(installedRoots==null?Collections.emptyList():Arrays.asList(installedRoots));File dir=staging();try{String base=m.getString("base_url");List<String> staged=new ArrayList<>();long total=0;for(JSONObject v:files.values())total+=v.getLong("bytes");long reused=0;int position=0;
   for(Map.Entry<String,JSONObject> e:files.entrySet()){position++;progress.update("准备模型 "+position+"/"+files.size());JSONObject v=e.getValue();File have=old==null?null:child(old,e.getKey());if(have!=null&&have.isFile()&&have.length()==v.getLong("bytes")&&sha(have).equals(v.getString("sha256"))){reused+=have.length();continue;}File f=child(dir,e.getKey());f.getParentFile().mkdirs();if(shared.materialize(v,f)){reused+=v.getLong("bytes");progress.update("复用本地文件 "+position+"/"+files.size());}else downloadFile(v.optString("url",base+e.getKey()),v.optJSONArray("download_urls"),f,v.getLong("bytes"),v.getString("sha256"),"下载模型 "+position+"/"+files.size());staged.add(e.getKey());}
   m.put("files",fileArray(files));m.put("last_download",new JSONObject().put("variant",variant).put("selected_bytes",total).put("reused_bytes",reused).put("downloaded_bytes",total-reused));
   if(old==null){Files.write(new File(dir,"model.json").toPath(),m.toString().getBytes(StandardCharsets.UTF_8));return activate(dir,m);}
   // Same revision: add verified missing components to the existing shared root.
   LinkedHashMap<String,JSONObject> installed=entries(oldMeta);installed.putAll(files);requireCore(m,installed);
   for(String path:staged){File target=child(old,path);target.getParentFile().mkdirs();Files.move(child(dir,path).toPath(),target.toPath(),StandardCopyOption.REPLACE_EXISTING);}
   m.put("files",fileArray(installed));File temp=new File(old,"model.json.tmp");Files.write(temp.toPath(),m.toString().getBytes(StandardCharsets.UTF_8));Files.move(temp.toPath(),new File(old,"model.json").toPath(),StandardCopyOption.REPLACE_EXISTING);discard(dir);context.getSharedPreferences("models",0).edit().putString("current",old.getAbsolutePath()).apply();return old;
  }catch(Exception e){discard(dir);throw e;}
 }

 void downloadFile(String url,File dest,long bytes,String expected,String title)throws Exception{downloadFile(url,null,dest,bytes,expected,title);}
 void downloadFile(String url,JSONArray alternatives,File dest,long bytes,String expected,String title)throws Exception{
  DownloadNetworkPolicy.check(context);Exception failure=null;for(String address:DownloadSources.candidates(context,url,alternatives)){File part=new File(dest.getPath()+".part");try{
   progress.update(title+" · "+DownloadSources.label(DownloadRoute.channel(address)));
   try(InputStream in=open(address,context);OutputStream out=new BufferedOutputStream(new FileOutputStream(part))){long actual=copy(in,out,bytes,title,true);if(actual!=bytes)throw new IOException("下载长度不符");}
   progress.update("校验文件 · "+dest.getName());if(!sha(part).equals(expected))throw new IOException("下载校验失败");if(dest.exists()||!part.renameTo(dest))throw new IOException("无法保存下载文件");DownloadSources.success(context,address);return;
  }catch(Exception e){DownloadNetworkPolicy.check(context);DownloadSources.rejected(address);failure=e;}finally{part.delete();}}
  throw new IOException("所有可用下载通道均失败",failure);
 }

 private byte[] readManifest(String url,JSONObject expected)throws Exception{
  Exception failure=null;for(String address:DownloadSources.candidates(context,url,null))try{
   byte[] b=readLimited(open(address),2*1024*1024);JSONObject m=new JSONObject(new String(b,StandardCharsets.UTF_8));
   if(expected!=null&&(!shaBytes(b).equals(expected.getString("manifest_sha256"))||!m.getString("model_id").equals(expected.getString("id"))||!m.getString("revision").equals(expected.getString("revision"))))throw new IOException("模型清单与目录固定版本不匹配");return b;
  }catch(Exception e){failure=e;}throw new IOException("无法从所选通道获取可信模型清单",failure);
 }
 private static InputStream open(String address)throws IOException{return open(address,null);}
 private static InputStream open(String address,Context networkContext)throws IOException{URL url=new URL(address);if(url.getUserInfo()!=null||(!url.getProtocol().equals("https")&&!url.getProtocol().equals("http")))throw new IOException("仅支持HTTP/HTTPS下载地址");for(int i=0;i<6;i++){HttpURLConnection c=(HttpURLConnection)(networkContext==null?url.openConnection():DownloadNetworkPolicy.open(networkContext,url));c.setConnectTimeout(8000);c.setReadTimeout(20000);c.setInstanceFollowRedirects(false);c.setRequestProperty("User-Agent","OrTTS-Android/0.3.1");int code=c.getResponseCode();if(code>=300&&code<400){String next=c.getHeaderField("Location");c.disconnect();if(next==null)throw new IOException("无效下载跳转");URL redirected=new URL(url,next);if(url.getProtocol().equals("https")&&!redirected.getProtocol().equals("https"))throw new IOException("不允许HTTPS降级跳转");url=redirected;if(url.getUserInfo()!=null||(!url.getProtocol().equals("https")&&!url.getProtocol().equals("http")))throw new IOException("无效下载跳转");continue;}if(code!=200){c.disconnect();throw new IOException("下载失败 HTTP "+code);}InputStream in=c.getInputStream();return new FilterInputStream(in){public void close()throws IOException{try{super.close();}finally{c.disconnect();}}};}throw new IOException("下载跳转次数过多");}
 private static byte[] readLimited(InputStream in,int max)throws IOException{try(InputStream input=in;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[8192];int n;while((n=input.read(b))!=-1){if(out.size()+n>max)throw new IOException("清单过大");out.write(b,0,n);}return out.toByteArray();}}
 private long copy(InputStream in,OutputStream out,long max,String title)throws IOException{return copy(in,out,max,title,false);}
 private long copy(InputStream in,OutputStream out,long max,String title,boolean network)throws IOException{byte[] b=new byte[1<<20];int n;long total=0,last=0;while((n=in.read(b))!=-1){total+=n;if(total>max)throw new IOException("文件超过清单大小");out.write(b,0,n);long now=System.currentTimeMillis();if(title!=null&&now-last>600){if(network)DownloadNetworkPolicy.check(context);progress.update(String.format(Locale.ROOT,"%s · %.1f / %.1f MB · %.1f%%",title,total/1e6,max/1e6,max>0?100.*total/max:0));last=now;}}return total;}
}
