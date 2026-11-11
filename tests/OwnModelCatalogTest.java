package com.orient.ortts.demo;
import org.json.*;import java.nio.file.*;import java.util.*;
public class OwnModelCatalogTest {
 static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);}
 static byte[] read(String root,String name)throws Exception{return Files.readAllBytes(Paths.get(root,name));}
 public static void main(String[] args)throws Exception{
 String root=args[0];check(OwnModelCatalog.repositories(new JSONObject(new String(read(root,"owner.json"),"UTF-8"))).size()==2,"owner filter");
 List<JSONObject> sources=OwnModelCatalog.manifests("OrientLuna/OrTTS-Qwen3-LFM-0.6B",new JSONObject(new String(read(root,"files.json"),"UTF-8")));check(sources.size()==2,"nested manifests");JSONArray models=new JSONArray();
 for(int i=0;i<2;i++){byte[] b=read(root,i==0?"q8.json":"ptq.json");models.put(OwnModelCatalog.normalize(sources.get(i),b));boolean rejected=false;try{OwnModelCatalog.normalize(sources.get(i),Arrays.copyOf(b,b.length-1));}catch(Exception e){rejected=true;}check(rejected,"tamper");}
 check(models.getJSONObject(1).getJSONArray("supported_variants").toString().equals("[\"P3\"]"),"PTQ scope");check(OwnModelCatalog.merge(models,models).length()==2,"merge");
 for(String key:new String[]{"runtime","model_id","files"}){JSONObject m=new JSONObject(new String(read(root,"ptq.json"),"UTF-8"));m.put(key,key.equals("runtime")?new JSONObject().put("schema","unknown"):key.equals("model_id")?"OtherOwner/OrTTS-Fake":new JSONArray().put(new JSONObject().put("path","../escape").put("sha256",String.join("",Collections.nCopies(64,"a"))).put("bytes",1)));byte[] b=m.toString().getBytes("UTF-8");JSONObject s=new JSONObject(sources.get(1).toString()).put("manifest_sha256",OwnModelCatalog.sha(b));boolean rejected=false;try{OwnModelCatalog.normalize(s,b);}catch(Exception e){rejected=true;}check(rejected,key);}
 if(args.length>1){JSONArray live=OwnModelCatalog.refresh(new JSONArray());check(live.length()>=3,"live discovery");Files.write(Paths.get(args[1]),live.toString(2).getBytes("UTF-8"));System.out.println("Live discovery: "+live.length()+" models");}System.out.println("PASS: catalog discovery, nested PTQ, SHA, contract rejection and merge");
 }
}
