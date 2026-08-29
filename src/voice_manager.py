"""Voice metadata + assignment helpers for PodCraft's Studio UI.

The selectable voices mirror the Gemini TTS pool in :mod:`src.config`
(``Config.VOICE_POOL``). Each entry carries display metadata (emoji,
tagline, pitch/tempo, style tags) plus a hint about which speaker roles the
voice suits, so the UI can recommend sensible assignments.

Served at GET /voices and consumed by :mod:`src.streamlit_app`. Voice *names*
must stay valid TLS voice names -- they are what the backend passes to
`GeminiTTSTool.generate_speech(text, voice)`.
"""

VOICE_POOL = ["Puck", "Charon", "Kore", "Fenrir", "Aoede", "Zephyr"]

VOICES = [
    {
        "id": "puck",
        "name": "Puck",
        "emoji": "🎙️",
        "tagline": "Deep, confident newsroom anchor",
        "pitch": "low",
        "tempo": "medium",
        "style": ["confident", "authoritative", "news-anchor"],
        "roles": ["host", "narrator"],
    },
    {
        "id": "charon",
        "name": "Charon",
        "emoji": "🧊",
        "tagline": "Calm, resonant storyteller",
        "pitch": "low",
        "tempo": "slow",
        "style": ["calm", "deep", "measured"],
        "roles": ["host", "narrator"],
    },
    {
        "id": "kore",
        "name": "Kore",
        "emoji": "🗣️",
        "tagline": "Warm, clear, engaging host",
        "pitch": "medium",
        "tempo": "medium",
        "style": ["warm", "clear", "engaging"],
        "roles": ["host", "guest"],
    },
    {
        "id": "fenrir",
        "name": "Fenrir",
        "emoji": "🐺",
        "tagline": "Bold, rough-around-the-edges",
        "pitch": "low",
        "tempo": "slow",
        "style": ["bold", "raspy", "intense"],
        "roles": ["guest"],
    },
    {
        "id": "aoede",
        "name": "Aoede",
        "emoji": "🎤",
        "tagline": "Bright, expressive, musical",
        "pitch": "high",
        "tempo": "fast",
        "style": ["bright", "expressive", "dynamic"],
        "roles": ["guest"],
    },
    {
        "id": "zephyr",
        "name": "Zephyr",
        "emoji": "🌬️",
        "tagline": "Soft, youthful and airy",
        "pitch": "high",
        "tempo": "fast",
        "style": ["soft", "youthful", "light"],
        "roles": ["guest"],
    },
]


def get_voice(name: str) -> dict:
    """Return voice metadata by name (case-insensitive), defaulting to Puck."""
    for voice in VOICES:
        if voice["name"].lower() == (name or "").lower():
            return voice
    return VOICES[0]


def voice_names() -> list:
    """Voice names ordered as in VOICES -- the canonical list for the UI/dropdowns."""
    return [v["name"] for v in VOICES]


def voice_labels() -> list:
    """Display labels for selector widgets: 'emoji Name — tagline'."""
    return [f"{v['emoji']} {v['name']} — {v['tagline']}" for v in VOICES]


def voice_by_label(label: str) -> str:
    """Resolve a selector label back to the canonical voice name."""
    label = label.strip()
    for voice in VOICES:
        if voice["name"] in label:
            return voice["name"]
    return voice_names()[0]


def recommend_for_role(role: str, used: list = None) -> str:
    """Suggest the first unused voice that suits a speaker role.

    `role` is any string; matching is loose (substring on host/guest/
    narrator/support). Falls back to the first unused voice overall.
    """
    used = [str(u).lower() for u in (used or [])]
    role = (role or "").lower()
    for voice in VOICES:
        if voice["name"].lower() in used:
            continue
        tags = " ".join(voice.get("roles", []))
        if role in tags:
            return voice["name"]
    for voice in VOICES:
        if voice["name"].lower() not in used:
            return voice["name"]
    return VOICE_POOL[0]


def voice_tag(name: str) -> str:
    """Short one-line descriptor for a voice (for captions / cards)."""
    voice = get_voice(name)
    pitch = voice.get("pitch", "medium")
    tempo = voice.get("tempo", "medium")
    return f"{voice['emoji']} {name} · {pitch.title()} pitch · {tempo.title()} tempo · {voice['tagline']}"