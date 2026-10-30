package com.orient.ortts.demo;
import android.media.*;
import android.os.*;
import org.json.*;
import java.util.*;
final class StreamingPlayer implements NativeBridge.PcmSink,AutoCloseable {
 private AudioTrack track;private final boolean enabled;private final PlaybackBufferPolicy policy;private final long start=SystemClock.elapsedRealtimeNanos();
 private final ArrayList<float[]> pending=new ArrayList<>();private long pendingSamples=0,samples=0,firstWrite=-1,firstPlay=-1;private int chunks=0;private boolean started=false;
 StreamingPlayer(boolean enabled,int textCharacters){this.enabled=enabled;this.policy=new PlaybackBufferPolicy(textCharacters);}
 @Override public void onPcm(float[] pcm,int rate){
  chunks++;if(!enabled){samples+=pcm.length;return;}
  if(track==null){int size=Math.max(AudioTrack.getMinBufferSize(rate,AudioFormat.CHANNEL_OUT_MONO,AudioFormat.ENCODING_PCM_FLOAT),12*rate*4);
   track=new AudioTrack.Builder().setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()).setAudioFormat(new AudioFormat.Builder().setSampleRate(rate).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).setEncoding(AudioFormat.ENCODING_PCM_FLOAT).build()).setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(size).build();
   if(track.getState()!=AudioTrack.STATE_INITIALIZED)throw new IllegalStateException("音频播放器初始化失败");}
  if(!started){pending.add(pcm);pendingSamples+=pcm.length;double seconds=policy.update(pendingSamples,rate,(SystemClock.elapsedRealtimeNanos()-start)/1e6);if(pendingSamples>=rate*seconds)begin();}else write(pcm);
 }
 private void write(float[] pcm){for(int offset=0;offset<pcm.length;){int n=track.write(pcm,offset,pcm.length-offset,AudioTrack.WRITE_BLOCKING);if(n<=0)throw new IllegalStateException("音频写入失败 "+n);offset+=n;samples+=n;if(firstWrite<0)firstWrite=SystemClock.elapsedRealtimeNanos()-start;}}
 private void begin(){if(track==null||started)return;if(Build.VERSION.SDK_INT>=31){track.setStartThresholdInFrames(1);for(float[] b:pending)write(b);track.play();}else{track.setBufferSizeInFrames(Math.max((int)pendingSamples,AudioTrack.getMinBufferSize(24000,AudioFormat.CHANNEL_OUT_MONO,AudioFormat.ENCODING_PCM_FLOAT)/4));track.play();for(float[] b:pending)write(b);}pending.clear();firstPlay=SystemClock.elapsedRealtimeNanos()-start;started=true;}
 void drain(){if(!enabled||track==null)return;begin();long deadline=SystemClock.elapsedRealtime()+samples*1000/24000+5000;while(Integer.toUnsignedLong(track.getPlaybackHeadPosition())<samples){if(SystemClock.elapsedRealtime()>deadline)throw new IllegalStateException("播放结束等待超时");SystemClock.sleep(10);}}
 JSONObject metrics()throws JSONException{return new JSONObject().put("playback_enabled",enabled).put("initial_buffer_ms",policy.targetSeconds()*1000).put("buffer_policy","adaptive").put("observed_startup_RTF",Double.isNaN(policy.observedRTF())?JSONObject.NULL:policy.observedRTF()).put("chunks",chunks).put("submitted_samples",samples).put("played_samples",track==null?0:Integer.toUnsignedLong(track.getPlaybackHeadPosition())).put("first_write_ms",firstWrite<0?JSONObject.NULL:firstWrite/1e6).put("play_requested_ms",firstPlay<0?JSONObject.NULL:firstPlay/1e6).put("underruns",track==null?JSONObject.NULL:track.getUnderrunCount()).put("start_threshold_frames",track!=null&&Build.VERSION.SDK_INT>=31?track.getStartThresholdInFrames():JSONObject.NULL).put("audible_onset_ms",JSONObject.NULL);}
 public void close(){if(track!=null){try{track.stop();}finally{track.release();track=null;}}}
}
