"""PodCraft Episode Studio — a Streamlit mirror of the Lovable reference design.

Faithfully reproduces the reference "Studio" page (deep ink stage, warm ember
accents, radial stage glow) built on the exact selector data extracted from
the prototype repo (RusticAngel/podcast-perfect):

  * "Pick the vibe"   -> genre list (technology, business, true crime, health,
                         comedy, education, news)
  * "Music & mix"     -> mood presets, intensity + ducking sliders
  * production steps  -> parse / director / research / audio / mix
  * result panels     -> episode card, music bed, recommendations, voice clips

PodCraft extras kept (styled to match): per-speaker Gemini TTS voice choice,
lite-mode segment cap, bundled demos, and video generation.

All backend behaviour is unchanged: vibe -> `genre` param; music & mix ->
`music_mood`, `music_intensity`, `duck_db` query params on /upload.
"""

import os
import json
import time

import requests
import streamlit as st

from src.vibe_mapper import (
    VIBES, MOODS, DEFAULT_VIBE, vibe_options, vibe_by_label, genre_for,
    intensity_label, mood_label_with_hint, gradient_stage, DESIGN,
)
from src.voice_manager import voice_labels, voice_by_label, recommend_for_role

API_BASE = os.getenv("API_BASE", "http://localhost:8080").rstrip("/")

DEMOS = [
    ("static/demo_script.pdf", "🎧 The Remote Work Revolution", "PDF · 2 speakers"),
    ("static/demo_script.txt", "⚽ The Final Whistle", "TXT · 3 speakers"),
]
UPLOAD_EXTS = ["pdf", "txt", "md", "docx"]
MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Proto "In the studio" stage delimiters (ms) drive the cosmetic progress bar.
STEPS = [
    ("parse", "Reading the script", "📄"),
    ("director", "Director's notes", "🗂️"),
    ("research", "Market research", "🔍"),
    ("audio", "Voices & music", "🎚️"),
    ("mix", "Mixing the episode", "✨"),
]
STEP_MILESTONES_MS = [1200, 9000, 20000, 38000]

