"""Vibe, music and design tokens — an exact match of the Lovable "Episode Studio".

Extracted from the reference prototype (RusticAngel/podcast-perfect, TanStack
frontend). Two selector concepts live here because the prototype defines both:

  * ``VIBES``  -- the "Pick the vibe" selector: a genre master-list. The
    Studio's genre select is exactly ``GENRES`` below; each option is styled
    with the design's warm-ember accent.
  * ``MOODS`` -- the "Mood preset" music selector (value / label / hint).

Also carries the "deep ink stage, warm ember accents" design tokens from the
prototype's ``styles.css`` (``oklch`` values kept verbatim so the Streamlit
clone renders pixel-equivalent, plus display-hex approximations for things
like the Streamlit theme config that require hex).

Served at GET /vibes and consumed by :mod:`src.streamlit_app`.
"""

# ── Design tokens (prototype styles.css, "Studio console palette") ─────────
# oklch strings are used verbatim in CSS; HEX are display-rendered equivalents.
DESIGN = {
    "bg": "oklch(0.17 0.022 275)",
    "bg_hex": "#0D0F19",
    "card": "oklch(0.221 0.024 275)",
    "card_hex": "#171A26",
    "panel": "oklch(0.27 0.026 275)",
    "panel_hex": "#232633",
    "foreground": "oklch(0.96 0.008 90)",
    "foreground_hex": "#F4F2EC",
    "primary": "oklch(0.77 0.16 62)",          # warm ember
    "primary_hex": "#FB9A32",
    "primary_fg": "oklch(0.2 0.03 62)",
    "primary_fg_hex": "#201307",
    "muted": "oklch(0.26 0.024 275)",
    "muted_hex": "#232633",
    "muted_fg": "oklch(0.73 0.02 265)",
    "muted_fg_hex": "#A2A8B5",
    "accent": "oklch(0.68 0.12 195)",          # teal stage light
    "accent_hex": "#00AFAF",
    "border": "oklch(1 0 0 / 12%)",
    "input": "oklch(1 0 0 / 16%)",
    "ring": "oklch(0.77 0.16 62)",
    "radius": "0.875rem",
    "shadow_stage": "0 24px 60px -28px oklch(0 0 0 / 70%)",
    "gradient_stage": (
        "radial-gradient(120% 90% at 12% 0%, "
        "color-mix(in oklab, oklch(0.77 0.16 62) 22%, transparent), transparent 60%),"
        "radial-gradient(100% 80% at 92% 8%, "
        "color-mix(in oklab, oklch(0.68 0.12 195) 18%, transparent), transparent 62%)"
    ),
}


def gradient_stage() -> str:
    """Body background stack from the prototype: stage + ink base."""
    return f"{DESIGN['gradient_stage']}, {DESIGN['bg']}"


def ember_gradient() -> str:
    """One-liner ember accent gradient for highlights/CTAs."""
    return "linear-gradient(135deg, oklch(0.82 0.14 70) 0%, oklch(0.77 0.16 62) 100%)"


# ── Vibe selector -- the prototype's "Pick the vibe" genre list ────────────
GENRES = [
    "technology",
    "business",
    "true crime",
    "health",
    "comedy",
    "education",
    "news",
]

_EMOJI_BY_GENRE = {
    "technology": "💻",
    "business": "💼",
    "true crime": "🕵️",
    "health": "💚",
    "comedy": "😄",
    "education": "🎓",
    "news": "📰",
}

# Default backend mood each genre tends toward, used only as a hint.
_DEFAULT_MOOD_BY_GENRE = {
    "technology": "neutral",
    "business": "serious",
    "true crime": "nervous",
    "health": "calm",
    "comedy": "funny",
    "education": "calm",
    "news": "serious",
}

VIBES = [
    {
        "id": genre,
        "name": genre.title(),
        "emoji": _EMOJI_BY_GENRE.get(genre, "🎙️"),
        "colors": [DESIGN["primary"], DESIGN["primary"]],
        "accent": DESIGN["primary"],
        "description": f"{genre.title()} conversation",
        "genre": genre,  # identity: the vibe IS the backend genre
        "mood": _DEFAULT_MOOD_BY_GENRE.get(genre, "neutral"),
        "keywords": [genre],
    }
    for genre in GENRES
]

DEFAULT_VIBE = "technology"


# ── Music mood presets -- the prototype's "Mood preset" selector ───────────
MOODS = [
    {"value": "auto", "label": "Auto (match the script)",
     "hint": "The director picks a bed from the script's tone."},
    {"value": "calm", "label": "Calm", "hint": "Ambient pads, gentle and unobtrusive."},
    {"value": "happy", "label": "Warm & upbeat", "hint": "Acoustic bed with light percussion."},
    {"value": "excited", "label": "Energetic", "hint": "Electronic pulse with drive."},
    {"value": "serious", "label": "Documentary", "hint": "Restrained, steady strings."},
    {"value": "nervous", "label": "Suspenseful", "hint": "Sparse pulse and muted plucks."},
    {"value": "sad", "label": "Reflective", "hint": "Melancholic solo piano."},
    {"value": "funny", "label": "Playful", "hint": "Ukulele and handclaps."},
    {"value": "neutral", "label": "Neutral lo-fi", "hint": "Soft instrumental bed."},
]

DEFAULT_MOOD = "auto"

# Music mix controls (slider defaults from the prototype)
INTENSITY_MIN, INTENSITY_MAX, INTENSITY_DEFAULT, INTENSITY_STEP = 10, 100, 60, 5
DUCK_MIN, DUCK_MAX, DUCK_DEFAULT, DUCK_STEP = -40, 0, -18, 1


def intensity_label(value: int) -> str:
    """Map an intensity slider value to its descriptive label (prototype)."""
    if value <= 25:
        return "Barely there"
    if value <= 50:
        return "Gentle"
    if value <= 75:
        return "Present"
    return "Bold"


def mood_label(mood: str) -> str:
    return mood_label_with_hint(mood)[0]


def mood_label_with_hint(mood: str):
    for m in MOODS:
        if m["value"] == mood:
            return m["label"], m["hint"]
    return mood, ""


# ── Lookups (stable API for the UI + /vibes endpoint) ──────────────────────
def get_vibe(vibe_id: str) -> dict:
    for vibe in VIBES:
        if vibe["id"] == vibe_id:
            return vibe
    return get_vibe(DEFAULT_VIBE)


def vibe_options() -> list:
    """Display labels for selector widgets: 'emoji name'. Ordered as GENRES."""
    return [f"{v['emoji']} {v['name']}" for v in VIBES]


def vibe_by_label(label: str) -> dict:
    label = label.strip()
    for vibe in VIBES:
        if label.endswith(vibe["name"]):
            return vibe
    return get_vibe(DEFAULT_VIBE)


def genre_for(vibe_id: str) -> str:
    """The backend genre a vibe maps to (identity for this selector)."""
    return get_vibe(vibe_id).get("genre", DEFAULT_VIBE)


def mood_for(vibe_id: str, fallback: str = "neutral") -> str:
    return get_vibe(vibe_id).get("mood", fallback)


def accent_for(vibe_id: str) -> str:
    return get_vibe(vibe_id).get("accent", DESIGN["primary"])