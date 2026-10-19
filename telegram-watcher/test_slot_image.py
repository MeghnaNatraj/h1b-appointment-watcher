import asyncio
import datetime
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import h1b_slot_watcher as w  # noqa: E402
import slot_image as s  # noqa: E402


class SummarizeTest(unittest.TestCase):
    def test_clean_screenshot(self):
        self.assertEqual(s.summarize("Hyderabad H1B Regular - Available: 04 Nov 2026, 05 Nov 2026, 12 Nov 2026"),
                         "Hyderabad, H1B regular, 3 dates: Nov 4, 5, 12 2026")

    def test_noisy_ocr(self):
        # Misread letters in the city, H-1B with a hyphen, 0 for o and O for 0.
        text = "HYDERAHAD  Consular\nH-1B  REGULAR\nN0v O4, 2026 | l2 Nov 2026"
        self.assertEqual(s.summarize(text), "Hyderabad, H1B regular, 2 dates: Nov 4, 12 2026")

    def test_date_formats(self):
        dates, months = s.find_dates("2026-11-04, Nov 5 2026, 11/06/2026, 7th November, 2026, 08-Nov-2026")
        self.assertEqual([d.day for d in dates], [4, 5, 6, 7, 8])
        self.assertEqual(months, [])

    def test_day_list(self):
        dates, _ = s.find_dates("Available 04, 05 & 12 Nov 2026")
        self.assertEqual([d.day for d in dates], [4, 5, 12])

    def test_numeric_dates_are_month_first(self):
        self.assertEqual(s.find_dates("01/05/2027")[0], [datetime.date(2027, 1, 5)])
        # Day first only when month first cannot be a date.
        self.assertEqual(s.find_dates("24/11/2026")[0], [datetime.date(2026, 11, 24)])

    def test_real_calendar_screenshot(self):
        # OCR of a real Hyderabad VAC screenshot: the calendar headers are not openings.
        text = ("OFC Post\nHYDERABAD VAC\nDate (MM/DD/YYYY)\n@ {Jan [2027 | February 2027 \u00b0\n"
                "Su Mo Tu We Th Sa Su Mo Tu We Th Fr Sa\nDate (MM/DD/YYYY) i Availability\n\u00ae 01/05/2027")
        self.assertEqual(s.summarize(text), "Hyderabad VAC, 1 date: Jan 5 2027")

    def test_month_only(self):
        self.assertEqual(s.summarize("Chennai H4 dropbox slots in December 2026"),
                         "Chennai, H4 dropbox, dates in Dec 2026")

    def test_month_only_not_repeated_for_full_dates(self):
        self.assertEqual(s.find_dates("04 Nov 2026"), ([datetime.date(2026, 11, 4)], []))

    def test_invalid_date_ignored(self):
        self.assertEqual(s.find_dates("31 Nov 2026"), ([], []))

    def test_locations(self):
        self.assertEqual(s.find_locations("U.S. Embassy NEW DELHI"), ["New Delhi"])
        self.assertEqual(s.find_locations("delhi then mumbai"), ["New Delhi", "Mumbai"])
        self.assertEqual(s.find_locations("Chennal"), ["Chennai"])
        self.assertEqual(s.find_locations("Kolkata / Toronto"), ["Kolkata", "Toronto"])
        # Words that merely contain a short city name do not count.
        self.assertEqual(s.find_locations("chrome romeo"), [])

    def test_years_change(self):
        self.assertEqual(s.summarize("Toronto 2026-12-30 2027-01-05"),
                         "Toronto, 2 dates: Dec 30 2026, Jan 5 2027")

    def test_nothing_useful(self):
        self.assertIsNone(s.summarize("random meme text H1B"))
        self.assertIsNone(s.summarize(""))
        self.assertIsNone(s.summarize(None))

    def test_many_dates_stay_short(self):
        text = "Mumbai " + " ".join(f"{d:02d} Nov 2026" for d in range(1, 21))
        summary = s.summarize(text)
        self.assertIn("20 dates", summary)
        self.assertIn("and 12 more", summary)
        self.assertLessEqual(len(summary), 120)


class ComposeAlertTest(unittest.TestCase):
    def test_summary_and_full_text(self):
        text = "Hyd slots open " + "x" * 2000
        self.assertEqual(s.compose_alert(text, "Hyderabad, 1 date: Nov 4 2026"),
                         "Hyderabad, 1 date: Nov 4 2026\n" + text)

    def test_text_only(self):
        self.assertEqual(s.compose_alert("Chennai 14 Nov", None), "Chennai 14 Nov")

    def test_summary_only(self):
        self.assertEqual(s.compose_alert("", "Hyderabad"), "Hyderabad")

    def test_neither(self):
        self.assertEqual(s.compose_alert("", None), "")


