package com.meghna.visaalarm;

import android.content.Context;
import android.content.SharedPreferences;

/** Small wrapper around the app's saved settings. */
final class Prefs {
    private Prefs() {}

    private static SharedPreferences sp(Context c) {
        return c.getSharedPreferences("visa_alarm", Context.MODE_PRIVATE);
    }

    /** The private ntfy topic, baked in at build time from the ntfyTopic Gradle property. */
    static String topic(Context c) {
        return BuildConfig.NTFY_TOPIC;
    }

    static boolean enabled(Context c) {
        return sp(c).getBoolean("enabled", false);
    }

    static void setEnabled(Context c, boolean on) {
        sp(c).edit().putBoolean("enabled", on).apply();
    }

    /** Time of the last ntfy event seen, so a reconnect picks up anything missed. */
    static long lastTime(Context c) {
        return sp(c).getLong("last_time", 0);
    }

    static void setLastTime(Context c, long t) {
        sp(c).edit().putLong("last_time", t).apply();
    }

    /** Id of the last ntfy message that rang, so a reconnect never rings twice. */
    static String lastId(Context c) {
        return sp(c).getString("last_id", "");
    }

    static void setLastId(Context c, String id) {
        sp(c).edit().putString("last_id", id).apply();
    }

    /** Alarm sound: "alarm" (the phone's own alarm sound), "scream" or "baby". */
    static String sound(Context c) {
        return sp(c).getString("sound", "alarm");
    }

    static void setSound(Context c, String s) {
        sp(c).edit().putString("sound", s).apply();
    }

    static String status(Context c) {
        return sp(c).getString("status", "Not started");
    }

    static void setStatus(Context c, String s) {
        sp(c).edit().putString("status", s).apply();
    }
}