_THEME_CSS = f"""
<style>
:root {{
  --bg: {DESIGN['bg']};
  --card: {DESIGN['card']};
  --panel: {DESIGN['panel']};
  --fg: {DESIGN['foreground']};
  --muted-fg: {DESIGN['muted_fg']};
  --primary: {DESIGN['primary']};
  --primary-fg: {DESIGN['primary_fg']};
  --accent: {DESIGN['accent']};
  --border: {DESIGN['border']};
  --input: {DESIGN['input']};
  --radius: {DESIGN['radius']};
  --shadow-stage: {DESIGN['shadow_stage']};
}}

html, body, [class*="css"] {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
}}

.stApp {{
  background: {gradient_stage()};
  color: var(--fg);
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none; }}
#MainMenu, footer {{ visibility: hidden; height: 0; }}
.block-container {{ padding-top: 2rem; padding-bottom: 3rem; max-width: 1024px; }}

.stMarkdown, p, li {{ color: var(--fg); }}
[data-testid="stCaptionContainer"], [data-testid="stWidgetLabel"] p {{ color: var(--muted-fg); }}

h1, h2, h3, h4 {{ color: var(--fg); letter-spacing: -0.01em; }}
a {{ color: var(--primary); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

/* ── header ─────────────────────────────────────────────────────────── */
.stage-header {{ display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }}
.logo-tile {{
  display: grid; place-items: center;
  width: 44px; height: 44px; border-radius: 16px;
  background: var(--primary); color: var(--primary-fg);
  font-size: 1.35rem; box-shadow: var(--shadow-stage);
}}
.eyebrow {{ font-size: .68rem; letter-spacing: .22em; text-transform: uppercase; color: var(--muted-fg); margin: 0; }}
.stage-title {{ font-size: 1.35rem; font-weight: 600; color: var(--fg); margin: 0; }}
.hero-text {{ color: var(--muted-fg); font-size: 1.06rem; line-height: 1.55; max-width: 640px; margin: 1.25rem 0 1.6rem; }}

/* ── studio card ────────────────────────────────────────────────────── */
.studio-card {{
  background: color-mix(in srgb, {DESIGN['card']} 70%, transparent);
  border: 1px solid var(--border); border-radius: 1.5rem;
  padding: 1.5rem 1.6rem; box-shadow: var(--shadow-stage);
  backdrop-filter: blur(8px);
}}
.step-row {{ display: flex; align-items: center; gap: .6rem; margin: 0 0 .35rem; }}
.step-num {{
  display: grid; place-items: center; width: 24px; height: 24px;
  border-radius: 50%; background: var(--panel);
  font-size: .72rem; font-weight: 600; color: var(--fg);
}}
.step-title {{ font-weight: 600; font-size: 1rem; color: var(--fg); margin: 0; }}
.hint [[data-testid="stMarkdownContainer"]] p {{ color: var(--muted-fg); font-size: .8rem; }}
.rule {{ height: 1px; background: var(--border); margin: 1.2rem 1.6rem; border: none; }}
.produce-summary {{ color: var(--muted-fg); font-size: .78rem; }}
.btn-cta {{
  background: linear-gradient(135deg, oklch(0.86 0.12 75) 0%, var(--primary) 100%);
  color: var(--primary-fg) !important; font-weight: 600;
  border: none; border-radius: .8rem;
  padding: .68rem 1.35rem; box-shadow: var(--shadow-stage);
  transition: transform .16s ease, box-shadow .16s ease, filter .16s ease;
}}
.btn-cta:hover {{ filter: brightness(1.06); transform: translateY(-1px); }}

/* Streamlit controls styled to token */
[data-testid="stFileUploaderDropzone"] {{
  background: color-mix(in srgb, {DESIGN['card']} 55%, transparent);
  border: 1.5px dashed var(--border) !important;
  border-radius: 1rem !important;
  transition: border-color .18s ease, background .18s ease, transform .18s ease;
}}
[data-testid="stFileUploaderDropzone"]:hover {{
  border-color: var(--primary) !important; background: color-mix(in srgb, var(--primary) 9%, transparent);
  transform: translateY(-1px);
}}
[data-testid="stFileUploaderDropzone"] [data-testid="stMarkdownContainer"] p {{ color: var(--muted-fg) !important; }}
[data-testid="stFileUploaderDropzone"] button {{ background: transparent !important; }}

[data-testid="stSelectbox"] > div > div {{
  background: color-mix(in srgb, {DESIGN['card']} 80%, transparent);
  border: 1px solid var(--border); border-radius: .75rem; color: var(--fg);
}}
[data-testid="stSelectbox"] [data-testid="stWidgetLabel"] p {{ color: var(--fg); }}
div[data-baseweb="popover"] ul {{ background: {DESIGN['panel']}; }}
div[data-baseweb="popover"] li {{ color: var(--fg); }}

[data-testid="stSlider"] [role="slider"] {{ background: var(--primary); border-color: var(--primary); }}
[data-testid="stSlider"] {{ color: var(--muted-fg); }}

.stButton > button, .stDownloadButton > button {{
  border-radius: .75rem; font-weight: 600;
  border: 1px solid var(--border); background: var(--panel);
  color: var(--fg); transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: var(--primary); transform: translateY(-1px); }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
  background: linear-gradient(135deg, oklch(0.86 0.12 75) 0%, var(--primary) 100%);
  color: var(--primary-fg); border: none; box-shadow: var(--shadow-stage);
}}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {{
  filter: brightness(1.06); box-shadow: var(--shadow-stage);
}}

[data-testid="stExpander"] {{ background: color-mix(in srgb, {DESIGN['card']} 55%, transparent);
  border: 1px solid var(--border); border-radius: 1rem; }}
[data-testid="stExpanderHeader"] {{ color: var(--fg); font-weight: 600; }}

[data-testid="stAudio"] audio {{ border-radius: .6rem; }}
[data-testid="stProgress"] [data-testid="stSlider"] [data-testid="stSliderThumbValue"] {{ background: var(--primary); }}

/* ── result panels ─────────────────────────────────────────────────── */
.episode-card {{
  background: color-mix(in srgb, {DESIGN['card']} 80%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary) 32%, transparent);
  border-radius: 1.5rem; padding: 1.5rem 1.6rem; box-shadow: var(--shadow-stage);
  backdrop-filter: blur(8px);
}}
.episode-title {{ font-size: 1.15rem; font-weight: 600; color: var(--fg); margin: 0; }}
.episode-meta {{ color: var(--muted-fg); font-size: .85rem; margin-top: .15rem; }}
.badge {{
  display: inline-flex; align-items: center; gap: .35rem;
  background: var(--panel); border: 1px solid var(--border);
  color: var(--fg); border-radius: 999px; padding: .28rem .7rem; font-size: .78rem;
  margin-right: .45rem; margin-top: .4rem;
}}
.panel-box {{
  background: color-mix(in srgb, {DESIGN['card']} 70%, transparent);
  border: 1px solid var(--border); border-radius: 1.25rem;
  padding: 1.1rem 1.25rem; box-shadow: var(--shadow-stage);
}}
.panel-title {{ display: flex; align-items: center; gap: .5rem; font-size: .9rem; font-weight: 600; margin: 0 0 .85rem; }}
.clip-item {{
  display: flex; align-items: center; justify-content: space-between; gap: .75rem;
  background: var(--panel); border: 1px solid var(--border);
  border-radius: .8rem; padding: .5rem .75rem; margin-bottom: .5rem; font-size: .85rem;
}}
.footnote {{ text-align: center; color: var(--muted-fg); font-size: .74rem; margin-top: 2.5rem; }}
</style>
"""


