"""Generate the sample podcast script PDF (static/demo_script.pdf).

Uses a minimal pure-Python PDF writer so no extra dependencies are needed
(the app itself only uses PyPDF2 for reading). Run from the project root:

    python -m scripts.make_demo_pdf
"""

import os
import zlib

SCRIPT_LINES = [
    "THE FUTURE OF AI STORYTELLING",
    "TECHNOLOGY PODCAST - EPISODE 12",
    "",
    "INT. STUDIO - MORNING",
    "",
    "HOST:",
    "Welcome back to The Creator's Cut! Today we are talking about how",
    "artificial intelligence is completely transforming storytelling, and",
    "I'm so excited to have an amazing guest with us today.",
    "",
    "GUEST:",
    "Thanks for having me, it's a pleasure. AI has truly changed how we",
    "approach narrative design - it is honestly amazing what these models",
    "can now create, from scripts to full audio production.",
    "",
    "HOST:",
    "That is fascinating. Let's talk about the practical side. How does a",
    "creator actually go from a simple idea to a finished episode?",
    "",
    "GUEST:",
    "Great question. The real workflow is recording, editing, music,",
    "mastering - normally that takes hours, if not days. New agent-based",
    "tools are reducing that to minutes, and the results are genuinely",
    "impressive for indie filmmakers and podcasters.",
    "",
    "HOST:",
    "Wow, so what would you recommend to someone just getting started",
    "with AI-assisted production software today?",
    "",
    "GUEST:",
    "Start small. Pick one part of the pipeline - like background music",
    "or voice synthesis - and experiment. The tools are powerful but",
    "understanding the fundamentals still matters a lot.",
    "",
    "OUTRO:",
    "Thanks so much for listening! If you enjoyed this episode, please",
    "subscribe and tune in next week - we have an incredible discussion",
    "lined up on the future of interactive cinema. See you soon!",
]


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(lines, title="Podcast Script Demo"):
    """Return bytes of a one-page text PDF from the given lines."""
    content_lines = ["BT /F1 11 Tf 50 750 Td 14 TL"]
    content_lines.append(f"({_pdf_escape(title)}) Tj")
    content_lines.append("T*")
    for line in lines:
        content_lines.append(f"({_pdf_escape(line)}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines)
    compressed = zlib.compress(stream.encode("latin-1"))

    objects = []

    def add(obj):
        objects.append(str(len(objects) + 1) + " 0 obj\n" + obj + "\nendobj")

    add("<< /Type /Catalog /Pages 2 0 R >>")
    add("<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    add("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>")
    add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    add("<< /Length %d /Filter /FlateDecode >>\nstream\n%s\nendstream" % (len(compressed), compressed.decode("latin-1")))

    pdf = "%PDF-1.4\n"
    offsets = []
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj + "\n"
    xref_start = len(pdf)
    pdf += "xref\n0 %d\n" % (len(objects) + 1)
    pdf += "0000000000 65535 f \n"
    for off in offsets:
        pdf += "%010d 00000 n \n" % off
    pdf += "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objects) + 1, xref_start)
    return pdf.encode("latin-1")


def main() -> str:
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    os.makedirs(static_dir, exist_ok=True)
    out_path = os.path.join(static_dir, "demo_script.pdf")
    with open(out_path, "wb") as f:
        f.write(build_pdf(SCRIPT_LINES))
    print(f"Demo PDF written to {out_path}")
    return out_path


if __name__ == "__main__":
    main()