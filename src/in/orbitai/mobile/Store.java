package in.orbitai.mobile;
import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.*;
import java.security.KeyStore;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import java.io.*;
final class Store {
 static synchronized javax.crypto.SecretKey secret() throws Exception {
  KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);
  if(!ks.containsAlias("OrbitVault")){KeyGenerator kg=KeyGenerator.getInstance("AES","AndroidKeyStore");kg.init(new KeyGenParameterSpec.Builder("OrbitVault",KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());kg.generateKey();}
  return (javax.crypto.SecretKey)ks.getKey("OrbitVault",null);
 }
 static String encrypt(String value) throws Exception{Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,secret());return Base64.encodeToString(c.getIV(),Base64.NO_WRAP)+":"+Base64.encodeToString(c.doFinal(value.getBytes(StandardCharsets.UTF_8)),Base64.NO_WRAP);}
 static String decrypt(String value) throws Exception{String[] a=value.split(":",2);Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.DECRYPT_MODE,secret(),new GCMParameterSpec(128,Base64.decode(a[0],Base64.NO_WRAP)));return new String(c.doFinal(Base64.decode(a[1],Base64.NO_WRAP)),StandardCharsets.UTF_8);}
 static synchronized void put(Context c,String k,String v) throws Exception{if(!c.getSharedPreferences("vault",0).edit().putString(k,encrypt(v)).commit())throw new IOException("Unable to save");}
 static synchronized String get(Context c,String k,String fallback) throws Exception{String v=c.getSharedPreferences("vault",0).getString(k,null);return v==null?fallback:decrypt(v);}
 static void remove(Context c,String k){c.getSharedPreferences("vault",0).edit().remove(k).commit();}
 static String safe(String s){if(s==null||!s.matches("[A-Za-z0-9_.-]{1,100}")||s.equals(".")||s.equals(".."))throw new IllegalArgumentException("Invalid identifier");return s;}
 static File folder(Context c,String bot){File f=new File(c.getFilesDir(),"workspace/"+safe(bot));f.mkdirs();return f;}
 static synchronized void artifact(Context c,String bot,String name,String text) throws Exception{safe(name);if(text.length()>300000)throw new IOException("File exceeds 300,000 characters");File dir=folder(c,bot);if(dir.list()!=null&&dir.list().length>=30&&!new File(dir,name).exists())throw new IOException("Workspace limit: 30 files");android.util.AtomicFile f=new android.util.AtomicFile(new File(dir,name));FileOutputStream out=f.startWrite();try{out.write(encrypt(text).getBytes(StandardCharsets.UTF_8));f.finishWrite(out);}catch(Exception e){f.failWrite(out);throw e;}}
 static synchronized String read(Context c,String bot,String name) throws Exception{File f=new File(folder(c,bot),safe(name));try(InputStream in=new FileInputStream(f)){ByteArrayOutputStream b=new ByteArrayOutputStream();byte[] buf=new byte[8192];int n;while((n=in.read(buf))!=-1){b.write(buf,0,n);if(b.size()>2000000)throw new IOException("File too large");}return decrypt(b.toString("UTF-8"));}}
 static JSONArray files(Context c,String bot){JSONArray a=new JSONArray();String[] names=folder(c,bot).list();if(names!=null)for(String n:names)if(!n.endsWith(".bak")&&!n.endsWith(".new"))a.put(n);return a;}
 static void wipe(Context c,String bot){File d=folder(c,bot);File[] fs=d.listFiles();if(fs!=null)for(File f:fs)f.delete();d.delete();remove(c,"memory:"+bot);}
}
