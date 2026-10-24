package com.meghna.visaalarm;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.text.SpannableString;
import android.text.style.RelativeSizeSpan;
import android.view.Gravity;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;

import java.util.Arrays;

/**
 * One screen: a big on/off switch, the alarm sound and a test button. Turning
 * it on asks for each permission the alarm needs, one at a time, then starts
 * listening. Nothing else to set up.
 */
public class MainActivity extends Activity {
    private static final int GREEN = Color.parseColor("#2E7D32");
    private static final int GRAY = Color.parseColor("#9E9E9E");
    private static final int BACKGROUND = Color.parseColor("#F5F6F5");
    private static final int INK = Color.parseColor("#1F2421");
    private static final int MUTED = Color.parseColor("#5F6661");
    private static final int LINE = Color.parseColor("#D5D9D6");
    private static final String[] SOUND_KEYS = {"alarm", "scream", "baby"};
    private static final String[] SOUND_LABELS = {"Phone alarm", "Horror movie scream", "Baby crying"};

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
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(pad, dp(56), pad, pad);
        root.setBackgroundColor(BACKGROUND);

        TextView title = new TextView(this);
        title.setText("Visa Alarm");
        title.setTextSize(30);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setTextColor(INK);
        root.addView(title);

        // One big switch: green while listening, gray while off.
        toggle = new Button(this);
        toggle.setAllCaps(false);
        toggle.setTextColor(Color.WHITE);
        toggle.setStateListAnimator(null);
        LinearLayout.LayoutParams big = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(170));
        big.topMargin = dp(36);
        root.addView(toggle, big);
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

        status = new TextView(this);
        status.setTextSize(15);
        status.setTextColor(MUTED);
        status.setGravity(Gravity.CENTER);
        status.setPadding(0, dp(14), 0, dp(36));
        root.addView(status);

        TextView soundLabel = new TextView(this);
        soundLabel.setText("Alarm sound");
        soundLabel.setTextSize(14);
        soundLabel.setTextColor(MUTED);
        root.addView(soundLabel, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        Spinner sound = new Spinner(this);
        ArrayAdapter<String> labels = new ArrayAdapter<>(this,
                android.R.layout.simple_spinner_dropdown_item, SOUND_LABELS);
        sound.setAdapter(labels);
        sound.setSelection(Math.max(0, Arrays.asList(SOUND_KEYS).indexOf(Prefs.sound(this))));
        sound.setBackground(rounded(Color.WHITE, LINE));
        sound.setPadding(dp(12), 0, dp(12), 0);
        LinearLayout.LayoutParams row = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(56));
        row.topMargin = dp(6);
        root.addView(sound, row);
        sound.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, android.view.View view, int position, long id) {
                Prefs.setSound(MainActivity.this, SOUND_KEYS[position]);
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
            }
        });

        Button test = new Button(this);
        test.setText("Test alarm");
        test.setAllCaps(false);
        test.setTextSize(17);
        test.setTextColor(INK);
        test.setStateListAnimator(null);
        test.setBackground(rounded(Color.TRANSPARENT, INK));
        LinearLayout.LayoutParams testLp = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(56));
        testLp.topMargin = dp(16);
        root.addView(test, testLp);
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
        String hint = on ? "Tap to turn off" : "Tap to turn on";
        SpannableString text = new SpannableString((on ? "ON" : "OFF") + "\n" + hint);
        text.setSpan(new RelativeSizeSpan(2.4f), 0, on ? 2 : 3, 0);
        toggle.setText(text);
        toggle.setBackground(rounded(on ? GREEN : GRAY, 0));
        status.setText(on ? Prefs.status(this) : "Not listening. Visa slot alarms are off.");
    }

    /** Rounded box with an optional 1.5 dp outline. */
    private GradientDrawable rounded(int fill, int outline) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(fill);
        d.setCornerRadius(dp(20));
        if (outline != 0) d.setStroke(Math.round(1.5f * getResources().getDisplayMetrics().density), outline);
        return d;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
