package com.meghna.visaalarm;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** "Dismiss" on the alarm notification. */
public class StopAlarmReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent intent) {
        Alarm.stop(c);
    }
}
