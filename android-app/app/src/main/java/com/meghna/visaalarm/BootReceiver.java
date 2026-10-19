package com.meghna.visaalarm;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Restarts listening after a reboot or an app update, if it was on. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent intent) {
        if (Prefs.enabled(c)) ListenerService.start(c);
    }
}
