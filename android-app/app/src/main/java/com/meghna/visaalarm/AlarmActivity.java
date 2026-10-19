package com.meghna.visaalarm;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Full-screen red alert shown over the lock screen while the alarm rings. */
public class AlarmActivity extends Activity {
    private TextView message;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        int pad = dp(24);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.parseColor("#B71C1C"));
        root.setPadding(pad, dp(48), pad, pad);

        TextView title = new TextView(this);
        title.setText("VISA SLOT");
        title.setTextColor(Color.WHITE);
        title.setTextSize(40);
        title.setGravity(Gravity.CENTER);
        root.addView(title);

        message = new TextView(this);
        message.setTextColor(Color.WHITE);
        message.setTextSize(20);
        message.setPadding(0, dp(24), 0, dp(24));
        ScrollView scroll = new ScrollView(this);
        scroll.addView(message);
        root.addView(scroll, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));

        Button telegram = bigButton("Open Telegram");
        telegram.setOnClickListener(v -> {
            Alarm.stop(this);
            openTelegram();
            finish();
        });
        root.addView(telegram);

        Button dismiss = bigButton("Dismiss");
        dismiss.setOnClickListener(v -> {
            Alarm.stop(this);
            finish();
        });
        root.addView(dismiss);

        setContentView(root);
        showMessage(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        showMessage(intent);
    }

    private void showMessage(Intent intent) {
        String m = intent.getStringExtra(Alarm.EXTRA_MESSAGE);
        message.setText(m == null ? "Visa slot posted" : m);
    }

    private void openTelegram() {
        for (String pkg : new String[]{"org.telegram.messenger", "org.telegram.messenger.web",
                "org.thunderdog.challegram"}) {
            Intent launch = getPackageManager().getLaunchIntentForPackage(pkg);
            if (launch != null) {
                startActivity(launch);
                return;
            }
        }
    }

    private Button bigButton(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setTextSize(22);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(72));
        lp.topMargin = dp(12);
        b.setLayoutParams(lp);
        return b;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
