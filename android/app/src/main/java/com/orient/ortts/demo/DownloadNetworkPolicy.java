package com.orient.ortts.demo;
import android.app.*;
import android.content.*;
import android.net.*;
import java.io.IOException;
import java.net.*;
import java.util.function.Consumer;

/** Consent belongs to one foreground job, not a persistent preference. */
final class DownloadNetworkPolicy {
 interface Job { void run()throws Exception; }
 private static final ThreadLocal<Boolean> allowed=ThreadLocal.withInitial(()->false);
 static boolean needsConsent(Context context){try{ConnectivityManager c=(ConnectivityManager)context.getSystemService(Context.CONNECTIVITY_SERVICE);NetworkCapabilities n=c==null?null:c.getNetworkCapabilities(c.getActiveNetwork());return n==null||n.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)||c.isActiveNetworkMetered()||!n.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED);}catch(Exception e){return true;}}
 static void confirm(Activity activity,Consumer<Boolean> start){if(!needsConsent(activity)){start.accept(false);return;}new AlertDialog.Builder(activity).setTitle("允许使用移动数据下载？").setMessage("当前为移动数据、计费网络，或无法确认网络类型。模型可能需要数百 MB 至数 GB。默认仅使用非计费网络，本次允许后可能消耗较多流量。").setNegativeButton("取消，等 Wi-Fi",null).setPositiveButton("本次允许",(d,w)->start.accept(true)).show();}
 static void run(boolean consent,Job job)throws Exception{boolean previous=allowed.get();allowed.set(consent);try{job.run();}finally{allowed.set(previous);}}
 static URLConnection open(Context context,URL url)throws IOException{
  if(allowed.get())return url.openConnection();
  check(context);ConnectivityManager manager=(ConnectivityManager)context.getSystemService(Context.CONNECTIVITY_SERVICE);Network network=manager==null?null:manager.getActiveNetwork();NetworkCapabilities caps=network==null?null:manager.getNetworkCapabilities(network);
  if(caps==null||caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)||!caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED))throw new IOException("仅允许非计费网络下载，请连接 Wi-Fi 或重新确认移动数据。");
  // Bind this TCP connection to the approved network so losing Wi-Fi cannot fall back to cellular.
  return network.openConnection(url);
 }
 static void check(Context context)throws IOException{if(!allowed.get()&&needsConsent(context))throw new IOException("下载已停止：当前为移动数据或计费网络。请连接 Wi-Fi，或点击下载按钮确认本次使用移动数据。");}
}
