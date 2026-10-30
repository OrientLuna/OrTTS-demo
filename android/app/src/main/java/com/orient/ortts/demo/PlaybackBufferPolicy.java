package com.orient.ortts.demo;

/** Startup buffering only; this does not change model execution or PCM. */
final class PlaybackBufferPolicy {
 private final double predictedSeconds;
 private long firstSamples=-1;
 private double firstMs;
 private double target=1.0, observedRTF=Double.NaN;
 PlaybackBufferPolicy(int textCharacters){predictedSeconds=Math.max(1.0,textCharacters*0.22);}
 double update(long accumulated,int rate,double nowMs){
  if(firstSamples<0){firstSamples=accumulated;firstMs=nowMs;return target;}
  double produced=(accumulated-firstSamples)/(double)rate;
  if(produced>0.1){
   observedRTF=Math.max(0,(nowMs-firstMs)/1000.0/produced);
   double cautiousRTF=observedRTF*1.10+0.05;
   target=Math.max(1.0,Math.min(10.0,0.35+predictedSeconds*Math.max(0,1-1/Math.max(cautiousRTF,0.01))));
  }
  return target;
 }
 double targetSeconds(){return target;}
 double observedRTF(){return observedRTF;}
}
