import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import h1b_slot_watcher as w  # noqa: E402

ALL_ON = {
    "NTFY_TOPIC": "t", "TG_BOT_TOKEN": "tok", "TG_BOT_CHAT_ID": "1",
    "GMAIL_ADDRESS": "me@example.com", "GMAIL_APP_PASSWORD": "pw",
    "EMAIL_RECIPIENTS": "me@example.com,friend@example.com", "EMAIL_ENABLED": "true",
    "WA_ENABLED": "true", "WA_PHONE_NUMBER_ID": "1", "WA_ACCESS_TOKEN": "a", "WA_RECIPIENT": "2",
}


def stubs(calls, ntfy=None):
    return (
        mock.patch.object(w, "send_ntfy", ntfy or (lambda t: calls.append(("ntfy", t)))),
        mock.patch.object(w, "send_telegram_bot", lambda t, i: calls.append(("bot", t))),
        mock.patch.object(w, "send_email", lambda s, b, r=None: calls.append(("email", s, r))),
        mock.patch.object(w, "send_whatsapp", lambda t, report=True: calls.append(("whatsapp", t, report))),
    )


class ChannelsTest(unittest.TestCase):
    def run_with(self, env, only=None, ntfy=None):
        calls = []
        patches = stubs(calls, ntfy) + (mock.patch.dict(os.environ, env, clear=True),)
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        code = w.run_test_alert("hello", only)
        return code, calls

    def test_order_and_enabled_flags(self):
        with mock.patch.dict(os.environ, ALL_ON, clear=True):
            self.assertEqual([(n, e) for n, e, _ in w.build_channels()],
                             [("ntfy", True), ("bot", True), ("email", True), ("whatsapp", True)])
        with mock.patch.dict(os.environ, {"EMAIL_ENABLED": "false"}, clear=True):
            self.assertEqual([(n, e) for n, e, _ in w.build_channels()],
                             [("ntfy", False), ("bot", False), ("email", False), ("whatsapp", False)])

    def test_bot_needs_token_and_chat(self):
        with mock.patch.dict(os.environ, {"TG_BOT_TOKEN": "x"}, clear=True):
            self.assertFalse(dict((n, e) for n, e, _ in w.build_channels())["bot"])
            self.assertEqual(w.channel_skip_reason("bot"), "missing TG_BOT_CHAT_ID")

    def test_all_channels_sent_email_only_to_owner(self):
        code, calls = self.run_with(ALL_ON)
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in calls], ["ntfy", "bot", "email", "whatsapp"])
        self.assertTrue(all("TEST: " in c[1] for c in calls if c[0] != "email"))
        self.assertEqual(calls[2][2], ["me@example.com"])
        self.assertFalse(calls[3][2])  # whatsapp report=False in test mode

    def test_disabled_and_missing_are_skipped(self):
        env = dict(ALL_ON, EMAIL_ENABLED="false", WA_ENABLED="false")
        del env["NTFY_TOPIC"]
        code, calls = self.run_with(env)
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in calls], ["bot"])

    def test_enabled_email_missing_password_is_skipped(self):
        env = {k: v for k, v in ALL_ON.items() if k != "GMAIL_APP_PASSWORD"}
        code, calls = self.run_with(env)
        self.assertNotIn("email", [c[0] for c in calls])

    def test_channels_filter(self):
        code, calls = self.run_with(ALL_ON, only={"ntfy", "whatsapp"})
        self.assertEqual([c[0] for c in calls], ["ntfy", "whatsapp"])

    def test_failure_gives_nonzero_exit(self):
        def boom(t):
            raise RuntimeError("down")
        code, calls = self.run_with(ALL_ON, ntfy=boom)
        self.assertEqual(code, 1)
        self.assertEqual([c[0] for c in calls], ["bot", "email", "whatsapp"])


if __name__ == "__main__":
    unittest.main()
