# PodCraft — Devpost Submission Draft

## Elevator Pitch

**PodCraft** is a multi-agent podcast production studio that turns a script PDF into a finished episode in minutes — multi-speaker TTS audio, mood-matched background music, sentiment analysis, market research, and a publishable video episode — all powered by Google Cloud AI.

## Project Story

### The Problem
Producing a single podcast episode takes 5–10 hours: scripting, recording each speaker, editing, sourcing or composing music, mixing, and mastering. Indie podcasters, audiobook producers, and indie filmmakers simply don't have that time or a full production team.

### The Solution
PodCraft replaces that manual pipeline with an agentic system. Upload a script or interview transcript as a PDF and PodCraft:

1. **Parses** the script, extracting speakers, dialogue segments, topics, mood, and structure.
2. **Directs** — a Gemini-powered Director Agent analyzes structure, tone, and pacing, and assigns production cues.
3. **Researches** — a Researcher Agent grounds production decisions in real-time market data via the Parallel Search API.
4. **Produces** — an Audio Producer Agent generates per-speaker speech with Gemini TTS, a mood-matched background music bed with Lyria 3, and runs multimodal sentiment analysis comparing script tone vs. delivered audio.
5. **Reports** — an orchestrator returns a full production pack: script analysis, director notes, market intelligence, audio assets, and actionable recommendations.
6. **Ships** — a Streamlit web UI gives one-click demos, audio previews, and downloads; MoviePy renders a waveform MP4 with speaker banners, a combined MP3, and SRT subtitles; an RSS feed makes each episode immediately publishable.

### How It's Built
- **Gemini (Google Cloud)** — all agent reasoning (`gemini-3.5-flash`), speech generation (`gemini-2.5-flash-preview-tts`), and sentiment analysis
- **Google Cloud Agent Engine (ADK)** — multi-agent orchestration via `google-cloud-aiplatform[agent_engines,adk]`. Agents run through heuristic `_fallback()` when Agent Engine credentials (`GOOGLE_CLOUD_PROJECT`) are absent; the ADK wiring is in place for production-scale deployment.
- **Lyria 3** — background music generation (`lyria-3-clip-preview`)
- **Parallel Search API** — real-time market research
- **Cloud Run** — serverless deployment; **Secret Manager** — runtime key management
- **FastAPI** — REST API; **Docker** — containerized runtime
- **Streamlit** — web UI (`src/streamlit_app.py`)
- **MoviePy** — video generation: waveform MP4, combined MP3, SRT subtitles (`src/video_generator.py`)
- **Gemini episode metadata** — episode title + mood-tinted cover art (`src/episode_meta.py`)

### What's Next
- Full multi-voice mixdown with ducking and fades
- Lyria 3 Pro for full-length scored episodes
- Persistent audio storage (GCS) so downloads survive Cloud Run instance churn

## Built With

| Technology | Role |
|---|---|
| Gemini Enterprise | Agent reasoning, TTS, sentiment analysis |
| Google Cloud Agent Engine (ADK) | Multi-agent orchestration |
| Lyria 3 | Music generation |
| Parallel Search API | Market research |
| Google Cloud Run | Deployment |
| Google Cloud Secret Manager | API key management |
| FastAPI / Docker | API + containerization |
| Streamlit | Web UI |
| MoviePy | Video generation (MP4/MP3/SRT) |

## Links

- GitHub Repo: https://github.com/RusticAngel/PodCraft
- Live Demo URL (Cloud Run): https://podcraft-347254432482.us-central1.run.app
- Demo Video: _add YouTube link here_
