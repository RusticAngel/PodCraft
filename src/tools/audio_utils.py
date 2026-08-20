import wave
import math
import random
import struct
import os
from typing import Optional, Tuple


def audio_duration(audio_path: str) -> Optional[float]:
    """Return duration in seconds for a WAV file."""
    try:
        import soundfile as sf

        info = sf.info(audio_path)
        return info.frames / info.samplerate
    except Exception:
        try:
            with wave.open(audio_path, "rb") as w:
                return w.getnframes() / w.getframerate()
        except Exception:
            return None


def read_wav_signal(audio_path: str) -> Optional[Tuple[int, int, list]]:
    """Read a WAV into (sample_rate, channels, sample_list)."""
    try:
        with wave.open(audio_path, "rb") as w:
            rate = w.getframerate()
            channels = w.getnchannels()
            n = w.getnframes()
            raw = w.readframes(n)
        if channels == 1:
            samples = struct.unpack("<%dh" % n, raw)
        else:
            samples = []
            all_values = struct.unpack("<%dh" % (n * channels), raw)
            for i in range(0, len(all_values), channels):
                samples.append(sum(all_values[i : i + channels]) // channels)
        return rate, 1, list(samples)
    except Exception:
        return None


def synth_placeholder_wav(mood: str = "calm", duration_seconds: int = 30,
                          sample_rate: int = 44100) -> str:
    """Generate a mood-tinted ambient pad WAV as a fallback when no music
    API key is available. Not a replacement for Lyria - just keeps the
    pipeline demo-able without credentials.

    Designed to sound like a soft background music bed (chord pad with
    gentle tremolo and a fade envelope), NOT static: the tremolo amplitude
    is floored so the tone never drops to zero, and the noise is a faint
    low-passed "air" instead of white static.
    """
    output_dir = "./outputs"
    os.makedirs(output_dir, exist_ok=True)

    # base_hz, tempo (oscillations per min-ish), warm_boost, minor_third
    mood_profile = {
        "calm": (220.0, 0.4, 1.0, False),
        "happy": (261.6, 1.2, 1.4, False),
        "excited": (329.6, 1.8, 1.6, False),
        "serious": (196.0, 0.5, 0.8, True),
        "sad": (174.6, 0.3, 0.9, True),
        "nervous": (261.6, 2.0, 1.1, True),
        "angry": (146.8, 1.5, 1.3, True),
        "neutral": (220.0, 0.6, 1.0, False),
        "funny": (293.7, 1.0, 1.2, False),
    }
    base_hz, lfo_hz, boost, minor = mood_profile.get(mood, mood_profile["neutral"])

    # Reuse the deterministic hash util to avoid Python hash() randomization.
    from src.utils.file_handlers import stable_token

    seed = int(stable_token(mood + str(duration_seconds)), 16) % (2 ** 32)
    rng = random.Random(seed)

    # Chord: root + third + fifth. Third is minor or major depending on mood.
    third_ratio = 2 ** (3 / 12) if minor else 2 ** (4 / 12)
    fifth_ratio = 2 ** (7 / 12)
    notes = [base_hz, base_hz * third_ratio, base_hz * fifth_ratio]

    note_amp = 0.045  # per-note amplitude -> peak roughly -19 dBFS
    total = int(sample_rate * duration_seconds)

    # Fade envelope: smooth attack/release so the pad doesn't click.
    attack_n = int(sample_rate * 1.0)
    release_n = min(int(sample_rate * 1.5), total // 3)

    def envelope(i):
        if i < attack_n:
            t = i / attack_n
            return t * t * (3 - 2 * t)  # smoothstep
        if i >= total - release_n:
            t = (total - 1 - i) / release_n
            return max(0.0, t * t * (3 - 2 * t))
        return 1.0

    # Phase accumulators so the pad stays smooth (no per-sample re-init).
    phases = [[0.0, 0.0] for _ in notes]  # per note: [main osc, detuned osc]
    detune = 0.004  # ~4 cents for a rich, slightly wide pad

    noise_prev = 0.0
    samples = []
    for i in range(total):
        t = i / sample_rate
        env = envelope(i)
        # Tremolo floored between 0.35 and 1.0 -> never silence / static.
        trem = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(2 * math.pi * lfo_hz * t))
        amp = 16000 * note_amp * boost * trem * env

        acc = 0.0
        for idx, freq in enumerate(notes):
            ph1 = phases[idx][0]
            ph2 = phases[idx][1]
            acc += math.sin(ph1) + 0.6 * math.sin(ph2)
            phases[idx][0] = (ph1 + 2 * math.pi * freq / sample_rate) % (2 * math.pi)
            phases[idx][1] = (ph2 + 2 * math.pi * freq * (1 + detune) / sample_rate) % (2 * math.pi)
        # Faint low-passed noise for "air" (brown-noise-ish), not white static.
        noise_prev = 0.85 * noise_prev + rng.uniform(-9, 9)
        samples.append(int(amp * acc + 0.12 * noise_prev))

    filename = f"music_{mood}_{duration_seconds}s_placeholder.wav"
    output_path = os.path.join(output_dir, filename)
    _write_wav(output_path, sample_rate, samples)
    return output_path


def _write_wav(output_path: str, sample_rate: int, samples: list):
    with wave.open(output_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))


def add_silence(audio_path: str, seconds: float = 0.3) -> str:
    """Does nothing if input cannot be read; returns original path otherwise."""
    try:
        info = read_wav_signal(audio_path)
        if not info:
            return audio_path
        rate, _, samples = info
        prefix = int(rate * seconds)
        padded = [0] * prefix + samples
        base = os.path.splitext(audio_path)[0]
        out = f"{base}_padded.wav"
        _write_wav(out, rate, padded)
        return out
    except Exception:
        return audio_path