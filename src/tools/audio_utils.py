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
    """Generate a simple mood-tinted ambient WAV as a fallback when no
    music API key is available. Not a replacement for Lyria - just keeps
    the pipeline demo-able without credentials."""
    output_dir = "./outputs"
    os.makedirs(output_dir, exist_ok=True)

    mood_profile = {
        # base_hz, tempo (oscillations min), warm_boost
        "calm": (220.0, 0.4, 1.0),
        "happy": (261.6, 1.2, 1.4),
        "excited": (329.6, 1.8, 1.6),
        "serious": (196.0, 0.5, 0.8),
        "sad": (174.6, 0.3, 0.9),
        "nervous": (261.6, 2.0, 1.1),
        "angry": (146.8, 1.5, 1.3),
        "neutral": (220.0, 0.6, 1.0),
        "funny": (293.7, 1.0, 1.2),
    }
    base_hz, lfo_hz, boost = mood_profile.get(mood, mood_profile["neutral"])

    # Reuse the deterministic hash util to avoid Python hash() randomization.
    from src.utils.file_handlers import stable_token

    seed = int(stable_token(mood + str(duration_seconds)), 16) % (2 ** 32)
    rng = random.Random(seed)

    total = int(sample_rate * duration_seconds)
    samples = []
    for i in range(total):
        t = i / sample_rate
        lfo = 0.5 + 0.5 * math.sin(2 * math.pi * lfo_hz * t)
        amp = 0.04 * boost * lfo
        tone = (math.sin(2 * math.pi * base_hz * t)
                + 0.5 * math.sin(2 * math.pi * base_hz * 0.5 * t)
                + 0.3 * math.sin(2 * math.pi * base_hz * 2.0 * t))
        samples.append(int(16000 * amp * tone + rng.uniform(-40, 40)))

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