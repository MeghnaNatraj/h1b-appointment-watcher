package com.meghna.visaalarm;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * One screen, one button. Tapping Start asks for each permission the alarm
 * needs, one at a time, then starts listening. Nothing else to set up.
 */
public class MainActivity extends Activity {
    private TextView status;
    private Button toggle;
    private boolean starting; // walking through the permission prompts after Start
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable ticker = new Runnable() {
        @Override
        public void run() {
            refresh();
            handler.postDelayed(this, 2000);
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        int pad = dp(24);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("Visa Alarm");
        title.setTextSize(32);
        title.setGravity(Gravity.CENTER);
        root.addView(title);

        status = new TextView(this);
        status.setTextSize(18);
        status.setGravity(Gravity.CENTER);
        status.setPadding(0, dp(16), 0, dp(32));
        root.addView(status);

        toggle = new Button(this);
        toggle.setTextSize(28);
        toggle.setTextColor(Color.WHITE);
        root.addView(toggle, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(120)));
        toggle.setOnClickListener(v -> {
            if (Prefs.enabled(this)) {
                Prefs.setEnabled(this, false);
                ListenerService.stop(this);
                refresh();
            } else {
                starting = true;
                continueStart();
            }
        });

        Button test = new Button(this);
        test.setText("Test alarm");
        test.setAllCaps(false);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(32);
        root.addView(test, lp);
        test.setOnClickListener(v -> Alarm.start(this, "Test: this is what a visa slot alarm looks like."));

        setContentView(root);

        // Already switched on (e.g. after an update): make sure it is running.
        if (Prefs.enabled(this)) ListenerService.start(this);
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Back from a permission screen: carry on with the next step.
        if (starting) continueStart();
        handler.post(ticker);
    }

    @Override
    protected void onPause() {
        super.onPause();
        handler.removeCallbacks(ticker);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        if (starting) continueStart();
    }

    /** Asks for the next missing permission, or starts listening once all are in place. */
    private void continueStart() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                && !askedOnce("notif")) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
            return;
        }
        if (Build.VERSION.SDK_INT >= 34
                && !getSystemService(NotificationManager.class).canUseFullScreenIntent()
                && !askedOnce("fullscreen")) {
            startActivity(new Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT,
                    Uri.parse("package:" + getPackageName())));
            return;
        }
        if (!getSystemService(PowerManager.class).isIgnoringBatteryOptimizations(getPackageName())
                && !askedOnce("battery")) {
            startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.parse("package:" + getPackageName())));
            return;
        }
        starting = false;
        Prefs.setEnabled(this, true);
        ListenerService.start(this);
        refresh();
    }

    /** True if this prompt was already shown during the current Start, so a "no" does not loop. */
    private boolean askedOnce(String key) {
        String k = "asked_" + key;
        if (getIntent().getBooleanExtra(k, false)) return true;
        getIntent().putExtra(k, true);
        return false;
    }

    private void refresh() {
        boolean on = Prefs.enabled(this);
        status.setText(on ? Prefs.status(this) : "Off. Tap Start to get visa slot alarms.");
        toggle.setText(on ? "STOP" : "START");
        toggle.setBackgroundColor(Color.parseColor(on ? "#757575" : "#2E7D32"));
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