def _inject_theme() -> None:
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def _mime_for(name: str) -> str:
    return MIME_BY_EXT.get(os.path.splitext(str(name))[1].lower(), "application/octet-stream")


def _api_base() -> str:
    return st.session_state.get("api_base", API_BASE).rstrip("/")


def _api_health() -> dict:
    try:
        resp = requests.get(f"{_api_base()}/health", timeout=5)
        return resp.json() if resp.status_code == 200 else {"status": "unhealthy"}
    except Exception as e:
        raise SystemExit(
            f"Cannot reach the production server at {_api_base()}: {e}"
        ) from e


def _poll_job(job_id: str, timeout_s: int = 1200, poll_s: int = 3) -> dict:
    """Poll a background job; animates the proto-style stage progress."""
    start = time.time()
    bar = st.progress(0, text="Reading the script…")
    pending = st.empty()
    stage = 0
    try:
        while True:
            elapsed_ms = (time.time() - start) * 1000
            new_stage = 1 + sum(1 for m in STEP_MILESTONES_MS if elapsed_ms >= m)
            new_stage = min(max(new_stage, stage), len(STEPS) - 1)
            if new_stage != stage:
                stage = new_stage
                bar.progress(min(95, int((stage + 1) / len(STEPS) * 100)),
                             text=f"{STEPS[stage][2]} {STEPS[stage][1]}…")
            resp = requests.get(f"{_api_base()}/jobs/{job_id}", timeout=10)
            if resp.status_code == 200:
                job = resp.json()
                if job.get("status") == "done":
                    bar.progress(100, text="Episode produced")
                    pending.empty()
                    return job.get("result") or {}
                if job.get("status") == "error":
                    bar.empty()
                    raise RuntimeError(job.get("error") or "Job failed")
            if time.time() - start > timeout_s:
                raise TimeoutError(f"Job {job_id} did not finish in {timeout_s}s")
            time.sleep(poll_s)
    finally:
        bar.empty()


