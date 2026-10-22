package in.orbitai.mobile;
import org.json.*;import com.sun.net.httpserver.*;import java.net.*;import java.nio.charset.StandardCharsets;import java.util.concurrent.atomic.AtomicReference;import java.io.*;
public class ProviderContractTest {
 static void check(boolean ok,String what){if(!ok)throw new AssertionError(what);}
 static void rejects(JSONObject c)throws Exception{try{Provider.validate(c);throw new AssertionError("Expected rejection: "+c);}catch(IOException expected){}}
 public static void main(String[] args)throws Exception{
  AtomicReference<JSONObject> last=new AtomicReference<>();AtomicReference<String> auth=new AtomicReference<>();HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
  server.createContext("/v1/chat/completions",e->{last.set(new JSONObject(new String(e.getRequestBody().readAllBytes(),StandardCharsets.UTF_8)));auth.set(e.getRequestHeaders().getFirst("Authorization"));byte[] out="{\"choices\":[{\"finish_reason\":\"tool_calls\",\"message\":{\"content\":null,\"tool_calls\":[{\"id\":\"a\",\"function\":{\"name\":\"list_files\",\"arguments\":\"{}\"}}]}}],\"usage\":{\"prompt_tokens\":7,\"completion_tokens\":2}}".getBytes(StandardCharsets.UTF_8);e.sendResponseHeaders(200,out.length);e.getResponseBody().write(out);e.close();});
  server.createContext("/v1/models",e->{byte[] out="{\"data\":[{\"id\":\"local-test\"}]}".getBytes();e.sendResponseHeaders(200,out.length);e.getResponseBody().write(out);e.close();});server.start();
  try{JSONObject cfg=new JSONObject().put("type","ollama").put("base","http://127.0.0.1:"+server.getAddress().getPort()+"/v1");Provider.validate(cfg);
   check(new JSONObject(Provider.call(cfg,"/models","GET","","",null)).getJSONArray("data").length()==1,"Model discovery");
   JSONObject p=new JSONObject().put("model","local-test").put("instructions","Do work").put("max_output_tokens",256).put("tools",new JSONArray().put(new JSONObject().put("type","function").put("name","list_files").put("description","List").put("parameters",new JSONObject().put("type","object"))));
   JSONArray input=new JSONArray().put(new JSONObject().put("role","user").put("content",new JSONArray().put(new JSONObject().put("type","input_text").put("text","Hello"))));
   for(String id:new String[]{"first","second"})input.put(new JSONObject().put("type","function_call").put("call_id",id).put("name","list_files").put("arguments","{}"));
   for(String id:new String[]{"first","second"})input.put(new JSONObject().put("type","function_call_output").put("call_id",id).put("output","[]"));p.put("input",input);
   JSONObject out=Provider.request(cfg,p,"test-key",null);JSONArray messages=last.get().getJSONArray("messages");check(messages.getJSONObject(2).getJSONArray("tool_calls").length()==2,"Parallel tool calls remain grouped");check(messages.getJSONObject(3).getString("role").equals("tool"),"Tool result mapping");check(out.getJSONArray("output").getJSONObject(0).getString("call_id").equals("a"),"Response tool mapping");check(out.getJSONObject("usage").getInt("input_tokens")==7,"Usage mapping");check(auth.get().equals("Bearer test-key"),"Explicit authentication");
   cfg.put("toolCalling",false).put("tokenField","max_completion_tokens");Provider.request(cfg,p,"",null);check(!last.get().has("tools"),"Chat-only mode");check(last.get().has("max_completion_tokens"),"OpenAI token field");check(auth.get()==null,"No key header when absent");
   String slot=Provider.slot(cfg);JSONObject other=new JSONObject(cfg.toString()).put("base",cfg.getString("base")+"other");check(!slot.equals(Provider.slot(other)),"Credentials bound to exact endpoint");
   rejects(new JSONObject().put("type","compatible").put("base","http://127.0.0.1/v1"));rejects(new JSONObject().put("type","ollama").put("base","http://8.8.8.8/v1"));rejects(new JSONObject().put("type","compatible").put("base","https://u:p@example.com/v1"));rejects(new JSONObject().put("type","compatible").put("base","https://example.com/v1?key=bad"));
   for(String url:new String[]{"http://example.com","https://127.0.0.1/","https://[::1]/","https://192.168.1.1/"})try{WebTools.publicUrl(url);throw new AssertionError("Private or insecure web URL accepted");}catch(IOException expected){}
   System.out.println("PASS: real local HTTP provider contract, models, tool-call grouping, usage, endpoint-bound credentials, chat-only mode, token fields and web URL restrictions. No paid provider contacted.");
  }finally{server.stop(0);}
 }
}
