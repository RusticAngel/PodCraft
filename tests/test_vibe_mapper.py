import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.vibe_mapper import (
    VIBES, GENRES, MOODS, vibe_options, vibe_by_label, genre_for,
    mood_for, get_vibe, intensity_label, DEFAULT_VIBE, DEFAULT_MOOD,
)
from src.voice_manager import VOICES, voice_names, voice_labels, voice_by_label, recommend_for_role


def test_vibe_options_match_prototype_genres():
    labels = vibe_options()
    assert len(labels) == len(GENRES) == 7
    assert set(genre_for(v["id"]) for v in VIBES) == set(GENRES)
    assert all(" " in lbl for lbl in labels)


def test_vibe_by_label_roundtrip():
    for vibe in VIBES:
        assert vibe_by_label(f"{vibe['emoji']} {vibe['name']}")["id"] == vibe["id"]


def test_vibe_maps_to_backend_genre():
    assert genre_for("true crime") == "true crime"
    assert genre_for("technology") == "technology"


def test_unknown_vibe_falls_back_to_default():
    assert get_vibe("does-not-exist")["id"] == DEFAULT_VIBE


def test_moods_match_prototype():
    assert len(MOODS) == 9
    assert MOODS[0]["value"] == "auto"
    assert DEFAULT_MOOD == "auto"  # selector starts on the auto preset
    # genre hint resolves to a valid mood preset
    assert mood_for("technology") in [m["value"] for m in MOODS]


def test_intensity_labels():
    assert intensity_label(10) == "Barely there"
    assert intensity_label(50) == "Gentle"
    assert intensity_label(75) == "Present"
    assert intensity_label(100) == "Bold"


def test_voice_metadata_references_known_pool():
    assert set(voice_names()) == {"Puck", "Charon", "Kore", "Fenrir", "Aoede", "Zephyr"}
    assert len(voice_labels()) == len(VOICES)


def test_voice_by_label_returns_canonical_name():
    assert voice_by_label("🗣️ Kore — Warm, clear, engaging host") == "Kore"


def test_recommend_for_role_prefers_suitable_voice():
    first = recommend_for_role("host")
    assert first in {"Puck", "Charon", "Kore"}
    second = recommend_for_role("guest", used=[first])
    assert second != first