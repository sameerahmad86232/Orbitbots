package in.orbitai.mobile;
import android.app.*;import android.app.job.*;import android.content.*;import org.json.*;
/** Optional periodic checks. Android decides actual timing; this is not push. */
public final class ComputerNotificationJob extends JobService {
 volatile boolean stopped;
 @Override public boolean onStartJob(JobParameters params){stopped=false;new Thread(()->{try{
  JSONObject status=(JSONObject)Computer.call(this,"/status","GET","",null);int pending=status.optInt("pending");String before=Store.get(this,"computerPendingCount","0");
  if(!stopped&&pending>0&&!before.equals(String.valueOf(pending))){NotificationManager manager=getSystemService(NotificationManager.class);manager.createNotificationChannel(new NotificationChannel("results","Task results and approvals",NotificationManager.IMPORTANCE_DEFAULT));Intent open=new Intent(this,MainActivity.class).putExtra("orbitScreen","computer");PendingIntent pi=PendingIntent.getActivity(this,77,open,PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);manager.notify(77,new Notification.Builder(this,"results").setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle("Orbit is waiting for you").setContentText(pending+" computer action(s) need your review").setContentIntent(pi).setAutoCancel(true).build());}
  if(!stopped){Store.put(this,"computerPendingCount",String.valueOf(pending));if(pending==0)getSystemService(NotificationManager.class).cancel(77);}
 }catch(Exception ignored){}finally{if(!stopped)jobFinished(params,false);}}).start();return true;}
 @Override public boolean onStopJob(JobParameters params){stopped=true;return false;}
}
