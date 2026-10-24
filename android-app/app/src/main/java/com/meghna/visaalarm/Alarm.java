package com.meghna.visaalarm;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.PowerManager;
import android.os.VibrationEffect;
import android.os.Vibrator;

/**
 * Plays the alarm on the ALARM audio stream, so it rings even when the phone
 * is on silent or vibrate, and shows a full-screen alert until dismissed.
 */
final class Alarm {
    static final String CHANNEL_ALARM = "alarm";
    static final String EXTRA_MESSAGE = "message";
    static final int ALARM_NOTIFICATION_ID = 2;

    private static MediaPlayer player;
    private static Vibrator vibrator;
    private static PowerManager.WakeLock wakeLock;
    private static int previousVolume = -1;

    private Alarm() {}

    static void createChannel(Context c) {
        NotificationChannel ch = new NotificationChannel(CHANNEL_ALARM, "Visa slot alarms",
                NotificationManager.IMPORTANCE_HIGH);
        ch.setDescription("Full-screen alarm when a visa slot is posted");
        ch.setSound(null, null); // the app plays its own looping alarm sound
        ch.setBypassDnd(true);
        ch.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        c.getSystemService(NotificationManager.class).createNotificationChannel(ch);
    }

    static synchronized void start(Context c, String message) {
        Context app = c.getApplicationContext();
        createChannel(app);

        Intent full = new Intent(app, AlarmActivity.class)
                .putExtra(EXTRA_MESSAGE, message)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent fullPi = PendingIntent.getActivity(app, 0, full,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stopPi = PendingIntent.getBroadcast(app, 1, new Intent(app, StopAlarmReceiver.class),
                PendingIntent.FLAG_IMMUTABLE);

        Notification n = new Notification.Builder(app, CHANNEL_ALARM)
                .setSmallIcon(R.drawable.ic_alarm)
                .setContentTitle("VISA SLOT")
                .setContentText(message)
                .setStyle(new Notification.BigTextStyle().bigText(message))
                .setCategory(Notification.CATEGORY_ALARM)
                .setFullScreenIntent(fullPi, true)
                .setContentIntent(fullPi)
                .setDeleteIntent(stopPi)
                .addAction(new Notification.Action.Builder(null, "Dismiss", stopPi).build())
                .setOngoing(true)
                .build();
        app.getSystemService(NotificationManager.class).notify(ALARM_NOTIFICATION_ID, n);

        if (player != null) return; // already ringing; the notification text is updated

        PowerManager pm = app.getSystemService(PowerManager.class);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "visaalarm:ringing");
        wakeLock.acquire(10 * 60 * 1000L); // ring for at most 10 minutes

        AudioManager am = app.getSystemService(AudioManager.class);
        previousVolume = am.getStreamVolume(AudioManager.STREAM_ALARM);
        am.setStreamVolume(AudioManager.STREAM_ALARM, am.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0);

        Uri sound = soundUri(app);
        try {
            player = new MediaPlayer();
            player.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build());
            player.setDataSource(app, sound);
            player.setLooping(true);
            player.prepare();
            player.start();
        } catch (Exception e) {
            player = null;
        }

        vibrator = app.getSystemService(Vibrator.class);
        if (vibrator != null) {
            vibrator.vibrate(VibrationEffect.createWaveform(new long[]{0, 800, 400}, 0),
                    new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build());
        }

        // Also try opening the alert screen directly (works while the app is in front).
        try {
            app.startActivity(full);
        } catch (Exception ignored) {
            // Background launch blocked: the full-screen notification covers it.
        }
    }

    private static Uri soundUri(Context app) {
        switch (Prefs.sound(app)) {
            case "scream":
                return Uri.parse("android.resource://" + app.getPackageName() + "/" + R.raw.scream);
            case "wilhelm":
                return Uri.parse("android.resource://" + app.getPackageName() + "/" + R.raw.wilhelm);
            case "vastuguna":
                int clip = personalClip(app);
                if (clip != 0) return Uri.parse("android.resource://" + app.getPackageName() + "/" + clip);
                // Built without the clip: fall through to the phone alarm.
            default:
                Uri u = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
                return u != null ? u : RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE);
        }
    }

    /** The personal "vastuguna huiya" clip, which is not in the repo; 0 when this build lacks it. */
    static int personalClip(Context c) {
        return c.getResources().getIdentifier("vastuguna", "raw", c.getPackageName());
    }

    static synchronized void stop(Context c) {
        Context app = c.getApplicationContext();
        if (player != null) {
            try {
                player.stop();
            } catch (Exception ignored) {
            }
            player.release();
            player = null;
        }
        if (vibrator != null) {
            vibrator.cancel();
            vibrator = null;
        }
        if (previousVolume >= 0) {
            app.getSystemService(AudioManager.class)
                    .setStreamVolume(AudioManager.STREAM_ALARM, previousVolume, 0);
            previousVolume = -1;
        }
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        wakeLock = null;
        app.getSystemService(NotificationManager.class).cancel(ALARM_NOTIFICATION_ID);
    }
}
