package com.orient.ortts.demo;

final class SpeechBridge {
 interface TextSink {void onText(String text,int endpoint,long segment);}
 static void load()throws java.io.IOException {NativeBridge.ensureLoaded();if(!available())throw new java.io.IOException("此安装包未包含多模型后端");}
 static native boolean available();
 static native String synthesize(String family,String library,String data,String identity,String path,String voice,String text,boolean stream,NativeBridge.PcmSink sink,String out,String reference,String referenceText,String cache,int threads);
 static native String environment();
 static native void openAsr(String family,String path);
 static native void accept(float[] pcm,int count,TextSink sink);
 static native void finish(TextSink sink);
 static native void close();
 static native void endTask();
 static native void cancel();
}
