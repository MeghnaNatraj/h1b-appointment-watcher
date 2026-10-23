import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import h1b_slot_watcher as w  # noqa: E402


class TestAlertTest(unittest.TestCase):
    def test_sends_test_message(self):
        calls = []
        with mock.patch.object(w, "send_ntfy", lambda t: calls.append(t)):
            self.assertEqual(w.run_test_alert("hello"), 0)
        self.assertEqual(calls, ["TEST: hello"])

    def test_failure_gives_nonzero_exit(self):
        def boom(t):
            raise RuntimeError("down")
        with mock.patch.object(w, "send_ntfy", boom):
            self.assertEqual(w.run_test_alert(""), 1)


class ReportProblemTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(w, "HERE", Path(tmp.name))
        p.start()
        self.addCleanup(p.stop)

    def test_goes_to_alarm_once_per_window(self):
        calls = []
        with mock.patch.object(w, "send_ntfy", lambda t, title="", priority="": calls.append((title, priority))):
            w.report_problem("unit-test", "Telegram login (logged out).", "Log in again")
            w.report_problem("unit-test", "Telegram login (logged out).", "Log in again")
        self.assertEqual(calls, [("H1B watcher stopped: Telegram login", "high")])

    def test_falls_back_to_healthcheck_fail(self):
        def boom(*a, **k):
            raise RuntimeError("down")
        with mock.patch.dict(os.environ, {"HEALTHCHECK_URL": "https://hc.example/abc"}), \
                mock.patch.object(w, "send_ntfy", boom), \
                mock.patch.object(w.requests, "post") as post:
            w.report_problem("unit-test", "Crash.", "Restart")
        self.assertEqual(post.call_args[0][0], "https://hc.example/abc/fail")


if __name__ == "__main__":
    unittest.main()
