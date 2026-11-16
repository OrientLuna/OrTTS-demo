package com.orient.ortts.demo;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaPlayer;
import android.media.MediaRecorder;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.WindowManager;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.TreeMap;

/** Dedicated tab view for either third-party TTS or streaming/offline ASR. */
final class SpeechTabPanel {
 interface TransferHandler { void onSpeakText(String text); }
 interface TabLock { void setLocked(boolean locked); }

 final ScrollView root;
 private final Activity activity;
 private final boolean asr;
 private final TransferHandler transferHandler;
 private final TabLock tabLock;
 private final LinearLayout box;
 private Spinner model, voice;
 private EditText input;
 private TextView info, status, result;
 private Button run, download, importModel, importAudio, lastAudio, stop, creditsButton, replayButton, transferButton, releaseButton;
 private SpeechModels store;
 private final ArrayList<JSONObject> choices = new ArrayList<>();
 private final Handler ui = new Handler(Looper.getMainLooper());
 private final TreeMap<Long, String> finals = new TreeMap<>();
 private String verifiedTtsIdentity = "";
 private long cacheEpoch;
 private volatile boolean recording, cancelled, destroyed;
 private boolean busy;
 private volatile AudioRecord recorder;
 private volatile StreamingPlayer player;
 private MediaPlayer replay;
 private final StringBuilder partial = new StringBuilder();

 private interface Job { void run() throws Exception; }

