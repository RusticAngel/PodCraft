"""MoviePy-based video generation for PodCraft.

Consumes the same production pack ZIP that ``/upload`` builds (manifest +
per-segment speech WAVs + music) and renders an MP4 with:
  * a waveform visualization of the full episode mix,
  * the episode title as an opening overlay + pinned at the top,
  * per-segment speaker name banners aligned to each segment's timing,
  * a low-volume music bed under the spoken segments.

Also emits a combined episode MP3 and a timed SRT subtitle file.

MoviePy is imported lazily so the API-only code path still boots when
moviepy/matplotlib are not installed. Text overlays are rendered with
Pillow on numpy frames (no ImageMagick / TextClip dependency).
"""

import json
import os
import tempfile
import zipfile
from typing import Dict, List, Optional

from src.config import Config
from src.utils.file_handlers import ensure_dirs, stable_token
from src.tools.audio_utils import audio_duration

FRAME_WIDTH = 960
FRAME_HEIGHT = 540
FPS = 15
MUSIC_VOLUME = 0.15


def _import_moviepy():
    from moviepy import (
        AudioFileClip,
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        concatenate_audioclips,
    )
    return AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip, concatenate_audioclips


def _import_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    return plt


def _import_pil():
    from PIL import Image, ImageDraw, ImageFont

    return Image, ImageDraw, ImageFont


