"""Read slot screenshots with local OCR (the free tesseract CLI) and summarise them.

Everything here is best effort: any failure returns None and the alert goes
out exactly as it would without OCR.
"""
import datetime
import difflib
import logging
import os
import re
import shutil
import subprocess
import tempfile

log = logging.getLogger("h1b_watcher")

OCR_TIMEOUT_SECONDS = 15

# US visa posts in India first, then common US consulates elsewhere that H1B
# applicants book. Aliases (old names, short forms) map to the display name.
LOCATIONS = {
    "Hyderabad": ["hyderabad"],
    "Chennai": ["chennai", "madras"],
    "Mumbai": ["mumbai", "bombay"],
    "New Delhi": ["new delhi", "delhi"],
    "Kolkata": ["kolkata", "calcutta"],
    "Toronto": ["toronto"],
    "Vancouver": ["vancouver"],
    "Calgary": ["calgary"],
    "Montreal": ["montreal"],
    "Ottawa": ["ottawa"],
    "Halifax": ["halifax"],
    "Quebec City": ["quebec"],
    "Mexico City": ["mexico city"],
    "Monterrey": ["monterrey"],
    "Guadalajara": ["guadalajara"],
    "Tijuana": ["tijuana"],
    "Ciudad Juarez": ["ciudad juarez", "juarez"],
    "Nuevo Laredo": ["nuevo laredo"],
    "Nogales": ["nogales"],
    "Matamoros": ["matamoros"],
    "Merida": ["merida"],
    "Hermosillo": ["hermosillo"],
    "London": ["london"],
    "Belfast": ["belfast"],
    "Dublin": ["dublin"],
    "Frankfurt": ["frankfurt"],
    "Munich": ["munich"],
    "Paris": ["paris"],
    "Amsterdam": ["amsterdam"],
    "Singapore": ["singapore"],
    "Bangkok": ["bangkok"],
    "Kathmandu": ["kathmandu"],
    "Colombo": ["colombo"],
    "Dhaka": ["dhaka"],
    "Abu Dhabi": ["abu dhabi"],
    "Dubai": ["dubai"],
    "Doha": ["doha"],
    "Kuwait": ["kuwait"],
    "Tokyo": ["tokyo"],
    "Seoul": ["seoul"],
    "Hong Kong": ["hong kong"],
    "Manila": ["manila"],
    "Kuala Lumpur": ["kuala lumpur"],
    "Sydney": ["sydney"],
    "Nassau": ["nassau"],
    "Bridgetown": ["bridgetown"],
    "Kingston": ["kingston"],
    "Bogota": ["bogota"],
}

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH_RE = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
            r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
DAY_RE = r"(?:[0-3]?\d)(?:st|nd|rd|th)?"
DAY_LIST_RE = rf"({DAY_RE}(?:\s*(?:,|&|and)\s*{DAY_RE})*)"
YEAR_RE = r"(20\d{2})(?!\d)"
SEP = r"[\s,\-./]*"

# "04 Nov 2026", "4th November, 2026", "04, 05 & 12 Nov 2026", "04-Nov-2026"
DAY_MONTH_YEAR = re.compile(rf"(?<!\d){DAY_LIST_RE}{SEP}{MONTH_RE}{SEP}{YEAR_RE}", re.IGNORECASE)
# "Nov 4 2026", "November 4, 2026", "Nov 4, 5, 12 2026"
MONTH_DAY_YEAR = re.compile(rf"(?<![a-z]){MONTH_RE}{SEP}{DAY_LIST_RE}(?!\d)\s*,?\s*{YEAR_RE}", re.IGNORECASE)
# "2026-11-04"
ISO_DATE = re.compile(r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)")
# "01/05/2027", month first: the US visa appointment pages label dates MM/DD/YYYY
NUMERIC_DATE = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})(?!\d)")
# "November 2026" when no day is visible
MONTH_YEAR = re.compile(rf"(?<![a-z]){MONTH_RE}{SEP}{YEAR_RE}", re.IGNORECASE)


def ocr_image(image_bytes, timeout=OCR_TIMEOUT_SECONDS):
    """Return the text tesseract reads from the image, or None if it cannot run."""
    exe = shutil.which("tesseract")
    if not exe:
        log.info("tesseract is not installed, sending the alert without screenshot details")
        return None
    with tempfile.NamedTemporaryFile(suffix=".img") as f:
        f.write(image_bytes)
        f.flush()
        result = subprocess.run([exe, f.name, "stdout", "-l", "eng"], capture_output=True, timeout=timeout)
    if result.returncode != 0:
        log.warning("tesseract failed: %s", result.stderr.decode(errors="replace")[:300])
        return None
    return result.stdout.decode(errors="replace")


def _fix_ocr_digits_and_letters(text):
    """Undo common OCR swaps so dates and month names parse: N0v -> Nov, O4 -> 04, l2 -> 12."""
    text = re.sub(r"(?<=[A-Za-z])0(?=[A-Za-z])", "o", text)
    text = re.sub(r"\b0(?=ct\b|ctober\b)", "O", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=[A-Za-z])1(?=[A-Za-z]|\b)", "l", text)
    text = re.sub(r"(?<![A-Za-z])[Oo](?=\d)", "0", text)
    text = re.sub(r"(?<=\d)[Oo](?![A-Za-z])", "0", text)
    text = re.sub(r"(?<![A-Za-z])[lI|](?=\d)", "1", text)
    return text


