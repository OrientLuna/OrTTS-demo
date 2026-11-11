package com.orient.ortts.demo;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.media.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.util.*;

/** One foreground worker and one active model; no inference on the UI thread. */
public final class SpeechActivity extends Activity {
 private LinearLayout box;private Spinner task,model,voice;private EditText input;private TextView info,status,result;
 private Button run,download,importModel,importAudio,lastAudio,stop,creditsButton,replayButton,legacyButton;private SpeechModels store;private final ArrayList<JSONObject> choices=new ArrayList<>();
 private final Handler ui=new Handler(Looper.getMainLooper());private final TreeMap<Long,String> finals=new TreeMap<>();
 private int qaRemaining=1;private final JSONArray qaRuns=new JSONArray();private JSONObject lastTtsReport;
 private String verifiedTtsIdentity="";private long cacheEpoch;private boolean foreground;
 private volatile boolean recording,cancelled,destroyed;private boolean busy,leaveAfterStop;
 private volatile AudioRecord recorder;private volatile StreamingPlayer player;private MediaPlayer replay;
 private final StringBuilder partial=new StringBuilder();
 private interface Job {void run()throws Exception;}
 private void message(String value){ui.post(()->{if(!destroyed)status.setText(value);});}
 private Button button(String text,Runnable action){Button b=new Button(this);b.setText(text);b.setOnClickListener(v->action.run());box.addView(b);return b;}
 private Spinner spinner(){Spinner s=new Spinner(this);box.addView(s);return s;}
 private void values(Spinner s,List<String> values){s.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,values));}
 private JSONObject selected(){return choices.isEmpty()?null:choices.get(Math.max(0,model.getSelectedItemPosition()));}
 private void working(boolean value){busy=value;task.setEnabled(!value);model.setEnabled(!value);voice.setEnabled(!value);input.setEnabled(!value);download.setEnabled(!value);importModel.setEnabled(!value);importAudio.setEnabled(!value);lastAudio.setEnabled(!value);run.setEnabled(!value||recording);run.setText(recording?"结束录音并识别":task.getSelectedItemPosition()==0?"合成并播放":"开始录音识别");stop.setEnabled(value);}
 private void submit(Job job){
  if(busy||!MainActivity.busy.compareAndSet(false,true)){message("请等待当前任务完成");return;}
  cacheEpoch++;cancelled=false;store.prepare();working(true);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
  MainActivity.worker.execute(()->{boolean success=false;try{job.run();success=!cancelled;}catch(Exception e){message(cancelled?"已停止":"操作失败："+e.getMessage());}
   finally{try{if(success){SpeechBridge.endTask();}else{SpeechBridge.close();verifiedTtsIdentity="";}}catch(Throwable ignored){}recording=false;AudioRecord r=recorder;recorder=null;if(r!=null){try{r.stop();}catch(Exception ignored){}r.release();}MainActivity.busy.set(false);
    final boolean ok=success;ui.post(()->{if(!destroyed){working(false);getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);writeQA(ok);if(ok&&foreground){long ticket=++cacheEpoch;ui.postDelayed(()->{if(ticket==cacheEpoch&&!busy)releaseCache();},30000);}if(leaveAfterStop)finish();}});}});
 }
 @Override public void onCreate(Bundle saved){super.onCreate(saved);ScrollView scroll=new ScrollView(this);box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(24,24,24,24);scroll.addView(box);setContentView(scroll);
  TextView title=new TextView(this);title.setText("第三方语音模型与语音识别");title.setTextSize(26);box.addView(title);
  task=spinner();values(task,Arrays.asList("第三方语音模型 · TTS","语音识别 · 中文 / 英语"));model=spinner();voice=spinner();
  info=new TextView(this);info.setTextIsSelectable(true);box.addView(info);creditsButton=button("模型许可与音色来源",this::credits);download=button("下载 / 检查所选模型",()->{JSONObject m=selected();if(m!=null&&!busy)DownloadNetworkPolicy.confirm(this,allowed->submit(()->DownloadNetworkPolicy.run(allowed,()->store.download(m))));});
  importModel=button("导入所选模型 ZIP",()->{if(!busy)startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/zip").addCategory(Intent.CATEGORY_OPENABLE),403);});
  input=new EditText(this);input.setMinLines(3);input.setText("Hello, welcome to local speech synthesis.");input.setHint("按音色语言输入；Kokoro 中文音色支持中文");box.addView(input);
  run=button("合成并播放",this::primary);importAudio=button("导入 WAV 识别（最多60秒）",()->{if(!busy){Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("audio/*").addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(i,402);}});
  lastAudio=button("识别上次合成",()->{String path=getSharedPreferences("speech",MODE_PRIVATE).getString("last_tts_audio",new File(getFilesDir(),"speech-last.wav").getPath());onActivityResult(402,RESULT_OK,new Intent().setData(android.net.Uri.fromFile(new File(path))));});
  stop=button("取消当前任务",()->cancel(false));
  replayButton=button("重播上次合成",()->{if(busy)return;File file=new File(getFilesDir(),"speech-last.wav");try{if(replay!=null)replay.release();replay=new MediaPlayer();replay.setDataSource(file.getPath());replay.prepare();replay.start();}catch(Exception e){message("暂无可播放音频");}});
  legacyButton=button("返回OrTTS语音合成",()->{if(busy){leaveAfterStop=true;cancel(false);}else finish();});
  result=new TextView(this);result.setTextIsSelectable(true);result.setTextSize(18);box.addView(result);status=new TextView(this);status.setTextIsSelectable(true);box.addView(status);arrange(title);DownloadSources.addSelector(this,box);
  try{store=new SpeechModels(this,this::message);}catch(Exception e){message(e.getMessage());run.setEnabled(false);download.setEnabled(false);return;}
  task.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?>p){}public void onItemSelected(AdapterView<?>p,View v,int position,long id){updateModels();}});
  model.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?>p){}public void onItemSelected(AdapterView<?>p,View v,int position,long id){updateInfo();}});
  updateModels();message("选择任务和模型，下载一次后可离线使用。录音仅在本机处理。");
  if(BuildConfig.DEBUG&&getIntent().getBooleanExtra("speech_qa",false))ui.postDelayed(this::smoke,300);
 }
 private LinearLayout row(View...views){LinearLayout r=new LinearLayout(this);r.setOrientation(LinearLayout.HORIZONTAL);for(View v:views)r.addView(v,new LinearLayout.LayoutParams(0,LinearLayout.LayoutParams.WRAP_CONTENT,1));return r;}
 private void arrange(TextView title){box.removeAllViews();int padding=(int)(16*getResources().getDisplayMetrics().density);box.setPadding(padding,padding,padding,padding);info.setTextSize(14);status.setTextSize(14);result.setMinHeight((int)(100*getResources().getDisplayMetrics().density));result.setHint("识别结果显示在这里");run.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xff2365df));run.setTextColor(android.graphics.Color.WHITE);LinearLayout selection=row(model,voice);((LinearLayout.LayoutParams)model.getLayoutParams()).weight=2;for(View v:new View[]{title,task,selection,info,row(download,importModel),input,run,row(importAudio,lastAudio),status,result,row(stop,replayButton),creditsButton,legacyButton})box.addView(v);}
 private void releaseCache(){cacheEpoch++;MainActivity.worker.execute(()->{try{SpeechBridge.close();}catch(Throwable ignored){}verifiedTtsIdentity="";});}
 @Override protected void onResume(){super.onResume();foreground=true;}
 private void updateModels(){if(busy)return;releaseCache();((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(input.getWindowToken(),0);input.clearFocus();JSONObject previous=selected();if(previous!=null)getPreferences(0).edit().putString("model_"+previous.optString("task"),previous.optString("id")).apply();choices.clear();ArrayList<String> names=new ArrayList<>();boolean asr=task.getSelectedItemPosition()==1;
  for(int i=0;i<store.models.length();i++){JSONObject m=store.models.optJSONObject(i);if(m.optBoolean("demo_enabled")&&asr==m.optString("task").equals("asr")){choices.add(m);names.add(m.optString("display_name"));}}
  values(model,names);String remembered=getPreferences(0).getString("model_"+(asr?"asr":"tts"),"");for(int i=0;i<choices.size();i++)if(choices.get(i).optString("id").equals(remembered))model.setSelection(i);result.setText("");status.setText(asr?"选择识别模型，再录音或导入音频。":"按所选模型和音色支持的语言输入文本。OrTTS 多语种合成可返回 OrTTS语音合成页。");input.setVisibility(asr?View.GONE:View.VISIBLE);voice.setVisibility(asr?View.GONE:View.VISIBLE);importAudio.setVisibility(asr?View.VISIBLE:View.GONE);lastAudio.setVisibility(asr?View.VISIBLE:View.GONE);result.setVisibility(asr?View.VISIBLE:View.GONE);working(false);updateInfo();
 }
 private void updateInfo(){if(busy)return;releaseCache();JSONObject m=selected();if(m==null)return;JSONArray presets=m.optJSONArray("voice_sample");ArrayList<String> names=new ArrayList<>();if(presets!=null)for(int i=0;i<presets.length();i++)names.add(presets.optString(i));if(names.isEmpty())names.add("默认");values(voice,names);
  long bytes=0;JSONArray assets=m.optJSONArray("assets");for(int i=0;i<assets.length();i++)bytes+=assets.optJSONObject(i).optLong("bytes");
   JSONObject license=m.optJSONObject("license_review");String detail=m.optString("family").equals("moss_tts_nano")?"中文 / English · female / male · 48kHz立体声 · 流式合成":m.optString("family").equals("moonshine_asr")?"英文增量识别 · 结果会修订":m.optString("task").equals("asr")?"中文 / 英文 · 离线识别；上方可切换 Moonshine 英语增量识别":"按模型和音色语言输入 · Piper/Kitten 离线合成";
  info.setText(detail+String.format(Locale.ROOT,"\n下载约 %.1f MB · 大小及SHA256校验",bytes/1e6)+"\n许可："+license.optString("weights_license"));
 }
  private void writeQA(boolean ok){if(!BuildConfig.DEBUG||!getIntent().getBooleanExtra("speech_qa",false))return;try{String id=getIntent().getStringExtra("speech_qa_id");if(id==null||!id.matches("[a-zA-Z0-9_-]{1,64}"))id="speech-smoke";File dir=new File(getFilesDir(),"qa");dir.mkdirs();JSONObject report=new JSONObject().put("ok",ok).put("status",status.getText()).put("text",result.getText()).put("model",selected().getString("id"));if(lastTtsReport!=null&&task.getSelectedItemPosition()==0){report.put("engine_reused",lastTtsReport.optBoolean("engine_reused")).put("api_ms",lastTtsReport.optDouble("api_ms")).put("audio_s",lastTtsReport.optDouble("audio_s")).put("tts",lastTtsReport);}qaRuns.put(new JSONObject(report.toString()));String scenario=getIntent().getStringExtra("speech_scenario");if((ok||"cancel".equals(scenario))&&qaRemaining>1){qaRemaining--;
if("switch".equals(scenario)||"rate".equals(scenario)){String target=qaRuns.length()==1?("rate".equals(scenario)?"piper-lessac-medium":"pocket-english-q8"):"kokoro-82m-q8";for(int i=0;i<choices.size();i++)if(choices.get(i).optString("id").equals(target))model.setSelection(i);updateInfo();String preset=target.equals("pocket-english-q8")?"alba":"af_heart";for(int i=0;i<voice.getCount();i++)if(voice.getItemAtPosition(i).equals(preset))voice.setSelection(i);}
   if("voice".equals(scenario)){boolean moss=selected().optString("family").equals("moss_tts_nano");String preset=moss?(qaRuns.length()==1?"male":"female"):(qaRuns.length()==1?"am_adam":"af_heart");for(int i=0;i<voice.getCount();i++)if(voice.getItemAtPosition(i).equals(preset))voice.setSelection(i);}
if("cancel".equals(scenario)&&qaRuns.length()==1)ui.postDelayed(()->cancel(false),100);
 if("reload".equals(scenario))releaseCache();if("ttl".equals(scenario))ui.postDelayed(this::primary,31000);else primary();return;}report.put("runs",qaRuns);try(OutputStream out=new FileOutputStream(new File(dir,id+".json"))){out.write(report.toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8));}}catch(Exception ignored){}}
  private String mossSourceNotice(){try(InputStream in=getAssets().open("licenses/MOSS-SOURCES.txt")){ByteArrayOutputStream b=new ByteArrayOutputStream();byte[] data=new byte[4096];int n;while((n=in.read(data))!=-1){if(b.size()+n>32768)throw new IOException("来源文本过大");b.write(data,0,n);}return "\n\n"+b.toString("UTF-8");}catch(Exception ex){return "\n来源文本读取失败："+ex.getMessage();}}
  private void credits(){JSONObject m=selected();if(m==null)return;JSONObject license=m.optJSONObject("license_review");StringBuilder text=new StringBuilder(license.optString("weights_license")).append("\n").append(license.optString("source"));text.append("\n\neSpeak NG 1.52.0: GPL-3.0-or-later\n应用源码与构建说明：https://github.com/OrientLuna/OrTTS-demo\n模型与音色许可另行适用。");JSONArray voices=m.optJSONArray("voice_origins");if(voices!=null){for(int i=0;i<voices.length();i++){JSONObject v=voices.optJSONObject(i);text.append("\n\n").append(v.optString("voice")).append(" · ").append(v.optString("license")).append("\n").append(v.optString("source"));}text.append("\n音色音频已转换为模型嵌入；模型由Kyutai提供。");}if(m.optString("family").equals("moss_tts_nano")){text.append(mossSourceNotice());text.append("\n\n参考音色：OrTTS female / male。\n");try(InputStream in=getAssets().open(license.getString("license_asset"))){ByteArrayOutputStream b=new ByteArrayOutputStream();byte[] chunk=new byte[8192];int n;while((n=in.read(chunk))!=-1)b.write(chunk,0,n);text.append(b.toString("UTF-8"));}catch(Exception ex){text.append("许可文本读取失败：").append(ex.getMessage());}}new AlertDialog.Builder(this).setTitle("模型与音色来源").setMessage(text).setNegativeButton("关闭",null).setPositiveButton("打开模型来源",(d,w)->startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(license.optString("source"))))).show();}
 private void smoke(){String action=getIntent().getStringExtra("speech_action"),id=getIntent().getStringExtra("speech_model");boolean asr="asr".equals(action)||"last".equals(action);for(int n=0;n<store.models.length();n++){JSONObject target=store.models.optJSONObject(n);if(target!=null&&target.optString("id").equals(id)){asr=target.optString("task").equals("asr");break;}}task.setSelection(asr?1:0);updateModels();for(int i=0;i<choices.size();i++)if(choices.get(i).optString("id").equals(id))model.setSelection(i);updateInfo();
   if("environment".equals(action)){submit(()->{SpeechBridge.load();message("前台调用线程亲和性："+SpeechBridge.environment());});}
   else if("last".equals(action)){lastAudio.performClick();}
  else if("import_zip".equals(action)){String name=getIntent().getStringExtra("speech_zip");if(name==null||!name.matches("[a-zA-Z0-9_.-]{1,80}")){writeQA(false);return;}onActivityResult(403,RESULT_OK,new Intent().setData(android.net.Uri.fromFile(new File(getFilesDir(),name))));}
  else if("download".equals(action)){JSONObject m=selected();submit(()->store.download(m));}
  else if(asr){String name=getIntent().getStringExtra("speech_audio");if(name==null||!name.matches("[a-zA-Z0-9_.-]{1,80}")){message("Invalid QA audio");writeQA(false);return;}onActivityResult(402,RESULT_OK,new Intent().setData(android.net.Uri.fromFile(new File(getFilesDir(),name))));}
  else{qaRemaining=Math.max(1,Math.min(4,getIntent().getIntExtra("speech_repeat",1)));input.setText(getIntent().hasExtra("speech_text")?getIntent().getStringExtra("speech_text"):"At nine thirty, please check the train ticket and call the station.");String preset=getIntent().getStringExtra("speech_voice");for(int i=0;i<voice.getCount();i++)if(voice.getItemAtPosition(i).equals(preset))voice.setSelection(i);primary();int delay=getIntent().getIntExtra("speech_cancel_ms",0);if(delay>0)ui.postDelayed(()->cancel(false),delay);}
 }
 private void primary(){
  if(recording){recording=false;AudioRecord r=recorder;if(r!=null)try{r.stop();}catch(Exception ignored){}run.setEnabled(false);message("正在结束录音并完成识别…");return;}
  if(busy)return;JSONObject m=selected();if(m==null)return;
  if(task.getSelectedItemPosition()==0){String text=input.getText().toString().trim(),preset=voice.getSelectedItem().toString();if(text.isEmpty()){message("请输入英文");return;}
    lastTtsReport=null;submit(()->{SpeechBridge.load();String identity=store.identity(m);if(!identity.equals(verifiedTtsIdentity)){store.requireReady(m);verifiedTtsIdentity=identity;}File path=store.child(m.getString("model_path"));JSONObject ref=store.reference(m,preset);boolean moss=m.optString("family").equals("moss_tts_nano");message("正在合成与播放…");
     boolean stream=!m.getString("family").equals("piper_tts")&&!m.getString("family").equals("kitten_tts")&&!(moss&&getIntent().getBooleanExtra("speech_offline",false));
     try(StreamingPlayer p=new StreamingPlayer(!getIntent().getBooleanExtra("speech_no_playback",false),text.codePointCount(0,text.length()))){player=p;File wav=new File(getFilesDir(),"speech-last.wav");JSONObject report=new JSONObject(SpeechBridge.synthesize(m.getString("family"),m.optBoolean("external_espeak")?getApplicationInfo().nativeLibraryDir+"/libespeak-ng.so":"",m.optBoolean("external_espeak")?store.prepareG2p(this).getPath():"",identity,path.getPath(),preset,text,stream,p,wav.getPath(),ref==null?"":ref.getString("local_path"),ref==null?"":ref.getString("reference_text"),new File(getCacheDir(),"moss-runtime").getPath(),moss?getIntent().getIntExtra("speech_threads",4):4));lastTtsReport=report;p.drain();report.put("playback",p.metrics()).put("voice",preset);if(BuildConfig.DEBUG&&getIntent().getBooleanExtra("speech_qa",false)){String id=getIntent().getStringExtra("speech_qa_id");if(id!=null&&id.matches("[a-zA-Z0-9_-]{1,64}")){File dir=new File(getFilesDir(),"qa");dir.mkdirs();String stem=id+"-r"+qaRuns.length();java.nio.file.Files.copy(wav.toPath(),new File(dir,stem+".wav").toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING);File trace=new File(wav.getPath()+".trace.log");if(trace.isFile())java.nio.file.Files.copy(trace.toPath(),new File(dir,stem+".trace.log").toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING);report.put("qa_audio",stem+".wav");}}if(!cancelled)getSharedPreferences("speech",MODE_PRIVATE).edit().putString("last_tts_audio",wav.getPath()).apply();if(!cancelled)message(String.format(Locale.ROOT,"完成 · %.2fs · 接口RTF %.3f · %s · %s",report.getDouble("audio_s"),report.getDouble("RTF"),stream?"原生流式":"整句合成",report.optBoolean("engine_reused")?"复用引擎":"首次构图"));}finally{player=null;}
   });
  }else{if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},401);else startRecording(m);}
 }
 @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){super.onRequestPermissionsResult(request,permissions,results);if(request==401){if(results.length>0&&results[0]==PackageManager.PERMISSION_GRANTED)startRecording(selected());else message("未授予录音权限；仍可导入WAV识别。");}}
 private void clearText(){finals.clear();partial.setLength(0);ui.post(()->result.setText(""));}
 private final SpeechBridge.TextSink sink=(text,endpoint,segment)->{if(endpoint!=0){if(!text.trim().isEmpty())finals.put(segment,text);partial.setLength(0);}else{partial.setLength(0);partial.append(text);}String value=String.join("\n",finals.values())+(partial.length()>0?"\n识别中："+partial:"");ui.post(()->{if(!destroyed)result.setText(value);});};
 private void startRecording(JSONObject model){if(model==null)return;submit(()->{
  SpeechBridge.load();File path=store.requireReady(model);SpeechBridge.openAsr(model.getString("family"),path.getPath());clearText();if(cancelled)return;
  int size=Math.max(6400,AudioRecord.getMinBufferSize(16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT));
  AudioRecord r=new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION,16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,size);recorder=r;
  if(r.getState()!=AudioRecord.STATE_INITIALIZED)throw new IOException("麦克风初始化失败");r.startRecording();recording=true;
  ui.post(()->{working(true);message("正在录音 · 最长60秒；再次点击结束识别");});
  short[] raw=new short[1600];float[] pcm=new float[1600];int frames=0;
  while(recording&&!cancelled&&frames<16000*60){int n=r.read(raw,0,Math.min(raw.length,16000*60-frames));if(n<0){if(recording)throw new IOException("录音读取失败 "+n);break;}if(n==0)continue;for(int i=0;i<n;i++)pcm[i]=raw[i]/32768f;SpeechBridge.accept(pcm,n,sink);frames+=n;}
  recording=false;try{r.stop();}catch(Exception ignored){}if(!cancelled&&frames>0){SpeechBridge.finish(sink);message(String.format(Locale.ROOT,"识别完成 · 输入 %.2fs",frames/16000.0));}else message(cancelled?"已取消":"未录到音频");
 });}
 private void cancel(boolean quiet){cancelled=true;recording=false;if(store!=null)store.cancel();try{SpeechBridge.cancel();}catch(Throwable ignored){}AudioRecord r=recorder;if(r!=null)try{r.stop();}catch(Exception ignored){}StreamingPlayer p=player;if(p!=null)p.requestStop();if(replay!=null)try{replay.stop();}catch(Exception ignored){}if(!quiet)message("正在停止…");}
 @Override public void onBackPressed(){if(busy){leaveAfterStop=true;cancel(false);}else super.onBackPressed();}
 @Override protected void onPause(){super.onPause();foreground=false;releaseCache();if(busy)cancel(true);if(replay!=null)try{replay.pause();}catch(Exception ignored){}}
 @Override protected void onDestroy(){destroyed=true;cancel(true);if(replay!=null)replay.release();super.onDestroy();}
 @Override protected void onActivityResult(int request,int code,Intent data){super.onActivityResult(request,code,data);if(request==403&&code==RESULT_OK&&data!=null){JSONObject m=selected();android.net.Uri uri=data.getData();submit(()->{try(InputStream in=getContentResolver().openInputStream(uri)){store.importZip(in,m);}});}else if(request==402&&code==RESULT_OK&&data!=null){JSONObject m=selected();android.net.Uri uri=data.getData();submit(()->{SpeechBridge.load();File path=store.requireReady(m);float[] pcm;try(InputStream in=getContentResolver().openInputStream(uri)){pcm=wav(in);}clearText();SpeechBridge.openAsr(m.getString("family"),path.getPath());for(int i=0;i<pcm.length&&!cancelled;i+=1600){float[] chunk=Arrays.copyOfRange(pcm,i,Math.min(i+1600,pcm.length));SpeechBridge.accept(chunk,chunk.length,sink);}if(!cancelled){SpeechBridge.finish(sink);message(String.format(Locale.ROOT,"识别完成 · %.2fs",pcm.length/16000.0));}});}}
 private static byte[] read(InputStream in,int n)throws IOException{byte[] b=new byte[n];int p=0,k;while(p<n&&(k=in.read(b,p,n-p))>0)p+=k;if(p!=n)throw new EOFException("WAV不完整");return b;}
 private static int le(byte[]b,int at,int count){int value=0;for(int i=0;i<count;i++)value|=(b[at+i]&255)<<(8*i);return value;}
 private static float[] wav(InputStream in)throws IOException{
  byte[] header=read(in,12);if(!new String(header,0,4,java.nio.charset.StandardCharsets.US_ASCII).equals("RIFF")||!new String(header,8,4,java.nio.charset.StandardCharsets.US_ASCII).equals("WAVE"))throw new IOException("请选择16kHz单声道PCM16或F32 WAV");
  int format=0,bits=0,channels=0,rate=0;long scanned=12;
  while(scanned<64*1024*1024){byte[] chunk=read(in,8);int size=le(chunk,4,4);if(size<0||size>64*1024*1024)throw new IOException("WAV块过大");scanned+=size+8L;String kind=new String(chunk,0,4,java.nio.charset.StandardCharsets.US_ASCII);
   if(kind.equals("fmt ")){if(size<16||size>1024)throw new IOException("WAV格式无效");byte[] f=read(in,size);format=le(f,0,2);bits=le(f,14,2);channels=le(f,2,2);rate=le(f,4,4);if(channels<1||channels>2||rate<8000||rate>192000||!((format==1&&bits==16)||(format==3&&bits==32)))throw new IOException("需要8–192kHz单/双声道PCM16或F32 WAV");}
   else if(kind.equals("data")){int width=bits/8;if(width==0||channels==0||size<=0||size>32*1024*1024||size%(width*channels)!=0)throw new IOException("WAV为空、格式错误或超过32MB");int frames=size/(width*channels);if((double)frames/rate>60)throw new IOException("请选择最多60秒的WAV");byte[] data=read(in,size);float[] output=new float[(int)((long)frames*16000/rate)];
    for(int i=0;i<output.length;i++){double position=(double)i*rate/16000;int j=(int)position,k=Math.min(j+1,frames-1);double sum=0;for(int ch=0;ch<channels;ch++){int left=(j*channels+ch)*width,right=(k*channels+ch)*width;float x=format==1?(short)le(data,left,2)/32768f:Float.intBitsToFloat(le(data,left,4)),y=format==1?(short)le(data,right,2)/32768f:Float.intBitsToFloat(le(data,right,4));if(!Float.isFinite(x)||!Float.isFinite(y))throw new IOException("Nonfinite audio");sum+=x+(y-x)*(position-j);}output[i]=(float)(sum/channels);}return output;}

   else{int left=size;byte[] temp=new byte[8192];while(left>0){int n=in.read(temp,0,Math.min(left,temp.length));if(n<0)throw new EOFException();left-=n;}}
   if((size&1)!=0)read(in,1);
  }throw new IOException("WAV头过大");
 }
}
