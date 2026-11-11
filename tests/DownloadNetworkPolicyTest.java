package com.orient.ortts.demo;
import java.io.IOException;
/** Unknown network must fail closed; consent must never leak to the next worker job. */
public class DownloadNetworkPolicyTest {
 static void blocked()throws Exception{try{DownloadNetworkPolicy.check(null);throw new AssertionError("Unknown network allowed without consent");}catch(IOException expected){}}
 public static void main(String[]args)throws Exception{
  blocked();DownloadNetworkPolicy.run(true,()->DownloadNetworkPolicy.check(null));blocked();
  try{DownloadNetworkPolicy.run(true,()->{DownloadNetworkPolicy.check(null);throw new IOException("job failed");});}catch(IOException expected){}blocked();
  DownloadNetworkPolicy.run(true,()->{DownloadNetworkPolicy.run(false,DownloadNetworkPolicyTest::blocked);DownloadNetworkPolicy.check(null);});blocked();
  System.out.println("PASS: unknown network blocked, per-job permission, nesting and exception cleanup");
 }
}
