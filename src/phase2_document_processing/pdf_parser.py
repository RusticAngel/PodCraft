import os

import PyPDF2
import re
from typing import Dict, List


class PDFScriptParser:
    """Extract structured data from podcast scripts.

    Accepts PDF, plain text (.txt), Markdown (.md/.markdown) and Word
    (.docx) files; everything after text extraction is format-agnostic.
    """

    # Extensions handled without a PDF library.
    PLAIN_TEXT_EXTS = {".txt", ".md", ".markdown"}
    DOCX_EXTS = {".docx"}

    @classmethod
    def supported_extensions(cls) -> List[str]:
        return sorted(cls.PLAIN_TEXT_EXTS | cls.DOCX_EXTS | {".pdf"})

    # Allows all-caps speaker labels with an optional trailing parenthetical
    # (e.g. "OUTRO (Narrator):"), while excluding common header metadata.
    speaker_pattern = r'^([A-Z][A-Z0-9 ]*(?:\s*\([^)]*\))?):'
    # Also accepts numbered role labels as commonly written by humans,
    # e.g. "Speaker 1 – Host:", "Speaker 2 - Analyst:" (en/em dash or hyphen).
    # The full label ("Speaker 1 – Host") becomes the speaker name.
    speaker_pattern_numbered = r'^(Speaker\s*\d+\s*[‒–—-]\s*[^:\n]{1,60}):'
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

    @classmethod
    def _split_speaker(cls, line: str):
        """Return (label, remaining_text) when the line starts with a
        speaker label, otherwise (None, line).

        Tries the strict ALL-CAPS pattern first, then the numbered
        "Speaker N – Role:" pattern; only the matching pattern is applied.
        """
        match = re.match(cls.speaker_pattern, line)
        if not match:
            match = re.match(cls.speaker_pattern_numbered, line)
        if match:
            return match.group(1), line[match.end():].strip()
        return None, line

    @classmethod
    def _match_speaker(cls, line: str):
        """Return the matched speaker label for a line, or None."""
        return cls._split_speaker(line)[0]

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
        """Extract raw text, dispatching on the file extension."""
        ext = os.path.splitext(str(pdf_path))[1].lower()
        if ext == ".pdf":
            return self._extract_text_pdf(pdf_path)
        if ext in self.PLAIN_TEXT_EXTS:
            return self._extract_text_plain(pdf_path)
        if ext in self.DOCX_EXTS:
            return self._extract_text_docx(pdf_path)
        raise ValueError(
            f"Unsupported script format '{ext or 'unknown'}'. "
            f"Supported: {', '.join(self.supported_extensions())}"
        )

    def _extract_text_pdf(self, pdf_path: str) -> str:
        """Extract raw text from PDF."""
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text

    @staticmethod
    def _extract_text_plain(path: str) -> str:
        """Read a plain-text / Markdown script directly."""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    @staticmethod
    def _extract_text_docx(path: str) -> str:
        """Extract paragraph text from a Word .docx script."""
        try:
            import docx
        except ImportError as exc:
            raise ValueError(
                "DOCX support requires the 'python-docx' package "
                "(pip install python-docx)"
            ) from exc
        document = docx.Document(path)
        return "\n".join(p.text for p in document.paragraphs if p.text.strip())

    def _extract_speakers(self, text: str) -> List[str]:
        """Extract speaker names from script."""
        speakers = []
        for line in text.split('\n'):
            label = self._match_speaker(line)
            if label and self._is_speaker(label):
                speakers.append(label.lower().strip())
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
            label, rest = self._split_speaker(line)
            if label:
                if not self._is_speaker(label):
                    # Metadata header line -> close any open block and skip.
                    flush()
                    current_speaker = None
                    current_dialogue = []
                    continue
                flush()
                current_speaker = label
                current_dialogue = [rest]
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