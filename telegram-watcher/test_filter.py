import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import h1b_slot_watcher as w  # noqa: E402


class ShouldAlertTest(unittest.TestCase):
    def test_city_containing_na_alerts(self):
        self.assertTrue(w.should_alert("CHENNAI H1B slots open 12 Nov", False))
        self.assertTrue(w.should_alert("Ahmedabad available", False))

    def test_plain_na_skipped(self):
        self.assertFalse(w.should_alert("NA", False))
        self.assertFalse(w.should_alert("Hyderabad na", False))

    def test_n_slash_a_skipped(self):
        self.assertFalse(w.should_alert("Mumbai N/A", False))
        self.assertFalse(w.should_alert("n/a", False))

    def test_na_with_slot_number_skipped(self):
        for msg in ("NA1 H1B all", "Na1 h1b all", "Na2 all", "NA4 H1", "Na1 all h4"):
            self.assertFalse(w.should_alert(msg, False), msg)
            self.assertFalse(w.should_alert(msg, True), msg)

    def test_spaced_and_punctuated_na_skipped(self):
        for msg in ("Hyderabad N A", "n a", "Mumbai N . A", "Delhi N-A", "N  A all", "N A1 h1b"):
            self.assertFalse(w.should_alert(msg, False), msg)
            self.assertFalse(w.should_alert(msg, True), msg)

    def test_spaced_letters_inside_words_still_alert(self):
        for msg in ("Chennai available", "Kolkata Nov 4", "IN Amsterdam open", "Slots open in Hyderabad"):
            self.assertTrue(w.should_alert(msg, False), msg)

    def test_small_talk_skipped(self):
        for msg in ("What’s up?", "what's up", "Whats up??", "sup", "Hi", "hello!!", "Hey", "Good morning",
                    "Thanks", "thank you", "ok", "Okay.", "lol"):
            self.assertFalse(w.should_alert(msg, False), msg)

    def test_small_talk_with_slot_or_photo_alerts(self):
        self.assertTrue(w.should_alert("Hi, Chennai slots open Nov 13", False))
        self.assertTrue(w.should_alert("hey", True))
        self.assertTrue(w.should_alert("Hyderabad", False))

    def test_ghost_skipped(self):
        for msg in ("Ghost", "ghost slot", "Got ghosted again", "GHOST booking"):
            self.assertFalse(w.should_alert(msg, False), msg)
            self.assertFalse(w.should_alert(msg, True), msg)

    def test_n_dot_a_skipped(self):
        self.assertFalse(w.should_alert("Delhi N.A.", False))
        self.assertFalse(w.should_alert("Delhi: Na", False))

    def test_image_without_na_alerts(self):
        self.assertTrue(w.should_alert("", True))
        self.assertTrue(w.should_alert("Chennai 14 Nov", True))

    def test_image_with_na_skipped(self):
        self.assertFalse(w.should_alert("NA", True))
        self.assertFalse(w.should_alert("Hyderabad n/a", True))

    def test_empty_text_without_image_skipped(self):
        self.assertFalse(w.should_alert("", False))

    def test_junk_skipped(self):
        junk = "This is H1 H4 inperson slots available group, please read rules"
        self.assertFalse(w.should_alert(junk, False))
        self.assertFalse(w.should_alert(junk, True))

    def test_plain_text_alerts(self):
        self.assertTrue(w.should_alert("Kolkata 3 dates in December", False))


class LoadEnvTest(unittest.TestCase):
    def test_parses_and_does_not_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text('# comment\nVS_TEST_A=1\nVS_TEST_B="two words"\nexport VS_TEST_C=x=y\n')
            os.environ["VS_TEST_A"] = "keep"
            try:
                w.load_env(p)
                self.assertEqual(os.environ["VS_TEST_A"], "keep")
                self.assertEqual(os.environ["VS_TEST_B"], "two words")
                self.assertEqual(os.environ["VS_TEST_C"], "x=y")
            finally:
                for k in ("VS_TEST_A", "VS_TEST_B", "VS_TEST_C"):
                    os.environ.pop(k, None)


if __name__ == "__main__":
    unittest.main()
