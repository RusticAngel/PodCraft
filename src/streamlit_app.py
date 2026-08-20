"""PodCraft Streamlit Web UI.

Talks to the PodCraft FastAPI backend (API_BASE env var). Supports:
  * PDF upload + genre + segment-count controls
  * one-click "Try the Demo" using the bundled demo PDF (lite mode)
  * video generation from the finished pack
  * downloads (audio pack, video, MP3, SRT, RSS) + audio previews
"""

import os

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://localhost:8080").rstrip("/")
DEMO_PDF = "static/demo_script.pdf"
GENRES = ["technology", "business", "comedy", "education", "health", "sports", "general"]

st.set_page_config(page_title="PodCraft", page_icon="🎙️", layout="wide")

st.markdown("""
<style>
    .main-header { text-align: center; padding: 1.5rem 0; }
    .result-box { border: 1px solid #ddd; border-radius: 10px; padding: 1rem; margin: 0.5rem 0; }
    .metric { font-size: 1.2rem; }
    .hint { color: #b3541e; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)


def _api_health():
    try:
        return requests.get(f"{API_BASE}/health", timeout=5).json()
    except Exception as e:
        st.error(f"Cannot reach API at {API_BASE}: {e}")
        st.info("Start the backend with:  .venv\\Scripts\\python.exe -m uvicorn src.main:app --port 8080")
        st.stop()


def _upload(file_bytes, name, genre, max_segments):
    files = {"file": (name, file_bytes, "application/pdf")}
    params = {"genre": genre}
    if max_segments:
        params["max_segments"] = max_segments
    return requests.post(f"{API_BASE}/upload", files=files, params=params, timeout=180)


def _generate_video(token):
    return requests.post(f"{API_BASE}/video", params={"token": token}, timeout=300)


def _render_result(data, pack_token):
    script = data.get("script_analysis") or {}
    audio = data.get("audio_production") or {}
    research = data.get("market_research") or {}
    meta = data.get("episode_meta") or {}
    title = meta.get("title") or "PodCraft Episode"

    st.markdown(f"## {title}")
    if data.get("status"):
        st.success(f"Production complete ({len(audio.get('audio_files') or [])} segments).")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Speakers", len(script.get("speakers") or []))
    col2.metric("Segments", audio.get("total_segments") or 0)
    col3.metric("Mood", (script.get("mood") or "neutral").title())
    col4.metric("Est. Duration", f"{script.get('estimated_duration', 0)} min")

    if audio.get("lite_mode"):
        st.markdown(
            '<span class="hint">⚡ Lite mode active — only a subset of segments were rendered '
            "to preserve TTS quota.</span>",
            unsafe_allow_html=True,
        )

    with st.expander("🎧 Audio previews"):
        for entry in audio.get("audio_files") or []:
            dl = entry.get("download_url")
            if dl:
                st.audio(f"{API_BASE}{dl}")
                st.caption(f"[{entry['index']}] {entry.get('speaker')} ({entry.get('voice')})")
        if audio.get("music_path"):
            music = os.path.basename(os.path.normpath(audio["music_path"]))
            st.audio(f"{API_BASE}/download/{music}")

    with st.expander("📈 Market research"):
        comparable = research.get("comparable_podcasts") or research.get("market_data") or []
        if comparable:
            st.markdown("**Similar podcasts:**")
            for item in comparable:
                st.markdown(f"- {item}")
        else:
            st.info("No market research available (Parallel API not configured).")

    with st.expander("📄 Production manifest"):
        st.json(data)

    st.markdown("### Downloads")
    dl1, dl2, dl3, dl4 = st.columns(4)
    dl1.markdown(
        f'<a href="{API_BASE}/pack/{pack_token}" class="btn">📦 Audio Pack (ZIP)</a>',
        unsafe_allow_html=True,
    )
    dl2.markdown(f'<a href="{API_BASE}/rss" class="btn">📡 RSS</a>', unsafe_allow_html=True)

    if st.button("🎬 Generate video (MP4)"):
        with st.spinner("Rendering waveform video + MP3 + subtitles..."):
            resp = _generate_video(pack_token)
        if resp.status_code == 200:
            v = resp.json()
            st.success("Video ready!")
            st.video(f"{API_BASE}{v['video_url']}")
            col_v, col_m, col_s = st.columns(3)
            col_v.markdown(f'<a href="{API_BASE}{v["video_url"]}">⬇️ MP4</a>', unsafe_allow_html=True)
            col_m.markdown(f'<a href="{API_BASE}{v["mp3_url"]}">⬇️ MP3</a>', unsafe_allow_html=True)
            col_s.markdown(f'<a href="{API_BASE}{v["srt_url"]}">⬇️ SRT</a>', unsafe_allow_html=True)
        else:
            st.error(f"Video generation failed: {resp.text[:300]}")


def main():
    _api_health()

    st.markdown('<div class="main-header"><h1>🎙️ PodCraft</h1>'
                "<p>AI-Powered Podcast Production — Script to Sound in Minutes</p></div>",
                unsafe_allow_html=True)

    with st.sidebar:
        st.header("⚙️ Settings")
        genre = st.selectbox("Genre", GENRES, index=GENRES.index("technology"))
        max_segments = st.slider(
            "Segments (1 = fastest)",
            min_value=1, max_value=10, value=3,
            help="Lite mode: renders fewer segments to save free-tier TTS quota.",
        )
        st.markdown(f'API: `{API_BASE}`')
        st.caption("Free-tier Gemini TTS allows ~10 generations/day. Cached runs reuse them.")

    st.markdown("---")

    col_btn, col_btn2 = st.columns([1, 1])
    with col_btn:
        uploaded = st.file_uploader("📄 Upload your podcast script (PDF)", type=["pdf"])
    with col_btn2:
        st.markdown("**— or —**")
        try_demo = st.button("🚀 Try the Demo (bundled script)", type="primary")

    file_bytes, file_name = None, None
    if try_demo:
        if os.path.exists(DEMO_PDF):
            with open(DEMO_PDF, "rb") as f:
                file_bytes, file_name = f.read(), os.path.basename(DEMO_PDF)
        else:
            st.error("Demo PDF not found (run `python -m scripts.make_demo_pdf`).")
    elif uploaded is not None:
        file_bytes, file_name = uploaded.getvalue(), uploaded.name

    if file_bytes and (try_demo or st.button("🎙️ Create Podcast", type="primary")):
        if not file_name.lower().endswith(".pdf"):
            st.error("Please upload a PDF file.")
            return
        with st.spinner("🎬 Processing... (60–90s) — parsing, directing, researching, producing"):
            resp = _upload(file_bytes, file_name, genre, max_segments)
        if resp.status_code == 200:
            body = resp.json()
            data = body.get("data") or {}
            pack_url = body.get("download_url") or ""
            pack_token = pack_url.rsplit("/", 1)[-1].replace("podcraft_pack_", "").replace(".zip", "")
            st.session_state["pack_token"] = pack_token
            st.session_state["data"] = data
        else:
            st.error(f"❌ Production failed: {resp.text[:300]}")

    if "data" in st.session_state and st.session_state.get("pack_token"):
        _render_result(st.session_state["data"], st.session_state["pack_token"])

    if st.button("🔄 Start Over"):
        st.session_state.clear()
        st.rerun()

    st.markdown("---")
    st.caption("PodCraft — Built with Gemini, ADK, Parallel Search, Gemini TTS, Lyria 3, MoviePy | "
               "Google Cloud Agentic Cinema Hackathon")


if __name__ == "__main__":
    main()