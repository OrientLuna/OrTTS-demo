package com.orient.ortts.demo;
import java.io.*;
import java.nio.file.*;
import java.util.concurrent.atomic.AtomicBoolean;
public class PinnedAssetTest {
 public static void main(String[] args)throws Exception {
  File p=File.createTempFile("moss-integrity-",".bin",new File(args[0]));AtomicBoolean stop=new AtomicBoolean();
  String sha="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
  try{
   Files.write(p.toPath(),new byte[]{97,98,99});check(PinnedAsset.valid(p,3,sha,stop));
   check(!PinnedAsset.valid(p,4,sha,stop));check(!PinnedAsset.valid(p,3,"0".repeat(64),stop));
   Files.write(p.toPath(),new byte[]{97,98,100});check(!PinnedAsset.valid(p,3,sha,stop));
   stop.set(true);try{PinnedAsset.valid(p,3,sha,stop);throw new AssertionError("cancel ignored");}catch(IOException expected){}
   stop.set(false);check(!PinnedAsset.valid(new File(args[0],"missing-reference.wav"),3,sha,stop));
   try{PinnedAsset.valid(p,3,"not-a-sha",stop);throw new AssertionError("bad schema");}catch(IOException expected){}
   System.out.println("PINNED_ASSET_PASS: exact hash, bad SHA, wrong length, corruption, cancellation, missing reference, invalid schema");
  }finally{Files.delete(p.toPath());}
 }
 static void check(boolean ok){if(!ok)throw new AssertionError();}
}
