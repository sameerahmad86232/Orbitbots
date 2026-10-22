package in.orbitai.mobile;
import android.content.Context;import org.json.*;import java.net.*;import java.io.*;import java.nio.charset.StandardCharsets;
final class Computer {
 static String base(Context c)throws Exception{return Store.get(c,"computerBase","");}
 static String tokenSlot(String base)throws Exception{return "computer:"+Provider.slot(new JSONObject().put("type","ollama").put("base",base));}
 static void validate(String base)throws Exception{Provider.validate(new JSONObject().put("type","ollama").put("base",base));}
 static Object call(Context c,String path,String method,String body,String task)throws Exception{
  if(!path.matches("/(status|screen|jobs|jobs/[a-f0-9]{32}/cancel|actions|actions/[a-f0-9]{32}(/review)?|audit|knowledge|routines|routines/[a-f0-9]{32}|inbox)(\\?.*)?"))throw new IOException("Unsupported computer API path");
  if(!method.matches("GET|POST|DELETE"))throw new IOException("Unsupported method");String base=base(c);if(base.isEmpty())throw new IOException("Connect a computer server in Settings first");validate(base);String token=Store.get(c,tokenSlot(base),"");if(token.isEmpty())throw new IOException("Computer access token is missing");
  HttpURLConnection conn=(HttpURLConnection)new URL(base+path).openConnection();conn.setInstanceFollowRedirects(false);conn.setConnectTimeout(12000);conn.setReadTimeout(60000);conn.setRequestMethod(method);conn.setRequestProperty("Authorization","Bearer "+token);conn.setRequestProperty("Content-Type","application/json");if(task!=null)AgentService.connections.put(task,conn);
  try{if(method.equals("POST")){conn.setDoOutput(true);try(OutputStream o=conn.getOutputStream()){o.write(body.getBytes(StandardCharsets.UTF_8));}}int status=conn.getResponseCode();if(status<200||status>=300)throw new IOException("Computer HTTP "+status+". Check connection, access token, approval status and configured services.");try(InputStream in=conn.getInputStream()){ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1){out.write(b,0,n);if(out.size()>4000000)throw new IOException("Computer response too large");}if(path.equals("/screen"))return "data:image/jpeg;base64,"+android.util.Base64.encodeToString(out.toByteArray(),android.util.Base64.NO_WRAP);return new JSONObject(out.toString("UTF-8"));}}
  finally{if(task!=null)AgentService.connections.remove(task,conn);conn.disconnect();}
 }
}
