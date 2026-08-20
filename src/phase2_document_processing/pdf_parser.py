import PyPDF2
import re
from typing import Dict, List


class PDFScriptParser:
    """Extract structured data from podcast script PDFs."""

    # Allows all-caps speaker labels with an optional trailing parenthetical
    # (e.g. "OUTRO (Narrator):"), while excluding common header metadata.
    speaker_pattern = r'^([A-Z][A-Z0-9 ]*(?:\s*\([^)]*\))?):'
    # Header metadata labels that look like speakers but are not dialogue.
    non_speaker_labels = {
        "format", "topic", "title", "duration", "genre", "summary",
        "episode", "podcast", "guests", "date", "scene", "chapter",
        "int", "ext", "act", "note", "notes", "podcast title", "series",
        "written by", "directed by", "logline", "description",
        "subscribe", "support", "podcast summary", "episode title",
        "series title", "category",
    }
    scene_pattern = r'(INT\.|EXT\.|SCENE|CHAPTER)'
    mood_keywords = ['happy', 'sad', 'excited', 'angry', 'calm', 'nervous', 'funny', 'serious']

    @staticmethod
    def _is_speaker(label: str) -> bool:
        """True if a matched label is a real dialogue speaker, not metadata."""
        key = re.sub(r'\s*\(.*\)', '', label).strip().lower()
        if key in PDFScriptParser.non_speaker_labels:
            return False
        return bool(key)

    def parse(self, pdf_path: str) -> Dict:
        """Extract text and structured data from PDF."""
        text = self._extract_text(pdf_path)

        return {
            "full_text": text,
            "speakers": self._extract_speakers(text),
            "dialogue_segments": self._extract_dialogue_segments(text),
            "topics": self._extract_topics(text),
            "mood": self._detect_mood(text),
            "scene_breaks": self._detect_scene_breaks(text),
            "estimated_duration": self._calculate_duration(text),
        }

    def _extract_text(self, pdf_path: str) -> str:
        """Extract raw text from PDF."""
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text

    def _extract_speakers(self, text: str) -> List[str]:
        """Extract speaker names from script."""
        matches = re.findall(self.speaker_pattern, text, re.MULTILINE)
        speakers = []
        for m in matches:
            if self._is_speaker(m):
                speakers.append(m.lower().strip())
        return list(dict.fromkeys(speakers))

    def _extract_dialogue_segments(self, text: str) -> List[Dict]:
        """Extract dialogue with speaker attribution."""
        segments = []
        lines = text.split('\n')
        current_speaker = None
        current_dialogue = []

        def flush():
            if current_speaker and current_dialogue:
                text_out = ' '.join(current_dialogue).strip()
                if text_out:
                    segments.append({
                        "speaker": current_speaker,
                        "text": text_out,
                    })

        for line in lines:
            speaker_match = re.match(self.speaker_pattern, line)
            if speaker_match:
                label = speaker_match.group(1)
                if not self._is_speaker(label):
                    # Metadata header line -> close any open block and skip.
                    flush()
                    current_speaker = None
                    current_dialogue = []
                    continue
                flush()
                current_speaker = label
                current_dialogue = [re.sub(self.speaker_pattern, '', line).strip()]
            elif current_speaker:
                current_dialogue.append(line.strip())

        flush()
        return segments

    def _extract_topics(self, text: str) -> List[str]:
        """Extract key topics using keyword analysis."""
        words = re.findall(r'\b[A-Za-z]{4,}\b', text)
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
        word_freq = {}
        for word in words:
            w = word.lower()
            if w in stopwords:
                continue
            word_freq[w] = word_freq.get(w, 0) + 1
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:10]]

    def _detect_mood(self, text: str) -> str:
        """Detect overall mood from script."""
        mood_counts = {mood: 0 for mood in self.mood_keywords}
        lower_text = text.lower()
        for mood in self.mood_keywords:
            mood_counts[mood] = lower_text.count(mood)
        return max(mood_counts, key=mood_counts.get) if any(mood_counts.values()) else "neutral"

    def _detect_scene_breaks(self, text: str) -> int:
        """Count scene breaks."""
        matches = re.findall(self.scene_pattern, text)
        return len(matches)

    def _calculate_duration(self, text: str) -> int:
        """Estimate audio duration in minutes."""
        word_count = len(re.findall(r'\b\w+\b', text))
        return word_count // 150  # ~150 words per minute