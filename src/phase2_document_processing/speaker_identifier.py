from typing import Dict, List
from src.config import Config


class SpeakerIdentifier:
    """Assign production roles and TTS voices to speakers.

    Heuristic-based so it works without an LLM call, but the same
    information can be refined by the Director agent at runtime.
    """

    ROLE_HINTS = {
        "host": ["host", "narrator", "anchorman", "anchor", "presenter", "dj"],
        "guest": ["guest", "interviewee", "expert", "panelist", "founder"],
        "support": ["producer", "engineer", "assistant", "sound", "editor"],
    }

    def __init__(self, default_voice: str = None, secondary_voice: str = None):
        self.default_voice = default_voice or Config.DEFAULT_VOICE
        self.secondary_voice = secondary_voice or Config.SECONDARY_VOICE
        self._voice_pool = [
            self.default_voice,
            self.secondary_voice,
            "Kore",
            "Fenrir",
            "Aoede",
            "Zephyr",
        ]

    def identify(self, speakers: List[str], dialogue_segments: List[Dict],
                 voice_overrides: Dict = None) -> List[Dict]:
        """Return a speaker profile list with role and assigned voice.

        voice_overrides maps a speaker name (case-insensitive) to a voice;
        any speaker without an override gets an auto-assigned voice.
        """
        if not speakers:
            return []

        speaking_counts = self._count_utterances(speakers, dialogue_segments)
        sorted_speakers = sorted(speaking_counts.items(), key=lambda x: x[1], reverse=True)

        overrides = {str(k).lower(): v for k, v in (voice_overrides or {}).items()}
        profiles = []
        pool_size = len(self._voice_pool)
        for index, (speaker, utts) in enumerate(sorted_speakers):
            voice = overrides.get(speaker.lower())
            if not voice:
                voice = self._voice_pool[(index * 2) % pool_size]
                if pool_size > 1 and (index * 2) % pool_size != 1:
                    voice = self._voice_pool[(index + 1) % pool_size]
            profiles.append({
                "speaker": speaker,
                "role": self._infer_role(speaker),
                "voice": voice,
                "utterance_count": utts,
                "is_primary": index == 0,
            })
        return profiles

    def assign_voice(self, speaker: str, profiles: List[Dict], voice_overrides: Dict = None) -> str:
        """Look up the voice assigned to a speaker in the profile list.

        An explicit voice_overrides entry wins over the profile assignment.
        """
        overrides = {str(k).lower(): v for k, v in (voice_overrides or {}).items()}
        key = str(speaker).lower()
        if key in overrides:
            return overrides[key]
        for profile in profiles:
            if profile["speaker"].lower() == key:
                return profile["voice"]
        return self.default_voice

    def _count_utterances(self, speakers: List[str], dialogue_segments: List[Dict]) -> Dict[str, int]:
        counts = {s: 0 for s in speakers}
        for segment in dialogue_segments:
            speaker = str(segment.get("speaker", "")).lower().strip()
            if speaker in counts:
                counts[speaker] += 1
        return counts

    def _infer_role(self, speaker: str) -> str:
        low = speaker.lower()
        for role, hints in self.ROLE_HINTS.items():
            if any(hint in low for hint in hints):
                return role
        return "host" if low in ("host",) else "guest"