class PodCraftVideoGenerator:
    """Generate an episode video from a PodCraft production pack ZIP."""

    def __init__(self, pack_path: str, output_path: str = None, title: str = None,
                 burn_subtitles: bool = True):
        self.pack_path = pack_path
        self.title = title or "PodCraft Episode"
        self.burn_subtitles = burn_subtitles
        token = stable_token(os.path.basename(pack_path))
        self.token = token
        self.output_path = output_path or os.path.join(
            Config.OUTPUT_DIR, f"podcast_video_{token}.mp4"
        )
        self._manifest = None

    # -- pack / manifest ----------------------------------------------------

    @property
    def manifest(self) -> Dict:
        if self._manifest is None:
            with zipfile.ZipFile(self.pack_path) as zf:
                self._manifest = json.loads(zf.read("production_manifest.json"))
        return self._manifest

    def _pack_files(self) -> Dict[str, str]:
        """Map basename -> extracted temp path for every file in the pack."""
        tmp = tempfile.mkdtemp(prefix="podcraft_pack_")
        with zipfile.ZipFile(self.pack_path) as zf:
            zf.extractall(tmp)
        return {name: os.path.join(tmp, name) for name in os.listdir(tmp)}

    def _resolve(self, files: Dict[str, str], path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        return files.get(os.path.basename(os.path.normpath(path)))

    def _ordered_segments(self) -> List[Dict]:
        audio = (self.manifest.get("audio_production") or {}).get("audio_files") or []
        return sorted(audio, key=lambda a: a.get("index", 0))

    def _timed_segments(self, files: Dict[str, str]):
        """Return [(start, duration, entry), ...] using real WAV durations."""
        timed = []
        start = 0.0
        for entry in self._ordered_segments():
            path = self._resolve(files, entry.get("audio_path"))
            if not path or not os.path.exists(path):
                continue
            duration = audio_duration(path) or 0.0
            timed.append((start, duration, entry))
            start += duration
        return timed

    def _episode_title(self) -> str:
        analysis = self.manifest.get("script_analysis") or {}
        title = self.title
        if not title or title == "PodCraft Episode":
            genre = analysis.get("genre")
            title = f"{genre.title()} Podcast" if genre else "PodCraft Episode"
        return title

    # -- visual helpers -----------------------------------------------------

    def _waveform_frame(self, samples: List[float]) -> "numpy.ndarray":
        """Render a waveform figure to an RGBA numpy frame (background layer)."""
        import numpy as np

        plt = _import_matplotlib()
        fig, ax = plt.subplots(figsize=(FRAME_WIDTH / 100, FRAME_HEIGHT / 100), dpi=100)
        fig.patch.set_facecolor("#0d1117")
        ax.set_facecolor("#0d1117")
        ax.plot(samples, color="#58a6ff", linewidth=1.2)
        ax.fill_between(
            range(len(samples)), samples, color="#58a6ff", alpha=0.35
        )
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        fig.tight_layout(pad=0)
        fig.canvas.draw()
        frame = np.asarray(fig.canvas.buffer_rgba())
        plt.close(fig)
        return frame

    def _text_frame(self, text: str, font_size: int = 64, bg_alpha: int = 140,
                    text_color: tuple = (255, 255, 255),
                    width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT) -> "numpy.ndarray":
        """Render text centered on a transparent overlay frame via Pillow."""
        import numpy as np

        Image, ImageDraw, ImageFont = _import_pil()
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (width - tw) // 2
        ty = (height - th) // 2

        bar_y = ty - 16
        bar_h = th + 32
        draw.rectangle(
            [0, bar_y, width, bar_y + bar_h], fill=(10, 17, 23, bg_alpha)
        )
        draw.text((tx, ty), text, font=font, fill=text_color + (255,))
        return np.asarray(overlay)

    def _watermark_frame(self) -> "numpy.ndarray":
        import numpy as np

        Image, ImageDraw, ImageFont = _import_pil()
        overlay = Image.new("RGBA", (FRAME_WIDTH, FRAME_HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        try:
            font = ImageFont.truetype("arial.ttf", 26)
        except Exception:
            font = ImageFont.load_default()
        text = "PodCraft"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (FRAME_WIDTH - tw - 20, FRAME_HEIGHT - th - 16),
            text, font=font, fill=(255, 255, 255, 120),
        )
        return np.asarray(overlay)

    def _subtitle_frame(self, text: str, max_chars_per_line: int = 60) -> "numpy.ndarray":
        """Render wrapped subtitle text near the bottom (above the banner)."""
        import numpy as np
        import textwrap

        Image, ImageDraw, ImageFont = _import_pil()
        overlay = Image.new("RGBA", (FRAME_WIDTH, FRAME_HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        try:
            font = ImageFont.truetype("arial.ttf", 34)
        except Exception:
            font = ImageFont.load_default()

        wrapped = textwrap.wrap(text, width=max_chars_per_line) or [""]
        lines = wrapped[:3]  # cap at 3 lines to keep the overlay small
        line_h = 46
        block_h = len(lines) * line_h + 24

        x = 40
        y = FRAME_HEIGHT - 150 - block_h - 12
        draw.rectangle(
            [x - 16, y - 8, FRAME_WIDTH - x + 16, y + block_h + 8],
            fill=(10, 17, 23, 170),
        )
        for i, line in enumerate(lines):
            draw.text((x, y + i * line_h + 4), line, font=font, fill=(240, 240, 240, 255))
        return np.asarray(overlay)

    # -- audio composition --------------------------------------------------

    def _compose_audio(self, files: Dict[str, str], timed: List):
        AudioFileClip, CompositeAudioClip, _, _, concatenate_audioclips = _import_moviepy()
        clips = []
        for start, duration, entry in timed:
            path = self._resolve(files, entry.get("audio_path"))
            if not path or not os.path.exists(path):
                continue
            clips.append(AudioFileClip(path))
        if not clips:
            return None

        voice = concatenate_audioclips(clips)

        music_path = self._resolve(files, (self.manifest.get("audio_production") or {}).get("music_path"))
        if music_path and os.path.exists(music_path):
            try:
                music = AudioFileClip(music_path).with_volume_scaled(MUSIC_VOLUME)
                total = voice.duration
                bed = music
                if bed.duration < total:
                    bed = concatenate_audioclips([music.subclipped(0, bed.duration)] * (int(total // bed.duration) + 1))
                bed = bed.subclipped(0, total)
                voice = CompositeAudioClip([voice, bed])
            except Exception as e:
                print(f"Video: music bed skipped ({e})")

        return voice

    # -- outputs ------------------------------------------------------------

    def _write_mp3(self, audio_clip, episode_path: str) -> str:
        mp3_path = os.path.splitext(episode_path)[0] + ".mp3"
        audio_clip.write_audiofile(mp3_path, fps=44100, logger=None)
        return mp3_path

    def _write_srt(self, timed: List, srt_path: str) -> str:
        def stamp(seconds: float) -> str:
            ms = int(round(seconds * 1000))
            h, rem = divmod(ms, 3600000)
            m, rem = divmod(rem, 60000)
            s, ms = divmod(rem, 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        lines = []
        for i, (start, duration, entry) in enumerate(timed, start=1):
            end = start + max(duration, 0.1)
            speaker = entry.get("speaker", "Speaker")
            text = (entry.get("text") or "").strip()
            if not text:
                text = "..."
            lines.append(f"{i}\n{stamp(start)} --> {stamp(end)}\n{speaker}: {text}\n")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return srt_path

    # -- main ---------------------------------------------------------------

    def generate(self) -> Dict[str, str]:
        """Render the episode video, MP3 and SRT. Returns their paths."""
        import numpy as np

        AudioFileClip, _, CompositeVideoClip, ImageClip, _ = _import_moviepy()
        ensure_dirs(os.path.dirname(self.output_path))

        files = self._pack_files()
        timed = self._timed_segments(files)
        if not timed:
            raise ValueError("No playable audio segments found in pack")

        # 1. Audio mix -> MP3 + drive the video length
        audio = self._compose_audio(files, timed)
        if audio is None:
            raise ValueError("Could not compose episode audio")
        total = audio.duration
        mp3_path = self._write_mp3(audio, self.output_path)

        # 2. Background waveform (baked with the pinned title + watermark)
        title = self._episode_title()
        samples = audio.to_soundarray(fps=44100)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        step = max(1, len(samples) // 4000)
        waveform = self._waveform_frame(samples[::step])

        import numpy as np
        base = waveform
        if base.shape[:2] != (FRAME_HEIGHT, FRAME_WIDTH):
            Image, _, _ = _import_pil()
            base = np.asarray(Image.fromarray(base).resize((FRAME_WIDTH, FRAME_HEIGHT)))

        def _place_overlay(overlay, y=0):
            full = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 4), dtype=np.uint8)
            h = overlay.shape[0]
            y = max(0, min(y, FRAME_HEIGHT - h))
            full[y:y + h, :] = overlay
            return full

        pinned = _place_overlay(
            self._text_frame(title, font_size=40, bg_alpha=100, height=120), y=0
        )
        watermark = self._watermark_frame()
        base = np.where(pinned[..., 3:4] > 0, pinned[:, :, :3], base[..., :3])
        base = np.where(watermark[..., 3:4] > 0, watermark[:, :, :3], base)

        # 3. Pre-render ONE static frame per segment (background + speaker
        #    banner + title intro) and concatenate — avoids per-frame
        #    compositing, which is the slow path in MoviePy.
        intro_seconds = min(4.0, total)
        segment_clips = []
        cursor = 0.0
        for start, duration, entry in timed:
            if duration <= 0:
                continue
            frame = base.copy()
            name = entry.get("speaker", "Speaker")
            banner = _place_overlay(
                self._text_frame(name, font_size=56, height=140),
                y=FRAME_HEIGHT - 150,
            )
            frame = np.where(banner[..., 3:4] > 0, banner[:, :, :3], frame)
            if self.burn_subtitles:
                subtitle = self._subtitle_frame(entry.get("text") or "")
                frame = np.where(subtitle[..., 3:4] > 0, subtitle[:, :, :3], frame)
            if cursor < intro_seconds:
                title_overlay = _place_overlay(
                    self._text_frame(title, font_size=72)
                )
                frame = np.where(title_overlay[..., 3:4] > 0, title_overlay[:, :, :3], frame)
            seg_duration = min(duration, total - cursor)
            clip = ImageClip(frame.astype(np.uint8)).with_duration(seg_duration)
            segment_clips.append(clip)
            cursor += duration

        from moviepy import concatenate_videoclips
        video = concatenate_videoclips(segment_clips)
        video = video.with_audio(audio).with_duration(total)

        video.write_videofile(
            self.output_path,
            codec="libx264",
            audio_codec="aac",
            fps=FPS,
            preset="veryfast",
            threads=4,
            logger=None,
        )
        video.close()

        episode_path = os.path.splitext(self.output_path)[0]
        srt_path = os.path.join(os.path.dirname(self.output_path), os.path.basename(episode_path) + ".srt")
        self._write_srt(timed, srt_path)

        return {
            "video_path": self.output_path,
            "mp3_path": mp3_path,
            "srt_path": srt_path,
        }


def generate_video_from_pack(pack_path: str, output_path: str = None, title: str = None) -> Dict[str, str]:
    """One-call convenience: render a video + mp3 + srt from a pack ZIP."""
    return PodCraftVideoGenerator(pack_path, output_path=output_path, title=title).generate()