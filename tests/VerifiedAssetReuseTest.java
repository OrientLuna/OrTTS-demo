package com.orient.ortts.demo;
import java.io.*;import java.nio.file.*;import java.util.*;import org.json.*;
public class VerifiedAssetReuseTest {
 public static void main(String[]args)throws Exception{
 Path home=Files.createTempDirectory("ortts-reuse-");try{
 File root=home.resolve("old").toFile();root.mkdirs();File source=new File(root,"a.bin");Files.write(source.toPath(),"shared weights".getBytes("UTF-8"));JSONObject entry=new JSONObject().put("path","a.bin").put("bytes",source.length()).put("sha256",VerifiedAssetReuse.sha(source));Files.write(new File(root,"model.json").toPath(),new JSONObject().put("files",new JSONArray().put(entry)).toString().getBytes("UTF-8"));
 VerifiedAssetReuse reuse=new VerifiedAssetReuse(Arrays.asList(root));File target=home.resolve("new/renamed.bin").toFile();if(!reuse.materialize(entry,target)||!VerifiedAssetReuse.sha(target).equals(entry.getString("sha256")))throw new AssertionError("reuse failed");Files.write(source.toPath(),"broken weights".getBytes("UTF-8"));if(reuse.materialize(entry,home.resolve("missing.bin").toFile()))throw new AssertionError("corruption accepted");if(!VerifiedAssetReuse.sha(target).equals(entry.getString("sha256")))throw new AssertionError("source mutation affected target");System.out.println("PASS: cross-version content reuse, renamed path, corruption rejection, independent copies");
 }finally{try(java.util.stream.Stream<Path>s=Files.walk(home)){for(Path p:(Iterable<Path>)s.sorted(Comparator.reverseOrder())::iterator)Files.deleteIfExists(p);}}
 }
}
