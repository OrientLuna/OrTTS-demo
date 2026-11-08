package com.orient.ortts.demo;
import android.app.*;
import android.content.*;
import android.widget.*;
import org.json.*;
import java.util.*;

final class DownloadSources {
 static final String[] MODES={"auto","hf","hfmirror","modelscope"};
 static final String[] NAMES={"自动","Hugging Face","HF Mirror","ModelScope"};
 static android.content.SharedPreferences prefs(Context c){return c.getSharedPreferences("download_channels",0);}
 static String mode(Context c){return prefs(c).getString("mode","auto");}
 static String label(String c){for(int i=0;i<MODES.length;i++)if(MODES[i].equals(c))return NAMES[i];return "原地址";}
 static List<String> candidates(Context c,String primary,JSONArray extra)throws Exception{
  List<String>a=new ArrayList<>();if(extra!=null)for(int i=0;i<extra.length();i++)a.add(extra.getString(i));return DownloadRoute.candidates(primary,a,mode(c),prefs(c).getString("last_success",""));
 }
 static void rejected(String url){android.util.Log.i("OrTTSDownload",label(DownloadRoute.channel(url))+": rejected; trying next verified source");}
 static void success(Context c,String url){android.util.Log.i("OrTTSDownload",label(DownloadRoute.channel(url))+": SHA256 verified");prefs(c).edit().putString("last_success",DownloadRoute.channel(url)).apply();}
 static void addSelector(Activity a,LinearLayout box){Button b=new Button(a);b.setText("下载通道："+label(mode(a)));b.setOnClickListener(v->{if(MainActivity.busy.get()){Toast.makeText(a,"请等待当前任务完成",Toast.LENGTH_SHORT).show();return;}int index=Arrays.asList(MODES).indexOf(mode(a));new AlertDialog.Builder(a).setTitle("下载通道").setSingleChoiceItems(NAMES,index,(dialog,n)->{prefs(a).edit().putString("mode",MODES[n]).apply();b.setText("下载通道："+NAMES[n]);dialog.dismiss();}).setNegativeButton("取消",null).show();});box.addView(b);}
}
