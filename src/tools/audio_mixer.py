"""Mix a PodCraft production pack into a single episode MP3.

Consumes the same pack ZIP that ``/upload`` builds (production_manifest.json +
per-segment speech WAVs + music bed) and:

  1. orders the segments exactly as they appear in the script (manifest ``index``),
  2. concatenates them in that order,
  3. lays the music bed underneath at a reduced volume (ducking),
  4. writes one combined ``full_episode_.mp3`` and appends it back into the
     pack as ``full_episode.mp3`` so a single ZIP download carries every asset.

MoviePy / ffmpeg are imported lazily (exactly like :mod:`src.video_generator`)
so the API still boots when media dependencies are missing.
"""

import json
import os
import tempfile
import zipfile
from typing import Dict, List, Optional

from src.config import Config
from src.utils.file_handlers import ensure_dirs, stable_token
from src.tools.audio_utils import audio_duration

DEFAULT_MUSIC_VOLUME = 0.15


def volume_from_duck_db(duck_db) -> Optional[float]:
    """Convert a ducking value in dB to a linear bed volume (clamped 0..1).

    Mirrors the video generator: ``10 ** (duck_db / 20)``, e.g. -18 dB -> ~0.126.
    Returns None when the value is not a number so callers can fall back to
    their default volume.
    """
    if isinstance(duck_db, bool) or not isinstance(duck_db, (int, float)):
        return None
    return max(0.0, min(1.0, 10 ** (duck_db / 20)))


def _import_audio_clips():
    from moviepy import AudioFileClip, CompositeAudioClip, concatenate_audioclips

    return AudioFileClip, CompositeAudioClip, concatenate_audioclips


class AudioMixer:
    """Mix speech segments + music bed into one episode MP3."""

    def __init__(self, pack_path: str, music_volume: float = DEFAULT_MUSIC_VOLUME):
        self.pack_path = pack_path
        self.music_volume = music_volume if music_volume is not None else DEFAULT_MUSIC_VOLUME
        self.temp_dir = tempfile.mkdtemp(prefix="podcraft_mix_")

    # -- pack / manifest ----------------------------------------------------

    def extract_pack(self) -> Dict:
        """Extract the pack ZIP to a temp dir and resolve asset paths.

        Returns::

            {
                "segments":   [{"path", "speaker", "index", "order", ...}, ...],
                "music_path": <resolved music bed path or None>,
                "manifest":   {production_manifest.json as parsed dict},
            }

        Paths are re-anchored to the extracted files by basename so the
        manifest's absolute/local paths work inside the container.
        """
        with zipfile.ZipFile(self.pack_path) as zf:
            zf.extractall(self.temp_dir)

        files = {name: os.path.join(self.temp_dir, name) for name in os.listdir(self.temp_dir)}
        manifest_path = files.get("production_manifest.json")
        if not manifest_path or not os.path.exists(manifest_path):
            raise ValueError("Pack has no production_manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        audio = manifest.get("audio_production") or {}
        segments = []
        for entry in audio.get("audio_files") or []:
            path = files.get(os.path.basename(os.path.normpath(entry.get("audio_path") or "")))
            if path and os.path.exists(path):
                segments.append({
                    "path": path,
                    "speaker": entry.get("speaker", "Speaker"),
                    "index": entry.get("index", entry.get("order", 0)),
                    "order": entry.get("order", entry.get("index", 0)),
                })

        music_path = audio.get("music_path")
        music_path = files.get(os.path.basename(os.path.normpath(music_path))) if music_path else None

        return {"segments": segments, "music_path": music_path, "manifest": manifest}

    @staticmethod
    def order_segments(segments: List[Dict]) -> List[Dict]:
        """Order segments by script sequence (manifest ``index``, else ``order``)."""
        return sorted(segments, key=lambda s: s.get("index", s.get("order", 0)))

    # -- mixing -------------------------------------------------------------

    def mix_episode(self, segments: List[Dict], music_path: Optional[str],
                    output_path: str = None) -> str:
        """Concatenate segments (in order) under a ducked music bed -> MP3.

        Skips segment entries whose WAV cannot be loaded. Returns the written
        MP3 path.
        """
        if not segments:
            raise ValueError("No playable audio segments in pack")

        AudioFileClip, CompositeAudioClip, concatenate_audioclips = _import_audio_clips()

        clips = []
        for seg in segments:
            try:
                clips.append(AudioFileClip(seg["path"]))
            except Exception as e:
                print(f"AudioMixer: skipping {seg.get('speaker')} ({e})")
        if not clips:
            raise ValueError("No audio segments could be loaded for mixing")

        voice = concatenate_audioclips(clips)
        total = voice.duration

        if music_path and os.path.exists(music_path):
            try:
                music = AudioFileClip(music_path).with_volume_scaled(self.music_volume)
                bed = music
                if bed.duration < total:
                    repeats = int(total // bed.duration) + 1
                    bed = concatenate_audioclips([music.subclipped(0, bed.duration)] * repeats)
                bed = bed.subclipped(0, total)
                voice = CompositeAudioClip([voice, bed])
            except Exception as e:
                print(f"AudioMixer: music bed skipped ({e})")

        if output_path is None:
            token = stable_token(os.path.basename(self.pack_path))
            output_path = os.path.join(Config.OUTPUT_DIR, f"full_episode_{token}.mp3")
        ensure_dirs(os.path.dirname(output_path))

        voice.write_audiofile(output_path, fps=44100, codec="libmp3lame", logger=None)
        return output_path

    # -- repack -------------------------------------------------------------

    @staticmethod
    def add_to_pack(mp3_path: str, pack_path: str) -> str:
        """Idempotently append the episode MP3 into the pack as full_episode.mp3."""
        with zipfile.ZipFile(pack_path) as zf:
            if "full_episode.mp3" in zf.namelist():
                return pack_path
        with zipfile.ZipFile(pack_path, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.write(mp3_path, "full_episode.mp3")
        return pack_path

    # -- pipeline -----------------------------------------------------------

    def run(self) -> Dict:
        """Extract -> order -> mix -> repack. Returns mp3/pack paths."""
        pack = self.extract_pack()
        segments = self.order_segments(pack["segments"])
        if not segments:
            raise ValueError("Pack contains no speech segments to mix")
        mp3_path = self.mix_episode(segments, pack.get("music_path"))
        pack_path = self.add_to_pack(mp3_path, self.pack_path)
        return {"mp3_path": mp3_path, "pack_path": pack_path, "duration": _measure(mp3_path)}


def _measure(mp3_path: str) -> Optional[float]:
    """Best-effort duration of the mixed MP3 (None if unreadable)."""
    try:
        AudioFileClip, _, _ = _import_audio_clips()
        with AudioFileClip(mp3_path) as clip:
            d = clip.duration
        return round(d, 2)
    except Exception:
        try:
            return audio_duration(mp3_path)
        except Exception:
            return None