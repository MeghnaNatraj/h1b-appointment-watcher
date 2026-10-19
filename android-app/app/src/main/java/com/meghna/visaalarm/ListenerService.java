package com.meghna.visaalarm;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.IBinder;
import android.os.PowerManager;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.DateFormat;
import java.util.Date;

/**
 * Keeps one streaming connection open to the private ntfy topic and starts the
 * alarm for every message. Reconnects on its own and catches up on anything
 * sent while it was disconnected.
 */
public class ListenerService extends Service {
    private static final String CHANNEL_STATUS = "status";
    private static final int STATUS_NOTIFICATION_ID = 1;

    private volatile boolean running;
    private Thread worker;
    private PowerManager.WakeLock wakeLock;
    private volatile HttpURLConnection conn;

    static void start(Context c) {
        c.startForegroundService(new Intent(c, ListenerService.class));
    }

    static void stop(Context c) {
        c.stopService(new Intent(c, ListenerService.class));
    }

    @Override
    public void onCreate() {
        super.onCreate();
        NotificationChannel ch = new NotificationChannel(CHANNEL_STATUS, "Listening status",
                NotificationManager.IMPORTANCE_MIN);
        getSystemService(NotificationManager.class).createNotificationChannel(ch);
        Alarm.createChannel(this);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(STATUS_NOTIFICATION_ID, statusNotification("Listening for visa slots"),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        if (worker == null || !worker.isAlive()) {
            running = true;
            PowerManager pm = getSystemService(PowerManager.class);
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "visaalarm:listener");
            wakeLock.acquire();
            worker = new Thread(this::loop, "ntfy-listener");
            worker.start();
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        HttpURLConnection c = conn;
        if (c != null) c.disconnect();
        if (worker != null) worker.interrupt();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        Prefs.setStatus(this, "Stopped");
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private Notification statusNotification(String text) {
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this, CHANNEL_STATUS)
                .setSmallIcon(R.drawable.ic_alarm)
                .setContentTitle("Visa Alarm")
                .setContentText(text)
                .setContentIntent(open)
                .setOngoing(true)
                .build();
    }

    private void setStatus(String s) {
        String stamped = s + " (" + DateFormat.getTimeInstance(DateFormat.SHORT).format(new Date()) + ")";
        Prefs.setStatus(this, stamped);
        getSystemService(NotificationManager.class).notify(STATUS_NOTIFICATION_ID, statusNotification(stamped));
    }

    private void loop() {
        long backoffMs = 2000;
        while (running) {
            try {
                long since = Prefs.lastTime(this);
                // First connection ever: start from now, not from old messages.
                String url = "https://ntfy.sh/" + Prefs.topic(this) + "/json"
                        + (since == 0 ? "" : "?since=" + since);
                HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
                conn = c;
                c.setConnectTimeout(15000);
                // ntfy sends a keepalive every 45 s, so silence for 2 minutes means a dead link.
                c.setReadTimeout(120000);
                c.setRequestProperty("User-Agent", "VisaAlarm/1.0");
                try (BufferedReader r = new BufferedReader(
                        new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
                    setStatus("Listening for visa slots");
                    backoffMs = 2000;
                    String line;
                    while (running && (line = r.readLine()) != null) {
                        if (line.isEmpty()) continue;
                        handle(new JSONObject(line));
                    }
                } finally {
                    c.disconnect();
                }
            } catch (Exception e) {
                if (!running) break;
                setStatus("Reconnecting: " + e.getClass().getSimpleName());
            }
            try {
                Thread.sleep(backoffMs);
            } catch (InterruptedException e) {
                break;
            }
            backoffMs = Math.min(backoffMs * 2, 60000);
        }
    }

    private void handle(JSONObject ev) {
        String event = ev.optString("event");
        long time = ev.optLong("time", 0);
        if (!"message".equals(event)) {
            // Nothing seen yet: remember "now" so reconnects only fetch newer messages.
            if (Prefs.lastTime(this) == 0 && time > 0) Prefs.setLastTime(this, time);
            return;
        }
        String id = ev.optString("id");
        // "since" can repeat the last message on reconnect; ring only once per message.
        if (id.equals(Prefs.lastId(this))) return;
        Prefs.setLastId(this, id);
        if (time > 0) Prefs.setLastTime(this, time);
        String msg = ev.optString("message", "Visa slot posted");
        Alarm.start(this, msg);
    }
}