def _start_upload_job(file_bytes, name, genre, max_segments, voice_overrides,
                      music_mood, music_intensity, duck_db):
    files = {"file": (name, file_bytes, _mime_for(name))}
    params = {"genre": genre}
    if max_segments:
        params["max_segments"] = max_segments
    if voice_overrides:
        params["voice_overrides"] = json.dumps(voice_overrides)
    if music_mood:
        params["music_mood"] = music_mood
    if music_intensity is not None:
        params["music_intensity"] = music_intensity
    if duck_db is not None:
        params["duck_db"] = duck_db
    resp = requests.post(f"{_api_base()}/jobs/upload", files=files, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()["job_id"]


def _start_video_job(token):
    resp = requests.post(f"{_api_base()}/jobs/video", params={"token": token}, timeout=30)
    resp.raise_for_status()
    return resp.json()["job_id"]


# ── header components ──────────────────────────────────────────────────────
def _header() -> None:
    c1, c2 = st.columns([1, 8])
    with c1:
        st.markdown('<div class="logo-tile">🎙️</div>', unsafe_allow_html=True)
    with c2:
        st.markdown(
            '<p class="eyebrow">Podcast-to-Production</p>'
            '<p class="stage-title">Episode Studio</p>',
            unsafe_allow_html=True,
        )
    with st.expander("Server"):
        base = st.text_input("Production server address", value=st.session_state.get("api_base", API_BASE),
                             placeholder="http://localhost:8080")
        if base.strip():
            st.session_state["api_base"] = base.strip()


def _speaker_badges(speakers) -> str:
    if not speakers:
        return ""
    badges = "".join(f'<span class="badge">👤 {s}</span>' for s in speakers)
    return f'<div style="margin-top:.6rem">{badges}</div>'


# ── results ────────────────────────────────────────────────────────────────
def _render_results(data: dict, pack_token: str) -> None:
    script = data.get("script_analysis") or {}
    audio = data.get("audio_production") or {}
    research = data.get("market_research") or {}
    meta = data.get("episode_meta") or {}
    title = meta.get("title") or "Your episode"
    clips = audio.get("audio_files") or []
    speakers = script.get("speakers") or []
    music_config = audio.get("music_config") or {}

    st.markdown('<p style="margin-top:1.5rem;font-weight:600">In the studio — done</p>',
                unsafe_allow_html=True)

    st.markdown(
        f'<div class="episode-card">'
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.75rem">'
        f'<div><p class="episode-title">{title}</p>'
        f'<p class="episode-meta">{len(clips)} voice clips · {len(speakers)} speakers'
        f' · ~{script.get("estimated_duration") or "?"} min</p></div>'
        f'<a class="btn-cta" href="{_api_base()}/pack/{pack_token}">⬇️ Download pack</a></div>'
        f'{_speaker_badges(speakers)}</div>',
        unsafe_allow_html=True,
    )

    clips_panel, right = st.columns([1.15, 1], gap="large")
    with clips_panel:
        st.markdown(
            f'<div class="panel-box"><p class="panel-title">🎞️ Voice clips</p>',
            unsafe_allow_html=True,
        )
        for i, entry in enumerate(clips):
            dl = entry.get("download_url")
            if not dl:
                continue
            st.markdown(
                f'<div class="clip-item"><span>{i + 1}. {entry.get("speaker", "Speaker")}'
                f' &middot; {entry.get("voice", "")}</span>'
                f'<a href="{_api_base()}{dl}">⬇️</a></div>',
                unsafe_allow_html=True,
            )
            st.audio(f"{_api_base()}{dl}")
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        def _panel(title, icon, body_html):
            st.markdown(f'<div class="panel-box"><p class="panel-title">{icon} {title}</p>{body_html}</div>',
                        unsafe_allow_html=True)

        music = audio.get("music_path")
        if music:
            name = os.path.basename(os.path.normpath(music))
            _panel(
                "Music bed", "🎵",
                f'<div class="episode-meta" style="margin-bottom:.5rem">'
                f'mood {music_config.get("mood", "auto")} · '
                f'intensity {int(music_config.get("intensity", 0.6) * 100)}%</div>'
                f'<a href="{_api_base()}/download/{name}">⬇️ Download music bed</a>',
            )
            st.audio(f"{_api_base()}/download/{name}")
        else:
            _panel("Music bed", "🎵", '<p class="episode-meta">No music bed generated.</p>')

        recommendations = data.get("recommendations") or []
        if recommendations:
            items = "".join(
                f'<div style="display:flex;gap:.5rem;margin-bottom:.4rem;font-size:.85rem">'
                f'<span style="color:var(--primary)">●</span><span>{r}</span></div>'
                for r in recommendations
            )
            _panel("Recommendations", "🗂️", items)

    st.markdown(
        '<div class="panel-box" style="margin-top:1rem"><p class="panel-title">🎵 Full Episode — one mixed MP3</p>',
        unsafe_allow_html=True,
    )
    if st.button("📥 Export Full Episode (MP3)", type="primary"):
        with st.spinner("Mixing episode… this takes ~10-20 seconds."):
            try:
                resp = requests.post(
                    f"{_api_base()}/export/episode",
                    params={"pack_token": pack_token},
                    timeout=180,
                )
                resp.raise_for_status()
                body = resp.json()
                mp3 = requests.get(f"{_api_base()}{body['mp3_url']}", timeout=120)
                mp3.raise_for_status()
                dur = body.get("duration_seconds")
                st.success(
                    "✅ Full episode exported — every voice clip in script order, "
                    "music ducked under voice." + (f" ({dur}s)" if dur else "")
                )
                st.audio(mp3.content, format="audio/mpeg")
                a, b = st.columns(2)
                a.markdown(
                    f'<a class="btn-cta" href="{_api_base()}{body["mp3_url"]}">⬇️ Episode MP3</a>',
                    unsafe_allow_html=True,
                )
                b.markdown(
                    f'<a class="btn-cta" href="{_api_base()}{body["download_url"]}">⬇️ Updated pack (ZIP)</a>',
                    unsafe_allow_html=True,
                )
            except Exception as e:
                st.error(f"❌ Export failed: {e}")
    else:
        st.markdown(
            '<p class="hint" style="font-size:.8rem">Concatenates every voice clip in script order and '
            "lays the music bed underneath at ducked volume — then adds the MP3 to your pack.</p>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("🎬 Generate video (MP4)", type="primary"):
        try:
            job_id = _start_video_job(pack_token)
            v = _poll_job(job_id, timeout_s=1800, poll_s=5)
            st.success("Video ready!")
            st.video(f"{_api_base()}{v['video_url']}")
            a, b, c = st.columns(3)
            a.markdown(f'<a href="{_api_base()}{v["video_url"]}">⬇️ MP4</a>', unsafe_allow_html=True)
            b.markdown(f'<a href="{_api_base()}{v["mp3_url"]}">⬇️ MP3</a>', unsafe_allow_html=True)
            c.markdown(f'<a href="{_api_base()}{v["srt_url"]}">⬇️ SRT</a>', unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Video generation failed: {e}")

    with st.expander("Full production report (JSON)"):
        st.json(data)


def _start_produce() -> None:
    """Start a produce job and store its id — non-blocking (no poll loop)."""
    try:
        job_id = _start_upload_job(
            st.session_state["file_bytes"],
            st.session_state["file_name"],
            genre_for(st.session_state["vibe_id"]),
            st.session_state.get("max_segments"),
            st.session_state.get("voice_overrides") or None,
            st.session_state.get("music_mood", "auto"),
            st.session_state.get("music_intensity"),
            st.session_state.get("duck_db"),
        )
        st.session_state["active_job"] = job_id
        st.session_state["active_job_kind"] = "produce"
        st.session_state["active_job_started"] = time.time()
    except Exception as e:
        st.error(f"❌ Failed to start production: {e}")


_STAGE_LABELS = {
    "queued": "⏳ Queuing…",
    "voices": "🎙️ Preparing voices…",
    "music": "🎵 Scoring music bed…",
    "sentiment": "🎭 Analysing sentiment…",
    "packaging": "📦 Packaging…",
    "complete": "✅ Done!",
}


@st.fragment(run_every=5)
def _poll_active_job() -> None:
    """Poll the running job and render a live progress banner.

    Each invocation is a short server-side request (~100 ms) that
    re-issues itself every 5 seconds until the job completes.  Because
    the poll lives in a *fragment*, it never holds the main Streamlit
    request open for the full produce duration — the Cloud Run 900 s
    timeout is no longer a concern.
    """
    job_id = st.session_state.get("active_job")
    if not job_id:
        return

    try:
        resp = requests.get(f"{_api_base()}/jobs/{job_id}", timeout=10)
    except Exception:
        st.warning("⚠️ Network blip — retrying…")
        return

    if resp.status_code == 404:
        st.session_state.pop("active_job", None)
        st.session_state.pop("active_job_kind", None)
        st.session_state.pop("active_job_started", None)
        st.warning("⚠️ Production server restarted — your job was lost. Press Produce to retry.")
        return

    if resp.status_code != 200:
        return

    job = resp.json()
    status = job.get("status")

    if status == "done":
        result = job.get("result") or {}
        st.session_state["data"] = result.get("data") or {}
        pack_url = result.get("download_url") or ""
        st.session_state["pack_token"] = pack_url.rsplit("/", 1)[-1].replace(
            "podcraft_pack_", "").replace(".zip", "")
        st.session_state.pop("active_job", None)
        st.session_state.pop("active_job_kind", None)
        st.session_state.pop("active_job_started", None)
        st.rerun()
        return

    if status == "error":
        st.session_state.pop("active_job", None)
        st.session_state.pop("active_job_kind", None)
        st.session_state.pop("active_job_started", None)
        st.error(f"❌ Production failed: {job.get('error', 'Unknown error')}")
        return

    # Still running — render progress banner
    progress = job.get("progress") or {}
    stage = progress.get("stage", "queued")
    done = progress.get("done", 0)
    total = progress.get("total", 0)

    elapsed = int(time.time() - st.session_state.get("active_job_started", time.time()))
    elapsed_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"

    # Progress percentage: voices are the bulk (0-90%), rest is fast (90-100%).
    if total > 0 and "voice" in stage and "/" in stage:
        pct = min(90, int(done / total * 90))
    else:
        pct = {"queued": 5, "voices": 10, "music": 91, "sentiment": 95,
               "packaging": 98, "complete": 100}.get(stage, 50)

    label = _STAGE_LABELS.get(stage) or f"🎙️ {stage}…"
    st.progress(pct, text=f"{label}  ({elapsed_str})")


def main() -> None:
    st.set_page_config(page_title="Episode Studio | Podcast-to-Production", page_icon="🎙️",
                       layout="centered", initial_sidebar_state="collapsed")
    _inject_theme()

    try:
        _api_health()
    except SystemExit:
        st.error(f"Cannot reach the production server at {_api_base()}. "
                 "Start it with:  .venv\\Scripts\\python.exe -m uvicorn src.main:app --port 8080")
        st.stop()

    _header()
    st.markdown(
        '<p class="hero-text">Drop in a script. The studio reads it, writes '
        "director's notes, checks the market, casts AI voices, scores a music bed "
        "and hands you a mixable episode.</p>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="studio-card">', unsafe_allow_html=True)

    # Step 1 — bring your script
    st.markdown('<div class="step-row"><span class="step-num">1</span>'
                '<p class="step-title">Bring your script</p></div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Script file (PDF, TXT, MD, DOCX)", type=UPLOAD_EXTS, label_visibility="collapsed",
    )
    if uploaded is not None:
        st.session_state["file_bytes"] = uploaded.getvalue()
        st.session_state["file_name"] = uploaded.name
        st.session_state.pop("data", None)
    demo_path = None
    if not st.session_state.get("file_name"):
        demos = st.columns(len(DEMOS))
        for col, (path, label, meta) in zip(demos, DEMOS):
            with col:
                if st.button(f"{label}\n\n{meta}"):
                    demo_path = path
    if demo_path:
        with open(demo_path, "rb") as f:
            st.session_state["file_bytes"] = f.read()
        st.session_state["file_name"] = os.path.basename(demo_path)
        st.session_state.pop("data", None)
        st.rerun()

    # Step 2 — pick the vibe
    st.markdown('<div class="step-row" style="margin-top:1.2rem"><span class="step-num">2</span>'
                '<p class="step-title">Pick the vibe</p></div>', unsafe_allow_html=True)
    options = vibe_options()
    st.session_state.setdefault("vibe_id", DEFAULT_VIBE)
    default_index = options.index(next(f"{v['emoji']} {v['name']}" for v in VIBES
                                       if v["id"] == st.session_state["vibe_id"]))
    choice = st.selectbox("Vibe", options, index=default_index, label_visibility="collapsed")
    st.session_state["vibe_id"] = vibe_by_label(choice)["id"]

    # Step 3 — music & mix
    st.markdown('<hr class="rule"/>', unsafe_allow_html=True)
    st.markdown('<div class="step-row"><span class="step-num">3</span>'
                '<p class="step-title">Music &amp; mix</p></div>', unsafe_allow_html=True)
    col_mood, col_sliders = st.columns(2, gap="large")
    with col_mood:
        st.markdown('<p class="hint" style="font-size:.85rem;color:var(--muted-fg)">Mood preset</p>',
                    unsafe_allow_html=True)
        mood_labels = [m["label"] for m in MOODS]
        mood_by_label = {m["label"]: m for m in MOODS}
        mood_index = st.selectbox("Mood preset", mood_labels,
                                  index=0, label_visibility="collapsed")
        _mood = mood_by_label[mood_index]
        st.session_state.setdefault("music_mood", "auto")
        st.session_state["music_mood"] = _mood["value"]
        st.markdown(f'<p class="hint" style="font-size:.8rem">{_mood["hint"]}</p>',
                    unsafe_allow_html=True)
    with col_sliders:
        st.session_state.setdefault("music_intensity", 0.6)
        st.session_state.setdefault("duck_db", -18)
        intensity_pct = st.slider(
            "Intensity", 10, 100, int(st.session_state["music_intensity"] * 100), 5,
            format="%d", help="Subtle → Bold",
        )
        st.markdown(f'<p class="hint" style="font-size:.8rem">{intensity_label(intensity_pct)}</p>',
                    unsafe_allow_html=True)
        st.session_state["music_intensity"] = intensity_pct / 100
        duck = st.slider("Ducking under dialogue", -40, 0, int(st.session_state["duck_db"]), 1,
                         format="%d dB", help="More negative = music barely there")
        st.session_state["duck_db"] = duck

    # Optional advanced: lite segments + per-speaker voices
    with st.expander("⚙️ Advanced — segments & voices"):
        max_segments = st.slider("Render segments (lite quota mode)", 1, 12, 12,
                                 help="Caps the number of TTS segments; free tier allows ~10/day.")
        st.session_state["max_segments"] = max_segments

        if st.button("🔍 Detect speakers & choose voices"):
            try:
                with st.spinner("Reading the script…"):
                    files = {"file": (
                        st.session_state["file_name"],
                        st.session_state["file_bytes"],
                        _mime_for(st.session_state["file_name"]),
                    )}
                    resp = requests.post(f"{_api_base()}/analyze", files=files, timeout=120)
                    resp.raise_for_status()
                    script = resp.json().get("script_analysis") or {}
                st.session_state["speakers"] = script.get("speakers") or []
                st.session_state.pop("data", None)
            except Exception as e:
                st.error(f"❌ Analysis failed: {e}")

        if st.session_state.get("speakers"):
            st.markdown("**Voices per speaker** (auto-cast if left unchanged)")
            labels = voice_labels()
            overrides, used = {}, []
            cols = st.columns(min(2, len(st.session_state["speakers"])))
            for i, speaker in enumerate(st.session_state["speakers"]):
                with cols[i % len(cols)]:
                    suggested = recommend_for_role(speaker, used)
                    default_idx = labels.index(next(
                        l for l in labels if l.split("—")[0].strip().endswith(suggested)))
                    chosen = voice_by_label(st.selectbox(
                        speaker, labels, index=default_idx, key=f"voice_{i}",
                        label_visibility="collapsed"))
                    overrides[speaker] = chosen
                    used.append(chosen)
            st.session_state["voice_overrides"] = overrides

    # Footer + CTA
    mood_label, _ = mood_label_with_hint(st.session_state["music_mood"])
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;'
        f'gap:.9rem;margin-top:1.4rem">'
        f'<p class="produce-summary" style="margin:0">'
        f'{"Mood follows the director’s notes" if st.session_state["music_mood"] == "auto" else f"{mood_label} bed"}'
        f' · {intensity_label(intensity_pct).lower()} · ducked {abs(duck)} dB</p></div>',
        unsafe_allow_html=True,
    )
    if st.button("✨ Produce episode", type="primary", use_container_width=True,
                 disabled=(not st.session_state.get("file_name")
                           or st.session_state.get("active_job"))):
        _start_produce()
    if not st.session_state.get("file_name") and not st.session_state.get("active_job"):
        st.markdown('<p class="hint" style="font-size:.8rem">Drop in a script to enable production.</p>',
                    unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # Live progress banner (runs as a 5-second fragment, never holds the main request)
    if st.session_state.get("active_job"):
        _poll_active_job()

    # Results
    if st.session_state.get("data") and st.session_state.get("pack_token"):
        _render_results(st.session_state["data"], st.session_state["pack_token"])

    if st.session_state.get("data"):
        if st.button("🔄 Start over"):
            st.session_state.clear()
            st.rerun()

    st.markdown(
        '<p class="footnote">Director, researcher and audio-producer agents working from one script. '
        "Built on Gemini, Gemini TTS, Lyria 3, Parallel Search, ADK &amp; MoviePy.</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()