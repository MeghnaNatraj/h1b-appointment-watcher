import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import h1b_slot_watcher as w  # noqa: E402

ALL_ON = {
    "NTFY_TOPIC": "t", "TG_BOT_TOKEN": "tok", "TG_BOT_CHAT_ID": "1",
    "WA_ENABLED": "true", "WA_PHONE_NUMBER_ID": "1", "WA_ACCESS_TOKEN": "a", "WA_RECIPIENT": "2",
}


def stubs(calls, ntfy=None):
    return (
        mock.patch.object(w, "send_ntfy", ntfy or (lambda t, title="", priority="": calls.append(("ntfy", t)))),
        mock.patch.object(w, "send_telegram_bot", lambda t: calls.append(("bot", t))),
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
                             [("ntfy", True), ("bot", True), ("whatsapp", True)])
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual([(n, e) for n, e, _ in w.build_channels()],
                             [("ntfy", False), ("bot", False), ("whatsapp", False)])

    def test_bot_needs_token_and_chat(self):
        with mock.patch.dict(os.environ, {"TG_BOT_TOKEN": "x"}, clear=True):
            self.assertFalse(dict((n, e) for n, e, _ in w.build_channels())["bot"])
            self.assertEqual(w.channel_skip_reason("bot"), "missing TG_BOT_CHAT_ID")

    def test_bot_can_be_switched_off(self):
        with mock.patch.dict(os.environ, dict(ALL_ON, BOT_ENABLED="false"), clear=True):
            self.assertFalse(dict((n, e) for n, e, _ in w.build_channels())["bot"])
            self.assertEqual(w.channel_skip_reason("bot"), "disabled (BOT_ENABLED is off)")

    def test_all_channels_sent(self):
        code, calls = self.run_with(ALL_ON)
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in calls], ["ntfy", "bot", "whatsapp"])
        self.assertTrue(all("TEST: " in c[1] for c in calls))
        self.assertFalse(calls[2][2])  # whatsapp report=False in test mode

    def test_disabled_and_missing_are_skipped(self):
        env = dict(ALL_ON, WA_ENABLED="false")
        del env["NTFY_TOPIC"]
        code, calls = self.run_with(env)
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in calls], ["bot"])

    def test_enabled_whatsapp_missing_token_is_skipped(self):
        env = {k: v for k, v in ALL_ON.items() if k != "WA_ACCESS_TOKEN"}
        code, calls = self.run_with(env)
        self.assertNotIn("whatsapp", [c[0] for c in calls])

    def test_channels_filter(self):
        code, calls = self.run_with(ALL_ON, only={"ntfy", "whatsapp"})
        self.assertEqual([c[0] for c in calls], ["ntfy", "whatsapp"])

    def test_failure_gives_nonzero_exit(self):
        def boom(t, title="", priority=""):
            raise RuntimeError("down")
        code, calls = self.run_with(ALL_ON, ntfy=boom)
        self.assertEqual(code, 1)
        self.assertEqual([c[0] for c in calls], ["bot", "whatsapp"])


class NotifyOwnerTest(unittest.TestCase):
    def test_problem_report_goes_to_bot_and_alarm(self):
        calls = []
        with mock.patch.dict(os.environ, ALL_ON, clear=True), \
                mock.patch.object(w, "send_ntfy", lambda t, title="", priority="": calls.append(("ntfy", title, priority))), \
                mock.patch.object(w, "send_telegram_bot", lambda t: calls.append(("bot", t.split("\n")[0]))), \
                tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(w, "HERE", Path(tmp)):
            w.report_problem("unit-test", "Telegram login (logged out).", "Log in again")
        self.assertEqual(calls, [("bot", "H1B watcher stopped: Telegram login"),
                                 ("ntfy", "H1B watcher stopped: Telegram login", "high")])

    def test_no_channel_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                w.notify_owner("t", "b")


if __name__ == "__main__":
    unittest.main()