def find_locations(text):
    """Return the known locations named in `text`, in order of appearance.

    Exact matches first; long names also match with a letter or two misread.
    """
    lowered = _fix_ocr_digits_and_letters(text).lower()
    words = [(m.start(), m.group()) for m in re.finditer(r"[a-z]+", lowered)]
    found = {}
    for name, aliases in LOCATIONS.items():
        for alias in aliases:
            m = re.search(r"(?<![a-z])" + r"\s*".join(map(re.escape, alias.split())) + r"(?![a-z])", lowered)
            if m:
                found[name] = min(found.get(name, m.start()), m.start())
                break
            if len(alias.replace(" ", "")) < 6:
                continue
            n = len(alias.split())
            for i in range(len(words) - n + 1):
                candidate = " ".join(w for _, w in words[i:i + n])
                if difflib.SequenceMatcher(None, candidate, alias).ratio() >= 0.85:
                    found[name] = min(found.get(name, words[i][0]), words[i][0])
                    break
            if name in found:
                break
    # "New Delhi" also contains "Delhi": one location, not two.
    return [name for name, _ in sorted(found.items(), key=lambda kv: kv[1])]


def _month_number(word):
    return MONTHS.index(word.lower()[:3]) + 1


def _valid(year, month, day):
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def find_dates(text):
    """Return (full_dates, month_only) found in `text`.

    full_dates is a sorted list of datetime.date; month_only is a sorted list
    of (year, month) for months named without a day. Nothing is guessed.
    """
    text = _fix_ocr_digits_and_letters(text)
    dates, used = set(), []

    def take(match, found):
        dates.update(d for d in found if d)
        used.append(match.span())

    for m in DAY_MONTH_YEAR.finditer(text):
        month, year = _month_number(m.group(2)), int(m.group(3))
        take(m, [_valid(year, month, int(d)) for d in re.findall(r"\d+", m.group(1))])
    for m in MONTH_DAY_YEAR.finditer(text):
        if any(s <= m.start() < e for s, e in used):
            continue
        month, year = _month_number(m.group(1)), int(m.group(3))
        take(m, [_valid(year, month, int(d)) for d in re.findall(r"\d+", m.group(2))])
    for m in ISO_DATE.finditer(text):
        take(m, [_valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))])
    for m in NUMERIC_DATE.finditer(text):
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        take(m, [_valid(year, a, b) or _valid(year, b, a)])

    month_only = set()
    for m in MONTH_YEAR.finditer(text):
        if any(s <= m.start() < e or s < m.end() <= e for s, e in used):
            continue
        month_only.add((int(m.group(2)), _month_number(m.group(1))))
    # With exact dates found, a bare "February 2027" is a calendar header, not an opening.
    if dates:
        month_only = set()
    return sorted(dates), sorted(month_only)


def _format_dates(dates, month_only, max_shown=8):
    """'Nov 4, 5, 12 2026' style: days grouped by month, year written once per run."""
    parts, last_month, last_year = [], None, None
    shown = dates[:max_shown]
    for d in shown:
        if last_year is not None and d.year != last_year:
            parts[-1] += f" {last_year}"
        if (d.year, d.month) != last_month:
            parts.append(f"{d:%b} {d.day}")
        else:
            parts.append(str(d.day))
        last_month, last_year = (d.year, d.month), d.year
    if shown:
        parts[-1] += f" {last_year}"
    if len(dates) > max_shown:
        parts.append(f"and {len(dates) - max_shown} more")
    parts += [datetime.date(y, m, 1).strftime("%b %Y") for y, m in month_only]
    return ", ".join(parts)


def summarize(ocr_text):
    """One-line summary like "Hyderabad, 3 dates: Nov 4, 5, 12 2026", or None when
    neither a location nor a date was found."""
    if not ocr_text or not ocr_text.strip():
        return None
    locations = find_locations(ocr_text)
    dates, month_only = find_dates(ocr_text)
    if not locations and not dates and not month_only:
        return None
    parts = []
    if locations:
        # VAC is the biometrics appointment, not the consular interview.
        vac = " VAC" if re.search(r"(?<![a-z])vac(?![a-z])", ocr_text, re.IGNORECASE) else ""
        parts.append("/".join(locations[:3]) + vac)
    if dates:
        label = "1 date" if len(dates) == 1 else f"{len(dates)} dates"
        parts.append(f"{label}: {_format_dates(dates, month_only)}")
    elif month_only:
        parts.append(f"dates in {_format_dates(dates, month_only)}")
    return ", ".join(parts)


def read_slot_image(image_bytes):
    """OCR the screenshot and return its one-line summary, or None. Never raises."""
    if os.environ.get("OCR_ENABLED", "true").strip().lower() not in ("1", "true", "yes", "on"):
        return None
    try:
        text = ocr_image(image_bytes)
        summary = summarize(text)
        log.info("Screenshot read: %s", summary or "no slot details found")
        return summary
    except Exception as e:
        log.error("Could not read the screenshot: %s", e)
        return None
