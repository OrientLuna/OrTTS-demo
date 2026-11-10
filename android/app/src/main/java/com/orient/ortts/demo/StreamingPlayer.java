package com.orient.ortts.demo;
import android.media.*;
import android.os.*;
import org.json.*;
import java.util.*;
final class StreamingPlayer implements NativeBridge.PcmSink,AutoCloseable {
 private AudioTrack track;private int sampleRate=24000,channels=1;private boolean formatSet;private volatile boolean stopped;private final boolean enabled;private final PlaybackBufferPolicy policy;private final long start=SystemClock.elapsedRealtimeNanos();
 private final ArrayList<float[]> pending=new ArrayList<>();private long pendingSamples=0,samples=0,firstWrite=-1,firstPlay=-1;private int chunks=0;private boolean started=false;
 StreamingPlayer(boolean enabled,int textCharacters){this.enabled=enabled;this.policy=new PlaybackBufferPolicy(textCharacters);}
 @Override public void onPcm(float[] pcm,int rate){onPcm(pcm,rate,1);}
 @Override public void onPcm(float[] pcm,int rate,int count){
  if(stopped)throw new IllegalStateException("Playback stopped");if((count!=1&&count!=2)||rate<8000||rate>192000||pcm.length%count!=0)throw new IllegalArgumentException("PCM format");if(formatSet&&(sampleRate!=rate||channels!=count))throw new IllegalArgumentException("PCM format changed");for(float x:pcm)if(!Float.isFinite(x))throw new IllegalArgumentException("Nonfinite PCM");sampleRate=rate;channels=count;formatSet=true;chunks++;if(!enabled){samples+=pcm.length;return;}
  int mask=channels==2?AudioFormat.CHANNEL_OUT_STEREO:AudioFormat.CHANNEL_OUT_MONO;
  if(track==null){int size=Math.max(AudioTrack.getMinBufferSize(rate,mask,AudioFormat.ENCODING_PCM_FLOAT),12*rate*channels*4);
   track=new AudioTrack.Builder().setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()).setAudioFormat(new AudioFormat.Builder().setSampleRate(rate).setChannelMask(mask).setEncoding(AudioFormat.ENCODING_PCM_FLOAT).build()).setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(size).build();
   if(track.getState()!=AudioTrack.STATE_INITIALIZED)throw new IllegalStateException("音频播放器初始化失败");}
  if(!started){pending.add(pcm);pendingSamples+=pcm.length;double seconds=policy.update(pendingSamples/channels,rate,(SystemClock.elapsedRealtimeNanos()-start)/1e6);if(pendingSamples/channels>=rate*seconds)begin();}else write(pcm);
 }
 private void write(float[] pcm){for(int offset=0;offset<pcm.length;){if(stopped)throw new IllegalStateException("Playback stopped");int n=track.write(pcm,offset,pcm.length-offset,AudioTrack.WRITE_BLOCKING);if(n<=0)throw new IllegalStateException("音频写入失败 "+n);offset+=n;samples+=n;if(firstWrite<0)firstWrite=SystemClock.elapsedRealtimeNanos()-start;}}
 private void begin(){if(track==null||started)return;if(Build.VERSION.SDK_INT>=31)track.setStartThresholdInFrames(1);track.play();firstPlay=SystemClock.elapsedRealtimeNanos()-start;started=true;for(float[] b:pending)write(b);pending.clear();}
 void drain(){if(!enabled||track==null)return;begin();long frames=samples/channels;long deadline=SystemClock.elapsedRealtime()+frames*1000/sampleRate+5000;while(!stopped&&Integer.toUnsignedLong(track.getPlaybackHeadPosition())<frames){if(SystemClock.elapsedRealtime()>deadline)throw new IllegalStateException("播放结束等待超时");SystemClock.sleep(10);}}
 JSONObject metrics()throws JSONException{long played=track==null?0:Integer.toUnsignedLong(track.getPlaybackHeadPosition());return new JSONObject().put("playback_enabled",enabled).put("sample_rate",sampleRate).put("channels",channels).put("submitted_frames",samples/channels).put("played_frames",played).put("initial_buffer_ms",policy.targetSeconds()*1000).put("buffer_policy","adaptive").put("observed_startup_RTF",Double.isNaN(policy.observedRTF())?JSONObject.NULL:policy.observedRTF()).put("chunks",chunks).put("submitted_samples",samples).put("played_samples",played*channels).put("first_write_ms",firstWrite<0?JSONObject.NULL:firstWrite/1e6).put("play_requested_ms",firstPlay<0?JSONObject.NULL:firstPlay/1e6).put("underruns",track==null?JSONObject.NULL:track.getUnderrunCount()).put("start_threshold_frames",track!=null&&Build.VERSION.SDK_INT>=31?track.getStartThresholdInFrames():JSONObject.NULL).put("audible_onset_ms",JSONObject.NULL);}
 void requestStop(){stopped=true;synchronized(this){if(track!=null)try{track.pause();track.flush();}catch(IllegalStateException ignored){}}}
 public synchronized void close(){if(track!=null){try{track.stop();}finally{track.release();track=null;}}}
}
