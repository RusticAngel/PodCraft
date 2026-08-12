import re
from typing import Dict, List


class ScriptAnalyzer:
    """Higher-level analysis of podcast scripts: structure, sections, tone.

    Simple, dependency-free heuristics that run before the LLM Director
    agent. Results feed into the ADK agents as grounding context.
    """

    SECTION_HINTS = {
        "intro": ["intro", "introduction", "opening", "cold open", "welcome"],
        "segment": ["segment", "section", "part ", "chapter", "topic"],
        "middle": ["welcome back", "next up", "moving on", "let's talk", "discussion"],
        "outro": ["outro", "closing", "wrap-up", "thanks for listening", "tune in next", "goodbye"],
    }

    def __init__(self):
        self.mood_keywords = ['happy', 'sad', 'excited', 'angry', 'calm', 'nervous', 'funny', 'serious']

    def analyze(self, script_data: Dict) -> Dict:
        """Produce a structured analysis dict from parsed script data."""
        full_text = script_data.get("full_text", "")
        segments = script_data.get("dialogue_segments", [])
        speakers = script_data.get("speakers", [])

        structure = self._detect_structure(full_text)
        mood = script_data.get("mood") or self._detect_mood(full_text)
        topics = script_data.get("topics") or self._extract_topics(full_text)

        return {
            "structure": structure,
            "mood": mood,
            "topics": topics,
            "tone_profile": self._tone_profile(full_text),
            "segment_count": len(segments),
            "speaker_count": len(speakers),
            "estimated_duration_minutes": self._estimate_duration(full_text),
            "production_cues": self._production_cues(full_text, structure),
        }

    def _detect_structure(self, text: str) -> Dict[str, List[str]]:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        structure = {key: [] for key in self.SECTION_HINTS}
        for line in lines:
            low = line.lower()
            for section, hints in self.SECTION_HINTS.items():
                if any(hint in low for hint in hints):
                    structure[section].append(line)
                    break
        return structure

    def _production_cues(self, text: str, structure: Dict) -> List[str]:
        cues = []
        if structure.get("intro"):
            cues.append("Music intro under the opening.")
        intro_lines = structure.get("intro", [])
        if intro_lines and any("?" in ln for ln in intro_lines):
            cues.append("Pause for a listener hook after the intro question.")
        if structure.get("outro"):
            cues.append("Fade out music and add a closing CTA.")
        if re.search(r'\([^)]*(laughs|laughing|chuckles)[^)]*\)', text, re.I):
            cues.append("Keep natural laughs; avoid over-editing reactions.")
        if isinstance(structure, dict) and structure.get("middle"):
            cues.append("Add brief music beds between segments.")
        return cues

    def _extract_topics(self, text: str) -> List[str]:
        words = re.findall(r'\b[A-Za-z]{4,}\b', text.lower())
        stopwords = set(
            "about after again against ago all also always am and any are array because been before being "
            "between both but by can could did do does doing down during each few for from further had has "
            "have having he her here hers herself him himself his how however i if in into is it its itself "
            "just like made make may me might more most much must my myself no nor not now of off on once "
            "only or other our ours ourselves out over own same say says she should so some such take than "
            "that the their theirs them themselves then there these they this those through to too under "
            "until up upon us very was we were what when where which while who whom why will with would you "
            "your yours yourself yourselves".split()
        )
        freq = {}
        for w in words:
            if w in stopwords:
                continue
            freq[w] = freq.get(w, 0) + 1
        return [w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:10]]

    def _detect_mood(self, text: str) -> str:
        counts = {m: 0 for m in self.mood_keywords}
        low = text.lower()
        for m in self.mood_keywords:
            counts[m] = low.count(m)
        return max(counts, key=counts.get) if any(counts.values()) else "neutral"

    def _tone_profile(self, text: str) -> Dict[str, int]:
        tones = {"informative": 0, "entertaining": 0, "technical": 0, "conversational": 0}
        informative = re.findall(r'\b(provide|explain|fact|research|study|data|how|why|what)\b', text, re.I)
        entertaining = re.findall(r'\b(fun|funny|laugh|story|joke|wow|amazing|awesome)\b', text, re.I)
        technical = re.findall(r'\b(kernel|model|algorithm|api|system|pipeline|architecture|framework)\b', text, re.I)
        conversational = re.findall(r'\b(so|like|you know|well|actually|right\??|oh)\b', text, re.I)
        tones["informative"] = len(informative)
        tones["entertaining"] = len(entertaining)
        tones["technical"] = len(technical)
        tones["conversational"] = len(conversational)
        return tones

    def _estimate_duration(self, text: str) -> int:
        word_count = len(re.findall(r'\b\w+\b', text))
        return word_count // 150