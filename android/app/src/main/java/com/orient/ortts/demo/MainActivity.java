package com.orient.ortts.demo;
import android.app.*;
import android.content.*;
import android.net.Uri;
import android.os.*;
import android.view.*;
import android.widget.*;
import android.media.MediaPlayer;
import org.json.*;
import java.io.*;
import java.nio.file.Files;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class MainActivity extends Activity {
 private static final ExecutorService worker=Executors.newSingleThreadExecutor();private static final AtomicBoolean busy=new AtomicBoolean();
 private final Handler ui=new Handler(Looper.getMainLooper());private LinearLayout box;private TextView status;private Spinner variant,voice;private EditText text,url;private CheckBox streaming;private MediaPlayer replay;
 private ModelManager manager;private File latest;
 private interface Job {void run()throws Exception;}
 private void message(String s){ui.post(()->{if(status!=null)status.setText(s);});}
 private void button(String name,Job job){Button b=new Button(this);b.setText(name);b.setOnClickListener(v->submit(job,null));box.addView(b);}
 private void submit(Job job,String testId){if(!busy.compareAndSet(false,true)){message("请等待当前任务完成");return;}getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);for(int k=0;k<box.getChildCount();k++)box.getChildAt(k).setEnabled(false);worker.execute(()->{JSONObject result=new JSONObject();try{job.run();result.put("ok",true);}catch(Exception e){String msg=e.getMessage();message(msg!=null&&msg.contains("HTTP 404")?"下载地址暂不可用，请导入本地权重包或更换下载地址。":("操作失败："+msg));try{result.put("ok",false).put("error",String.valueOf(msg));}catch(Exception ignored){}}finally{if(testId!=null){try{File d=new File(getFilesDir(),"qa");d.mkdirs();Files.write(new File(d,testId+".json").toPath(),result.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));}catch(Exception ignored){}}busy.set(false);ui.post(()->{getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);for(int k=0;k<box.getChildCount();k++)box.getChildAt(k).setEnabled(true);});}});}
 private Spinner select(String[] values){Spinner s=new Spinner(this);s.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,values));box.addView(s);return s;}
 private EditText input(String hint,String value){EditText e=new EditText(this);e.setHint(hint);e.setText(value);box.addView(e);return e;}
 @Override public void onCreate(Bundle b){super.onCreate(b);ScrollView sc=new ScrollView(this);box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(28,28,28,28);sc.addView(box);setContentView(sc);TextView title=new TextView(this);title.setText("OrTTS");title.setTextSize(28);box.addView(title);variant=select(new String[]{"P3","P5"});voice=select(new String[]{"female","male"});text=input("输入要朗读的文字","你好，很高兴认识你。");TextView modelHint=new TextView(this);modelHint.setText("P3 速度优先 · P5 标准版");box.addView(modelHint);streaming=new CheckBox(this);streaming.setText("边生成边播放");streaming.setChecked(true);box.addView(streaming);manager=new ModelManager(this,this::message);
  button("合成语音",()->synthesize(variant.getSelectedItem().toString(),voice.getSelectedItem().toString(),text.getText().toString(),streaming.isChecked(),null));
  button("播放上一条",()->{if(latest==null)throw new IOException("请先合成语音");ui.post(()->{try{if(replay!=null)replay.release();replay=new MediaPlayer();replay.setDataSource(latest.getPath());replay.prepare();replay.start();}catch(Exception e){message("播放失败："+e.getMessage());}});});
  String address="";try(InputStream in=getAssets().open("defaults.json")){ByteArrayOutputStream data=new ByteArrayOutputStream();byte[] buffer=new byte[4096];int count;while((count=in.read(buffer))!=-1)data.write(buffer,0,count);address=new JSONObject(new String(data.toByteArray(),java.nio.charset.StandardCharsets.UTF_8)).getString("manifest_url");}catch(Exception ignored){}
  address=getPreferences(0).getString("manifest_url",address);url=input("模型下载清单地址（可修改）",address);url.setSingleLine(false);url.setVisibility(View.GONE);button("更换下载地址",()->ui.post(()->url.setVisibility(url.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE)));
  button("下载所选模型权重",()->{NativeBridge.ensureLoaded();manager.download(url.getText().toString().trim(),variant.getSelectedItem().toString());NativeBridge.release();message("模型已准备好");});
  button("导入本地权重 ZIP",()->ui.post(()->{Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(i,100);}));
  try{if(manager.hasBundled())button("准备内置权重",()->{manager.importBundled();NativeBridge.release();message("模型已准备好");});}catch(Exception ignored){}
  button("释放模型",()->{NativeBridge.release();message("已释放运行内存");});status=new TextView(this);status.setTextIsSelectable(true);box.addView(status);message(manager.current()==null?"首次使用请下载所选模型，或导入本地包。P5约2.0GB，P3约2.2GB，共享文件只下载一次。":"模型已准备好");handleTest(getIntent());
 }
 @Override protected void onNewIntent(Intent i){super.onNewIntent(i);setIntent(i);handleTest(i);}
 @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request==100&&result==RESULT_OK&&data!=null){Uri uri=data.getData();submit(()->{manager.importUri(uri);NativeBridge.release();message("模型已准备好");},null);}}
 private void synthesize(String v,String s,String t,boolean stream,String runId)throws Exception{if(t.trim().isEmpty())throw new IOException("请输入文字");NativeBridge.ensureLoaded();File root=manager.current();if(!manager.ready(v)){message("正在准备所选模型…");root=manager.hasBundled()?manager.importBundled():manager.download(url.getText().toString().trim(),v);}message("正在合成与缓冲…");File outputs=new File(getFilesDir(),"outputs");outputs.mkdirs();File out=new File(outputs,runId==null?Long.toString(System.currentTimeMillis()):runId);if(out.exists())throw new IOException("输出已存在");out.mkdirs();JSONObject report;
  try(StreamingPlayer player=new StreamingPlayer(stream,t.codePointCount(0,t.length()))){String result=NativeBridge.run(root.getAbsolutePath(),v,s,t,4,20261029L,stream,player,out.getAbsolutePath(),ModelManager.sha(new File(root,"native/bridge/MANIFEST.json")));report=new JSONObject(result);player.drain();report.put("playback",player.metrics());}
  Files.write(new File(out,"report.json").toPath(),report.toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8));latest=new File(out,"sample.wav");message(String.format(Locale.ROOT,"合成完成 · %.2f 秒音频\n生成 RTF %.3f%s",report.getDouble("audio_s"),report.optDouble("generation_RTF",report.getDouble("RTF")),stream?String.format(Locale.ROOT," · 首块 %.0f ms",report.getDouble("first_pcm_ms")):""));if(!report.getString("EOS").equals("eos"))throw new IOException("生成未正常结束，结果已保留");
 }
 private void handleTest(Intent i){if(!BuildConfig.DEBUG||!i.getBooleanExtra("qa",false))return;String id=i.getStringExtra("qa_id");if(id==null||!id.matches("[a-zA-Z0-9_-]{1,80}"))return;String action=i.getStringExtra("qa_action");submit(()->{
  if("capabilities".equals(action)){NativeBridge.ensureLoaded();}
  else if("import".equals(action)){File zip=ModelManager.child(getFilesDir(),i.getStringExtra("zip"));manager.importZip(zip);message("模型已准备好");}
  else if("download".equals(action)){manager.download(i.getStringExtra("url"),i.getStringExtra("variant")==null?"P3":i.getStringExtra("variant"));NativeBridge.release();message("模型已准备好");}
  else if("bundled".equals(action)){manager.importBundled();NativeBridge.release();message("模型已准备好");}
  else if("fetch".equals(action)){File f=new File(getFilesDir(),"qa-download-"+id);manager.downloadFile(i.getStringExtra("url"),f,i.getLongExtra("bytes",-1),i.getStringExtra("sha"),"下载测试");}
  else if("synth".equals(action)){synthesize(i.getStringExtra("variant"),i.getStringExtra("voice"),i.getStringExtra("text"),i.getBooleanExtra("stream",true),id);}
  else if("release".equals(action)){NativeBridge.release();}
  else throw new IOException("unknown QA action");
 },id);}
 @Override protected void onPause(){super.onPause();if(url!=null)getPreferences(0).edit().putString("manifest_url",url.getText().toString().trim()).apply();}
 @Override protected void onDestroy(){if(replay!=null)replay.release();super.onDestroy();}
}