 SpeechTabPanel(Activity activity, boolean asr, TransferHandler transferHandler, TabLock tabLock) {
  this.activity = activity;
  this.asr = asr;
  this.transferHandler = transferHandler;
  this.tabLock = tabLock;
  root = new ScrollView(activity);
  box = new LinearLayout(activity);
  box.setOrientation(LinearLayout.VERTICAL);
  int pad = (int) (16 * activity.getResources().getDisplayMetrics().density);
  box.setPadding(pad, pad, pad, pad);
  root.addView(box);

  TextView section = new TextView(activity);
  section.setText(asr ? "语音识别 · 中文 / 英语" : "其他语音合成 · 第三方开源模型");
  section.setTextSize(18);
  box.addView(section);

  model = new Spinner(activity);
  voice = new Spinner(activity);
  if (asr) {
   box.addView(model);
  } else {
   LinearLayout selection = row(model, voice);
   ((LinearLayout.LayoutParams) model.getLayoutParams()).weight = 2;
   box.addView(selection);
  }

  info = new TextView(activity);
  info.setTextIsSelectable(true);
  info.setTextSize(14);
  box.addView(info);

  download = makeButton("下载 / 检查所选模型", () -> {
   JSONObject m = selected();
   if (m != null && !busy) {
    DownloadNetworkPolicy.confirm(activity, allowed -> submit(() -> DownloadNetworkPolicy.run(allowed, () -> store.download(m))));
   }
  });
  importModel = makeButton("导入所选模型 ZIP", () -> {
   if (!busy) {
    activity.startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/zip").addCategory(Intent.CATEGORY_OPENABLE), asr ? 423 : 413);
   }
  });
  box.addView(row(download, importModel));

  if (!asr) {
   input = new EditText(activity);
   input.setMinLines(3);
   input.setText("Hello, welcome to local speech synthesis.");
   input.setHint("按音色语言输入；Kokoro 中文音色支持中文");
   box.addView(input);
  }

  run = makeButton(asr ? "开始录音识别" : "合成并播放", this::primary);
  run.setBackgroundTintList(ColorStateList.valueOf(0xff2365df));
  run.setTextColor(Color.WHITE);
  box.addView(run);

  if (asr) {
   importAudio = makeButton("导入 WAV 识别（最多60秒）", () -> {
    if (!busy) {
     Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("audio/*").addCategory(Intent.CATEGORY_OPENABLE);
     activity.startActivityForResult(i, 422);
    }
   });
   lastAudio = makeButton("识别上次合成", () -> {
    String path = activity.getSharedPreferences("speech", Activity.MODE_PRIVATE)
        .getString("last_tts_audio", new File(activity.getFilesDir(), "speech-last.wav").getPath());
    handleActivityResult(422, Activity.RESULT_OK, new Intent().setData(Uri.fromFile(new File(path))));
   });
   box.addView(row(importAudio, lastAudio));
  }

  status = new TextView(activity);
  status.setTextIsSelectable(true);
  status.setTextSize(14);
  box.addView(status);

  if (asr) {
   result = new TextView(activity);
   result.setTextIsSelectable(true);
   result.setTextSize(18);
   result.setMinHeight((int) (100 * activity.getResources().getDisplayMetrics().density));
   result.setHint("识别结果显示在这里");
   box.addView(result);
   transferButton = makeButton("用 OrTTS 朗读识别结果", () -> {
    if (busy) return;
    String spoken = String.join("，", finals.values()).trim();
    if (spoken.isEmpty()) {
     message("请先完成识别");
     return;
    }
    releaseCache();
    transferHandler.onSpeakText(spoken);
   });
   box.addView(transferButton);
  }

  stop = makeButton("取消当前任务", () -> cancel(false));
  if (!asr) {
   replayButton = makeButton("重播上次合成", () -> {
    if (busy) return;
    File file = new File(activity.getFilesDir(), "speech-last.wav");
    try {
     if (replay != null) replay.release();
     replay = new MediaPlayer();
     replay.setDataSource(file.getPath());
     replay.prepare();
     replay.start();
    } catch (Exception e) {
     message("暂无可播放音频");
    }
   });
   box.addView(row(stop, replayButton));
  } else {
   box.addView(stop);
  }

  releaseButton = makeButton("释放语音模型", () -> {
   if (!busy) {
    releaseCache();
    message("已释放语音模型");
   }
  });
  creditsButton = makeButton("模型许可与音色来源", this::credits);
  box.addView(row(releaseButton, creditsButton));
  DownloadSources.addSelector(activity, box);

  try {
   store = new SpeechModels(activity, this::message);
  } catch (Exception e) {
   message(e.getMessage());
   run.setEnabled(false);
   download.setEnabled(false);
   return;
  }

  model.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
   public void onNothingSelected(AdapterView<?> p) {}
   public void onItemSelected(AdapterView<?> p, View v, int position, long id) { updateInfo(); }
  });
  loadModels();
  message(asr ? "选择识别模型，再录音或导入 WAV 音频。" : "按所选模型和音色支持的语言输入文本，下载一次后可离线使用。");
 }

 private Button makeButton(String text, Runnable action) {
  Button b = new Button(activity);
  b.setText(text);
  b.setOnClickListener(v -> action.run());
  return b;
 }

 private LinearLayout row(View... views) {
  LinearLayout r = new LinearLayout(activity);
  r.setOrientation(LinearLayout.HORIZONTAL);
  for (View v : views) r.addView(v, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
  return r;
 }

 private void values(Spinner s, List<String> vals) {
  s.setAdapter(new ArrayAdapter<>(activity, android.R.layout.simple_spinner_dropdown_item, vals));
 }

 private JSONObject selected() {
  return choices.isEmpty() ? null : choices.get(Math.max(0, model.getSelectedItemPosition()));
 }

 private void message(String value) {
  ui.post(() -> { if (!destroyed) status.setText(value); });
 }

 private void working(boolean value) {
  busy = value;
  tabLock.setLocked(value);
  if (transferButton != null) transferButton.setEnabled(!value);
  if (releaseButton != null) releaseButton.setEnabled(!value);
  if (replayButton != null) replayButton.setEnabled(!value);
  model.setEnabled(!value);
  if (voice != null) voice.setEnabled(!value);
  if (input != null) input.setEnabled(!value);
  download.setEnabled(!value);
  importModel.setEnabled(!value);
  if (importAudio != null) importAudio.setEnabled(!value);
  if (lastAudio != null) lastAudio.setEnabled(!value);
  run.setEnabled(!value || recording);
  run.setText(recording ? "结束录音并识别" : (asr ? "开始录音识别" : "合成并播放"));
  stop.setEnabled(value);
 }

 private void submit(Job job) {
  if (busy || !MainActivity.busy.compareAndSet(false, true)) {
   message("请等待当前任务完成");
   return;
  }
  cacheEpoch++;
  cancelled = false;
  store.prepare();
  working(true);
  activity.getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
  MainActivity.worker.execute(() -> {
   boolean success = false;
   try {
    job.run();
    success = !cancelled;
   } catch (Exception e) {
    message(cancelled ? "已停止" : "操作失败：" + e.getMessage());
   } finally {
    try {
     if (success) SpeechBridge.endTask();
     else { SpeechBridge.close(); verifiedTtsIdentity = ""; }
    } catch (Throwable ignored) {}
    recording = false;
    AudioRecord r = recorder;
    recorder = null;
    if (r != null) {
     try { r.stop(); } catch (Exception ignored) {}
     r.release();
    }
    MainActivity.busy.set(false);
    ui.post(() -> {
     if (!destroyed) {
      working(false);
      activity.getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
     }
    });
   }
  });
 }

 void onTabActivated() {
  if (!busy) updateInfo();
 }

 void onTabDeactivated() {
  if (input != null) {
   android.view.inputmethod.InputMethodManager imm =
       (android.view.inputmethod.InputMethodManager) activity.getSystemService(Activity.INPUT_METHOD_SERVICE);
   if (imm != null) imm.hideSoftInputFromWindow(input.getWindowToken(), 0);
   input.clearFocus();
  }
  if (!busy) releaseCache();
 }

 void releaseCache() {
  cacheEpoch++;
  MainActivity.worker.execute(() -> {
   try { SpeechBridge.close(); } catch (Throwable ignored) {}
   verifiedTtsIdentity = "";
  });
 }

 private void loadModels() {
  choices.clear();
  ArrayList<String> names = new ArrayList<>();
  for (int i = 0; i < store.models.length(); i++) {
   JSONObject m = store.models.optJSONObject(i);
   if (m != null && m.optBoolean("demo_enabled") && asr == m.optString("task").equals("asr")) {
    choices.add(m);
    names.add(m.optString("display_name"));
   }
  }
  values(model, names);
  String remembered = activity.getPreferences(0).getString("model_" + (asr ? "asr" : "tts"), "");
  for (int i = 0; i < choices.size(); i++) {
   if (choices.get(i).optString("id").equals(remembered)) model.setSelection(i);
  }
  working(false);
  updateInfo();
 }

 private void updateInfo() {
  if (busy) return;
  releaseCache();
  JSONObject m = selected();
  if (m == null) return;
  activity.getPreferences(0).edit().putString("model_" + (asr ? "asr" : "tts"), m.optString("id")).apply();
  if (!asr) {
   JSONArray presets = m.optJSONArray("voice_sample");
   ArrayList<String> names = new ArrayList<>();
   if (presets != null) for (int i = 0; i < presets.length(); i++) names.add(presets.optString(i));
   if (names.isEmpty()) names.add("默认");
   values(voice, names);
  }
  long bytes = 0;
  JSONArray assets = m.optJSONArray("assets");
  if (assets != null) for (int i = 0; i < assets.length(); i++) bytes += assets.optJSONObject(i).optLong("bytes");
  JSONObject license = m.optJSONObject("license_review");
  String family = m.optString("family");
  String detail = family.equals("moss_tts_nano") ? "中文 / English · female / male · 48kHz立体声 · 流式合成"
      : family.equals("zipformer_bilingual") ? "中英及混说 · 增量流式实验档 · 质量筛查未达标，暂不推荐"
      : family.equals("moonshine_asr") ? "英文增量识别 · 结果会修订"
      : m.optString("task").equals("asr") ? "多语言离线识别 · 中文已过本批筛查；英语及混说仍有错误 · 无情绪标签输出"
      : "按模型和音色语言输入 · Piper/Kitten 离线合成";
  if (family.equals("qwen3_asr")) detail = "高内存离线可选 · 原28层INT8 · 按句返回，不是实时partial\n中英及混说仍需核对；非低配认证 · 本地ZIP导入，不自动下载";
  if (family.equals("streaming_paraformer")) detail = "Paraformer · 中英增量流式 · partial会修订\n英语及混说质量筛查未达标 · 手动结束或分段上限，无自动静音端点";
  download.setText(m.optBoolean("local_only") ? "检查本地模型" : "下载 / 检查所选模型");
  info.setText(detail + String.format(Locale.ROOT, "\n模型约 %.1f MB · 大小及SHA256校验", bytes / 1e6)
      + "\n许可：" + (license != null ? license.optString("weights_license") : ""));
 }

 private String mossSourceNotice() {
  try (InputStream in = activity.getAssets().open("licenses/MOSS-SOURCES.txt")) {
   ByteArrayOutputStream b = new ByteArrayOutputStream();
   byte[] data = new byte[4096];
   int n;
   while ((n = in.read(data)) != -1) {
    if (b.size() + n > 32768) throw new IOException("来源文本过大");
    b.write(data, 0, n);
   }
   return "\n\n" + b.toString("UTF-8");
  } catch (Exception ex) {
   return "\n来源文本读取失败：" + ex.getMessage();
  }
 }

 private void credits() {
  JSONObject m = selected();
  if (m == null) return;
  JSONObject license = m.optJSONObject("license_review");
  StringBuilder text = new StringBuilder(license.optString("weights_license")).append("\n").append(license.optString("source"));
  text.append("\n\neSpeak NG 1.52.0: GPL-3.0-or-later\n应用源码与构建说明：https://github.com/OrientLuna/OrTTS-demo\n模型与音色许可另行适用。");
  JSONArray voices = m.optJSONArray("voice_origins");
  if (voices != null) {
   for (int i = 0; i < voices.length(); i++) {
    JSONObject v = voices.optJSONObject(i);
    text.append("\n\n").append(v.optString("voice")).append(" · ").append(v.optString("license")).append("\n").append(v.optString("source"));
   }
   text.append("\n音色音频已转换为模型嵌入；模型由Kyutai提供。");
  }
  if (m.optString("family").equals("moss_tts_nano")) {
   text.append(mossSourceNotice());
   text.append("\n\n参考音色：OrTTS female / male。\n");
   try (InputStream in = activity.getAssets().open(license.getString("license_asset"))) {
    ByteArrayOutputStream b = new ByteArrayOutputStream();
    byte[] chunk = new byte[8192];
    int n;
    while ((n = in.read(chunk)) != -1) b.write(chunk, 0, n);
    text.append(b.toString("UTF-8"));
   } catch (Exception ex) {
    text.append("许可文本读取失败：").append(ex.getMessage());
   }
  }
  new AlertDialog.Builder(activity).setTitle("模型与音色来源").setMessage(text)
      .setNegativeButton("关闭", null)
      .setPositiveButton("打开模型来源", (d, w) -> activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(license.optString("source")))))
      .show();
 }

 private void primary() {
  if (recording) {
   recording = false;
   AudioRecord r = recorder;
   if (r != null) try { r.stop(); } catch (Exception ignored) {}
   run.setEnabled(false);
   message("正在结束录音并完成识别…");
   return;
  }
  if (busy) return;
  JSONObject m = selected();
  if (m == null) return;
  if (!asr) {
   String text = input.getText().toString().trim();
   String preset = voice.getSelectedItem().toString();
   if (text.isEmpty()) { message("请输入文本"); return; }
   submit(() -> {
    SpeechBridge.load();
    String identity = store.identity(m);
    if (!identity.equals(verifiedTtsIdentity)) {
     store.requireReady(m);
     verifiedTtsIdentity = identity;
    }
    File path = store.child(m.getString("model_path"));
    JSONObject ref = store.reference(m, preset);
    boolean moss = m.optString("family").equals("moss_tts_nano");
    message("正在合成与播放…");
    boolean stream = !m.getString("family").equals("piper_tts") && !m.getString("family").equals("kitten_tts");
    try (StreamingPlayer p = new StreamingPlayer(true, text.codePointCount(0, text.length()))) {
     player = p;
     File wav = new File(activity.getFilesDir(), "speech-last.wav");
     JSONObject report = new JSONObject(SpeechBridge.synthesize(
         m.getString("family"),
         m.optBoolean("external_espeak") ? activity.getApplicationInfo().nativeLibraryDir + "/libespeak-ng.so" : "",
         m.optBoolean("external_espeak") ? store.prepareG2p(activity).getPath() : "",
         identity, path.getPath(), preset, text, stream, p, wav.getPath(),
         ref == null ? "" : ref.getString("local_path"),
         ref == null ? "" : ref.getString("reference_text"),
         new File(activity.getCacheDir(), "moss-runtime").getPath(), 4));
     p.drain();
     if (!cancelled) {
      activity.getSharedPreferences("speech", Activity.MODE_PRIVATE).edit().putString("last_tts_audio", wav.getPath()).apply();
      message(String.format(Locale.ROOT, "完成 · %.2fs · 接口RTF %.3f · %s · %s",
          report.getDouble("audio_s"), report.getDouble("RTF"),
          stream ? "原生流式" : "整句合成",
          report.optBoolean("engine_reused") ? "复用引擎" : "首次构图"));
     }
    } finally {
     player = null;
    }
   });
  } else {
   if (activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
    activity.requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 401);
   } else {
    startRecording(m);
   }
  }
 }

 void handlePermissionResult(int request, int[] results) {
  if (asr && request == 401) {
   if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) startRecording(selected());
   else message("未授予录音权限；仍可导入WAV识别。");
  }
 }

 private void clearText() {
  finals.clear();
  partial.setLength(0);
  ui.post(() -> { if (result != null) result.setText(""); });
 }

 private final SpeechBridge.TextSink sink = (text, endpoint, segment) -> {
  if (endpoint != 0) {
   if (!text.trim().isEmpty()) finals.put(segment, text);
   partial.setLength(0);
  } else {
   partial.setLength(0);
   partial.append(text);
  }
  String value = String.join("\n", finals.values()) + (partial.length() > 0 ? "\n识别中：" + partial : "");
  ui.post(() -> { if (!destroyed && result != null) result.setText(value); });
 };

 private void startRecording(JSONObject model) {
  if (model == null) return;
  submit(() -> {
   SpeechBridge.load();
   File path = store.requireReady(model);
   SpeechBridge.openAsrProfile(model.getString("family"), path.getPath(), model.optString("decoder_profile", "headslice-compat"));
   clearText();
   if (cancelled) return;
   int size = Math.max(6400, AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT));
   AudioRecord r = new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, 16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, size);
   recorder = r;
   if (r.getState() != AudioRecord.STATE_INITIALIZED) throw new IOException("麦克风初始化失败");
   r.startRecording();
   recording = true;
   ui.post(() -> { working(true); message("正在录音 · 最长60秒；再次点击结束识别"); });
   short[] raw = new short[1600];
   float[] pcm = new float[1600];
   int frames = 0;
   while (recording && !cancelled && frames < 16000 * 60) {
    int n = r.read(raw, 0, Math.min(raw.length, 16000 * 60 - frames));
    if (n < 0) { if (recording) throw new IOException("录音读取失败 " + n); break; }
    if (n == 0) continue;
    for (int i = 0; i < n; i++) pcm[i] = raw[i] / 32768f;
    SpeechBridge.accept(pcm, n, sink);
    frames += n;
   }
   recording = false;
   try { r.stop(); } catch (Exception ignored) {}
   if (!cancelled && frames > 0) {
    SpeechBridge.finish(sink);
    message(String.format(Locale.ROOT, "识别完成 · 输入 %.2fs", frames / 16000.0));
   } else {
    message(cancelled ? "已取消" : "未录到音频");
   }
  });
 }

 boolean handleActivityResult(int request, int code, Intent data) {
  int zipReq = asr ? 423 : 413;
  if (request == zipReq) {
   if (code == Activity.RESULT_OK && data != null) {
    JSONObject m = selected();
    Uri uri = data.getData();
    submit(() -> { try (InputStream in = activity.getContentResolver().openInputStream(uri)) { store.importZip(in, m); } });
   }
   return true;
  }
  if (asr && request == 422) {
   if (code == Activity.RESULT_OK && data != null) {
    JSONObject m = selected();
    Uri uri = data.getData();
    submit(() -> {
     SpeechBridge.load();
     File path = store.requireReady(m);
     float[] pcm;
     try (InputStream in = activity.getContentResolver().openInputStream(uri)) { pcm = wav(in); }
     clearText();
     SpeechBridge.openAsrProfile(m.getString("family"), path.getPath(), m.optString("decoder_profile", "headslice-compat"));
     for (int i = 0; i < pcm.length && !cancelled; i += 1600) {
      float[] chunk = Arrays.copyOfRange(pcm, i, Math.min(i + 1600, pcm.length));
      SpeechBridge.accept(chunk, chunk.length, sink);
     }
     if (!cancelled) {
      SpeechBridge.finish(sink);
      message(String.format(Locale.ROOT, "识别完成 · %.2fs", pcm.length / 16000.0));
     }
    });
   }
   return true;
  }
  return false;
 }

 void cancel(boolean quiet) {
  cancelled = true;
  recording = false;
  if (store != null) store.cancel();
  try { SpeechBridge.cancel(); } catch (Throwable ignored) {}
  AudioRecord r = recorder;
  if (r != null) try { r.stop(); } catch (Exception ignored) {}
  StreamingPlayer p = player;
  if (p != null) p.requestStop();
  if (replay != null) try { replay.stop(); } catch (Exception ignored) {}
  if (!quiet) message("正在停止…");
 }

 void onPause() {
  releaseCache();
  if (busy) cancel(true);
  if (replay != null) try { replay.pause(); } catch (Exception ignored) {}
 }

 void onDestroy() {
  destroyed = true;
  cancel(true);
  if (replay != null) replay.release();
 }

 private static byte[] read(InputStream in, int n) throws IOException {
  byte[] b = new byte[n];
  int p = 0, k;
  while (p < n && (k = in.read(b, p, n - p)) > 0) p += k;
  if (p != n) throw new EOFException("WAV不完整");
  return b;
 }

 private static int le(byte[] b, int at, int count) {
  int value = 0;
  for (int i = 0; i < count; i++) value |= (b[at + i] & 255) << (8 * i);
  return value;
 }

 private static float[] wav(InputStream in) throws IOException {
  byte[] header = read(in, 12);
  if (!new String(header, 0, 4, java.nio.charset.StandardCharsets.US_ASCII).equals("RIFF")
      || !new String(header, 8, 4, java.nio.charset.StandardCharsets.US_ASCII).equals("WAVE")) {
   throw new IOException("请选择16kHz单声道PCM16或F32 WAV");
  }
  int format = 0, bits = 0, channels = 0, rate = 0;
  long scanned = 12;
  while (scanned < 64 * 1024 * 1024) {
   byte[] chunk = read(in, 8);
   int size = le(chunk, 4, 4);
   if (size < 0 || size > 64 * 1024 * 1024) throw new IOException("WAV块过大");
   scanned += size + 8L;
   String kind = new String(chunk, 0, 4, java.nio.charset.StandardCharsets.US_ASCII);
   if (kind.equals("fmt ")) {
    if (size < 16 || size > 1024) throw new IOException("WAV格式无效");
    byte[] f = read(in, size);
    format = le(f, 0, 2);
    bits = le(f, 14, 2);
    channels = le(f, 2, 2);
    rate = le(f, 4, 4);
    if (channels < 1 || channels > 2 || rate < 8000 || rate > 192000
        || !((format == 1 && bits == 16) || (format == 3 && bits == 32))) {
     throw new IOException("需要8–192kHz单/双声道PCM16或F32 WAV");
    }
   } else if (kind.equals("data")) {
    int width = bits / 8;
    if (width == 0 || channels == 0 || size <= 0 || size > 32 * 1024 * 1024 || size % (width * channels) != 0) {
     throw new IOException("WAV为空、格式错误或超过32MB");
    }
    int frames = size / (width * channels);
    if ((double) frames / rate > 60) throw new IOException("请选择最多60秒的WAV");
    byte[] data = read(in, size);
    float[] output = new float[(int) ((long) frames * 16000 / rate)];
    for (int i = 0; i < output.length; i++) {
     double position = (double) i * rate / 16000;
     int j = (int) position, k = Math.min(j + 1, frames - 1);
     double sum = 0;
     for (int ch = 0; ch < channels; ch++) {
      int left = (j * channels + ch) * width, right = (k * channels + ch) * width;
      float x = format == 1 ? (short) le(data, left, 2) / 32768f : Float.intBitsToFloat(le(data, left, 4));
      float y = format == 1 ? (short) le(data, right, 2) / 32768f : Float.intBitsToFloat(le(data, right, 4));
      if (!Float.isFinite(x) || !Float.isFinite(y)) throw new IOException("Nonfinite audio");
      sum += x + (y - x) * (position - j);
     }
     output[i] = (float) (sum / channels);
    }
    return output;
   } else {
    int left = size;
    byte[] temp = new byte[8192];
    while (left > 0) {
     int n = in.read(temp, 0, Math.min(left, temp.length));
     if (n < 0) throw new EOFException();
     left -= n;
    }
   }
   if ((size & 1) != 0) read(in, 1);
  }
  throw new IOException("WAV头过大");
 }
}
