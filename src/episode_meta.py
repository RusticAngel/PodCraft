"""Episode metadata generation: Gemini episode title + PIL cover art.

Lazy Gemini client + deterministic caching + graceful fallbacks so the
feature works even when keys are missing (matching project conventions).
"""

import os
from typing import Dict, Optional

from src.config import Config
from src.utils.file_handlers import ensure_dirs, stable_token
from src.utils.api_retry import call_with_retry


def generate_episode_title(script_analysis: Dict, genre: str = "general") -> Dict:
    """Return an episode title (+ optional hook) for the production.

    Uses one Gemini call, cached on disk by stable_token of the script text
    so repeated productions don't burn quota. Falls back to a genre-based
    title when Gemini is unavailable.
    """
    full_text = (script_analysis or {}).get("full_text") or ""
    text_key = full_text[:2000] or (script_analysis or {}).get("mood", "podcast")
    cache_path = os.path.join(Config.OUTPUT_DIR, f"title_{stable_token(text_key)}.txt")
    ensure_dirs(Config.OUTPUT_DIR)

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            title = f.read().strip()
        return {"title": title, "method": "cache", "generated_by": "gemini"}

    fallback = _fallback_title(genre, script_analysis)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"title": fallback, "method": "fallback", "generated_by": "heuristic"}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        prompt = (
            "Write a punchy, clickable podcast episode title (max 60 chars, no quotes). "
            "Return ONLY the title text.\n\n"
            f"Genre: {genre}\nScript excerpt:\n{full_text[:1500]}"
        )
        response = call_with_retry(lambda: client.models.generate_content(
            model=Config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["TEXT"]),
        ))
        title = (response.text or "").strip().strip('"')
        if not title:
            title = fallback
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(title)
        return {"title": title, "method": "gemini", "generated_by": "gemini"}
    except Exception as e:
        print(f"Episode title error: {e}")
        return {"title": fallback, "method": "fallback", "generated_by": "heuristic"}


def _fallback_title(genre: str, script_analysis: Dict) -> str:
    mood = (script_analysis or {}).get("mood", "excited")
    label = genre.title() if genre and genre != "general" else "Podcast"
    return f"{mood.title()} {label} Episode"


def generate_cover_art(title: str, mood: str = "excited",
                       output_dir: str = None) -> Optional[str]:
    """Render a 1400x1400 mood-tinted PNG cover for the episode."""
    try:
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        print(f"Cover art error (PIL unavailable): {e}")
        return None

    output_dir = output_dir or Config.OUTPUT_DIR
    ensure_dirs(output_dir)
    cover_path = os.path.join(output_dir, f"cover_{stable_token(title)}.png")

    size = 1400
    mood_colors = {
        "happy": ((255, 200, 80), (255, 120, 40)),
        "excited": ((255, 90, 60), (150, 40, 220)),
        "calm": ((90, 160, 255), (40, 60, 140)),
        "sad": ((90, 110, 160), (30, 35, 70)),
        "serious": ((70, 90, 120), (20, 25, 40)),
        "nervous": ((255, 170, 60), (190, 40, 90)),
        "angry": ((220, 40, 40), (90, 10, 10)),
        "funny": ((255, 230, 100), (255, 140, 40)),
        "neutral": ((110, 120, 160), (30, 34, 48)),
    }
    top, bottom = mood_colors.get(mood, mood_colors["excited"])

    arr = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(size):
        t = y / size
        arr[y, :] = [
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        ]
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    def _font(px):
        try:
            return ImageFont.truetype("arial.ttf", px)
        except Exception:
            return ImageFont.load_default()

    # Title
    title_font = _font(90)
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) // 2, size // 2 - th // 2), title,
              font=title_font, fill=(255, 255, 255))

    # PodCraft brand mark
    brand_font = _font(56)
    brand = "PodCraft"
    bbox = draw.textbbox((0, 0), brand, font=brand_font)
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - bw) // 2, size // 2 - th // 2 + 160), brand,
              font=brand_font, fill=(255, 255, 255, 200))

    img.save(cover_path)
    return cover_path