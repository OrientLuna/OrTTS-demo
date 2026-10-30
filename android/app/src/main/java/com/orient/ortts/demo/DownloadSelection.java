package com.orient.ortts.demo;
import java.util.*;
import java.util.regex.Pattern;
/** Component selection; P3 adds a predictor to the common P5-capable backbone. */
final class DownloadSelection {
 static boolean matches(String path,String glob){StringBuilder r=new StringBuilder("^");for(int i=0;i<glob.length();i++){char c=glob.charAt(i);if(c=='*'){if(i+1<glob.length()&&glob.charAt(i+1)=='*'){r.append(".*");i++;}else r.append("[^/]*");}else r.append(Pattern.quote(String.valueOf(c)));}return path.matches(r.append('$').toString());}
 static LinkedHashSet<String> select(Collection<String> paths,Map<String,List<String>> rules,String variant){if(!variant.equals("P3")&&!variant.equals("P5"))throw new IllegalArgumentException("Unknown variant");LinkedHashSet<String> out=new LinkedHashSet<>();List<String> groups=new ArrayList<>(Arrays.asList("common","P5"));if(variant.equals("P3"))groups.add("P3");for(String group:groups){List<String> patterns=rules.get(group);if(patterns==null)throw new IllegalArgumentException("Missing download group "+group);for(String path:paths)for(String glob:patterns)if(matches(path,glob)){out.add(path);break;}}if(out.isEmpty())throw new IllegalArgumentException("Empty model group");return out;}
}