class ReadSlotImageFallbackTest(unittest.TestCase):
    def test_no_tesseract(self):
        with mock.patch.object(s.shutil, "which", return_value=None):
            self.assertIsNone(s.read_slot_image(b"img"))

    def test_timeout(self):
        with mock.patch.object(s.shutil, "which", return_value="/usr/bin/tesseract"), \
                mock.patch.object(s.subprocess, "run", side_effect=subprocess.TimeoutExpired("tesseract", 15)):
            self.assertIsNone(s.read_slot_image(b"img"))

    def test_tesseract_error(self):
        failed = subprocess.CompletedProcess([], 1, b"", b"Error in pixReadStream")
        with mock.patch.object(s.shutil, "which", return_value="/usr/bin/tesseract"), \
                mock.patch.object(s.subprocess, "run", return_value=failed):
            self.assertIsNone(s.read_slot_image(b"img"))

    def test_disabled(self):
        with mock.patch.dict(os.environ, {"OCR_ENABLED": "false"}), \
                mock.patch.object(s, "ocr_image") as ocr:
            self.assertIsNone(s.read_slot_image(b"img"))
            ocr.assert_not_called()

    def test_success(self):
        ok = subprocess.CompletedProcess([], 0, b"Mumbai H1B 04 Nov 2026", b"")
        with mock.patch.object(s.shutil, "which", return_value="/usr/bin/tesseract"), \
                mock.patch.object(s.subprocess, "run", return_value=ok):
            self.assertEqual(s.read_slot_image(b"img"), "Mumbai, H1B, 1 date: Nov 4 2026")


class FakeMessage:
    def __init__(self, text, image):
        self.raw_text = text
        self.photo = object() if image else None
        self.post = False

    async def download_media(self, file=None):
        return b"jpeg-bytes"


class FakeEvent:
    def __init__(self, text, image):
        self.message = FakeMessage(text, image)
        self.sender_id = 42
        self.chat_id = 7


class FakePerms:
    is_admin = False
    is_creator = False


class FakeClient:
    def __init__(self, calls):
        self.calls = calls

    async def get_permissions(self, chat, sender):
        return FakePerms()

    async def send_file(self, target, f, caption=None):
        self.calls.append(("copy", caption))

    async def send_message(self, target, text):
        self.calls.append(("copy", text))


class HandlerTest(unittest.TestCase):
    """Run the real handler with every channel stubbed, no network."""

    def run_handler(self, text, image, summary):
        calls = []
        env = {"TELEGRAM_RECIPIENT": "someone", "NTFY_TOPIC": "t", "TG_BOT_TOKEN": "x", "TG_BOT_CHAT_ID": "1",
               "EMAIL_ENABLED": "true", "WA_ENABLED": "true", "TELEGRAM_COPIES_ENABLED": "false"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(w, "send_ntfy", lambda t, title="VISA SLOT", priority="urgent":
                                  calls.append(("ntfy", title, t))), \
                mock.patch.object(w.slot_image, "read_slot_image",
                                  lambda b: calls.append(("ocr",)) or summary), \
                mock.patch.object(w, "send_telegram_bot", lambda t, b: calls.append(("bot", t))), \
                mock.patch.object(w, "send_email", lambda subj, body: calls.append(("email", subj, body))), \
                mock.patch.object(w, "send_whatsapp", lambda t, report=True: calls.append(("wa", t))):
            asyncio.run(w.make_handler(FakeClient(calls))(FakeEvent(text, image)))
        return calls

    def test_photo_with_summary(self):
        calls = self.run_handler("", True, "Hyderabad, 1 date: Nov 4 2026")
        self.assertEqual(calls, [
            ("ntfy", "VISA SLOT", "New slot photo posted"),
            ("ocr",),
            ("ntfy", "Slot details", "Hyderabad, 1 date: Nov 4 2026"),
            ("bot", "Hyderabad, 1 date: Nov 4 2026"),
            ("email", "H1B slot alert: Hyderabad, 1 date: Nov 4 2026", "Hyderabad, 1 date: Nov 4 2026"),
            ("wa", "Hyderabad, 1 date: Nov 4 2026"),
        ])

    def test_photo_with_caption_and_summary_keeps_full_caption(self):
        caption = "Hyd open now, book fast " + "y" * 1500
        calls = self.run_handler(caption, True, "Hyderabad")
        self.assertEqual(calls[0], ("ntfy", "VISA SLOT", caption))
        self.assertIn(("bot", "Hyderabad\n" + caption), calls)
        self.assertIn(("wa", "Hyderabad\n" + caption), calls)

    def test_photo_unreadable_falls_back(self):
        calls = self.run_handler("", True, None)
        self.assertEqual(calls, [
            ("ntfy", "VISA SLOT", "New slot photo posted"),
            ("ocr",),
            ("bot", ""),
            ("email", "H1B slot alert", "New slot photo posted"),
            ("wa", "New slot photo posted"),
        ])

    def test_text_only_skips_ocr(self):
        calls = self.run_handler("Chennai 14 Nov", False, "unused")
        self.assertNotIn(("ocr",), calls)
        self.assertEqual(calls[0], ("ntfy", "VISA SLOT", "Chennai 14 Nov"))
        self.assertIn(("email", "H1B slot alert", "Chennai 14 Nov"), calls)


@unittest.skipUnless(s.shutil.which("tesseract"), "tesseract not installed")
class TesseractSmokeTest(unittest.TestCase):
    def test_synthetic_screenshot(self):
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            self.skipTest("Pillow not installed")
        import io
        img = Image.new("RGB", (1400, 200), "white")
        try:
            font = ImageFont.truetype("Arial.ttf", 36)
        except OSError:
            font = ImageFont.load_default(size=36)
        ImageDraw.Draw(img).text((30, 70), "Hyderabad H1B Regular - Available: 04 Nov 2026, 12 Nov 2026",
                                 fill="black", font=font)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        self.assertEqual(s.read_slot_image(buf.getvalue()), "Hyderabad, H1B regular, 2 dates: Nov 4, 12 2026")


if __name__ == "__main__":
    unittest.main()
