package com.orient.ortts.demo;
final class ErrorMessages {
 static String display(String raw) {
  if(raw==null||raw.trim().isEmpty())return "操作失败，请检查模型与输入。";
  if(raw.contains("generated-only Qwen16 codes"))return "当前声学模型不支持参考文本复刻，请使用参考音色模式或内置音色。";
  if(raw.contains("HTTP 404"))return "下载地址暂不可用，请导入本地权重包或更换下载地址。";
  return "操作失败："+raw;
 }
}
