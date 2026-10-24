"""Make the app's extra alarm sounds: a horror-movie scream and a crying baby.

Both are synthesized here, so there is no recording to license. Writes
loopable mono WAV files into app/src/main/res/raw/. Run with python3, no packages needed.
"""
import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050
OUT = Path(__file__).resolve().parent.parent / "app/src/main/res/raw"


def envelope(t, length, attack, release):
    if t < attack:
        return t / attack
    if t > length - release:
        return max(0.0, (length - t) / release)
    return 1.0


def scream():
    """Four sharp screeching stabs, then one long rising shriek."""
    rnd = random.Random(1)
    out = []
    parts = [(0.32, 1500, 1700)] * 4 + [(1.6, 900, 2100)]
    for length, f_start, f_end in parts:
        phases = [0.0, 0.0]
        for i in range(int(length * RATE)):
            t = i / RATE
            glide = f_start + (f_end - f_start) * (t / length) ** 0.6
            f = glide + 70 * math.sin(2 * math.pi * 9 * t)  # shaky vibrato
            s = 0.0
            # Two voices a little out of tune beat against each other.
            for v, detune in enumerate((0.0, 31.0)):
                phases[v] += 2 * math.pi * (f + detune) / RATE
                s += sum(math.sin(k * phases[v]) / k for k in range(1, 7))
            s += 0.6 * (rnd.random() * 2 - 1)  # breath and rasp
            out.append(math.tanh(1.8 * s) * envelope(t, length, 0.012, 0.06))
        out += [0.0] * int(0.06 * RATE)
    return out


# Infant "waa" vowel: resonances (Hz, width) that shape the harmonics.
FORMANTS = [(1100, 300), (2100, 400), (4000, 600)]


def _formant_gain(freq):
    return sum(1 / (1 + ((freq - fc) / bw) ** 2) for fc, bw in FORMANTS) + 0.05


def baby_cry():
    """Two "waa" cries with a short gasp after each."""
    rnd = random.Random(2)
    out = []
    for length, low, peak in ((1.1, 400, 560), (1.3, 380, 600)):
        phase, jitter = 0.0, 0.0
        for i in range(int(length * RATE)):
            t = i / RATE
            x = t / length
            # Pitch rises quickly, holds, then sags at the end of the breath.
            contour = low + (peak - low) * math.sin(math.pi * min(1.0, x * 1.4)) ** 0.7
            jitter = 0.995 * jitter + rnd.gauss(0, 0.6)
            f0 = contour + 14 * math.sin(2 * math.pi * 5.5 * t) + jitter
            phase += 2 * math.pi * f0 / RATE
            s = sum(_formant_gain(k * f0) / k ** 0.6 * math.sin(k * phase) for k in range(1, 12))
            out.append(s * envelope(t, length, 0.08, 0.18))
        smooth = 0.0
        for i in range(int(0.35 * RATE)):  # gasp for air
            smooth = 0.7 * smooth + 0.3 * (rnd.random() * 2 - 1)
            out.append(0.25 * smooth * math.sin(math.pi * i / (0.35 * RATE)))
    return out


def write(name, samples):
    peak = max(abs(s) for s in samples)
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(32000 * s / peak)) for s in samples))


if __name__ == "__main__":
    write("scream", scream())
    write("baby_cry", baby_cry())
