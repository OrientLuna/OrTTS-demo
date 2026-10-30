package com.orient.ortts.demo;
final class NativeBridge {
 private static boolean loaded;
 static synchronized void ensureLoaded()throws java.io.IOException{
  if(loaded)return;
  try{
   if(!DeviceSupport.supportsCurrentRuntime())throw new java.io.IOException("当前设备不支持此安装包需要的CPU指令集（DotProd、I8MM、FP16）。");
   System.loadLibrary("ortts_jni");loaded=true;
  }catch(LinkageError e){throw new java.io.IOException("无法加载语音引擎："+e.getMessage(),e);}
 }
 interface PcmSink { void onPcm(float[] pcm,int rate); }
 static String run(String root,String variant,String voice,String text,int threads,long seed,boolean streaming,PcmSink sink,String out,String bridgeSha)throws java.io.IOException{ensureLoaded();return runNative(root,variant,voice,text,threads,seed,streaming,sink,out,bridgeSha);}
 static synchronized void release(){if(loaded)releaseNative();}
 private static native String runNative(String root,String variant,String voice,String text,int threads,long seed,boolean streaming,PcmSink sink,String out,String bridgeSha);
 private static native void releaseNative();
}
