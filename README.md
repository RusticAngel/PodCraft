# 🎙️ PodCraft — Podcast-to-Production Agent

## Google Cloud Agentic Cinema Hackathon Submission

### Overview

A multi-agent system that converts podcast scripts into complete, production-ready audio episodes in minutes. Built exclusively on Google Cloud AI tools at runtime.

### Features

- 📄 **PDF Script Parsing** - Extract structured data from scripts
- 🎬 **Director Agent** - Analyze structure, tone, and pacing
- 🔍 **Researcher Agent** - Market intelligence via Parallel Search
- 🎵 **Audio Producer Agent** - TTS + Music + Sentiment Analysis
- 🎤 **Multi-Speaker TTS** - Different voices for each speaker
- 🎼 **Background Music** - Mood-matched via Lyria 3
- 📊 **Sentiment Analysis** - Compare script tone vs. audio

### Tech Stack

- **Gemini Enterprise** - Primary AI engine (`google-genai`)
- **Agent Engine (ADK)** - Multi-agent orchestration (`google-cloud-aiplatform[agent_engines,adk]`)
- **Parallel Search** - Web intelligence (free for OpenCode agents)
- **Gemini TTS** - Speech generation
- **Lyria 3** - Music generation
- **Cloud Run** - Deployment
- **FastAPI** - API framework

### Project Structure

```
podcraft/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
├── LICENSE                 # Apache 2.0
├── src/
│   ├── main.py             # FastAPI application
│   ├── config.py           # Environment variables
│   ├── phase2_document_processing/   # PDF parse, speakers, topics, mood
│   ├── phase3_partner_integration/   # Parallel Search API wrapper
│   ├── phase4_adk_agents/            # Director / Researcher / Producer + orchestrator
│   ├── phase5_deployment/            # Cloud Run + Secret Manager
│   ├── tools/                        # Gemini TTS, Lyria 3, sentiment, audio utils
│   ├── models/                       # Pydantic schemas
│   └── utils/                        # File handlers
├── tests/                   # pytest suite (mocked, no keys required)
├── static/demo_script.pdf   # Sample podcast script for demo
├── scripts/make_demo_pdf.py # Generates the demo PDF
└── notebooks/agent_test.ipynb        # ADK testing notebook
```

### How It Works (Media Workflow)

1. **Upload** a podcast script / interview transcript (PDF)
2. **Director Agent** (Gemini) extracts structure, speakers, tone, pacing
3. **Researcher Agent** (Gemini + Parallel Search) gathers market intelligence and comparable podcasts
4. **Audio Producer Agent** generates per-speaker TTS audio (Gemini TTS), mood-matched background music (Lyria 3), and runs multimodal sentiment analysis comparing script tone vs. delivery
5. **Orchestrator** returns a full production pack: script analysis, director notes, market research, audio files, and recommendations

**Problem solved:** podcast production takes 5-10 hours per episode today (scripting, recording, editing, music, mastering). This agent reduces it to ~5 minutes.

### Setup Instructions

1. **Clone the repository**

2. **Add your API keys**
   ```bash
   cp .env.example .env
   # fill in GOOGLE_CLOUD_PROJECT and GEMINI_API_KEY (minimum)
   ```

3. **(Optional) Prepare service credentials for Vertex AI**
   Place a service-account JSON at `./credentials.json` (referenced by `GOOGLE_APPLICATION_CREDENTIALS`). If absent, the app still runs with `GEMINI_API_KEY` when available and returns graceful errors otherwise.

4. **Generate the demo PDF**
   ```bash
   python -m scripts.make_demo_pdf
   ```

5. **Run locally**
   ```bash
   pip install -r requirements.txt
   uvicorn src.main:app --reload
   ```
   Access API at: http://localhost:8000

6. **Run with Docker**
   ```bash
   docker-compose up --build
   ```

### API Endpoints

| Method | Endpoint             | Description                          |
|--------|----------------------|--------------------------------------|
| GET    | `/`                  | Service info                         |
| POST   | `/upload`            | Upload script PDF, run full pipeline |
| POST   | `/analyze`           | Analyze only (no audio)              |
| GET    | `/download/{filename}`| Download generated audio or the production pack |
| GET    | `/health`            | Health check                         |

**Example cURL**
```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@static/demo_script.pdf" \
  -F "genre=technology"
```

**Lite demo mode (`?max_segments=N`)** — render at most N evenly-spaced dialogue segments (always the first and last) to save free-tier TTS quota during demos. Must be passed as a query string:
```bash
curl -X POST "http://localhost:8000/upload?max_segments=3" \
  -F "file=@static/demo_script.pdf" -F "genre=technology"
```

**Audio pack download** — `/upload` also builds `outputs/podcraft_pack_<token>.zip` (manifest + all speech/music WAVs) and returns its `download_url`; each audio segment gets its own `download_url` too. Download with `Content-Disposition: attachment`. Note: Cloud Run is stateless across instances, so run upload + download in one session.

### Running Tests

```bash
pytest -q
```

All tests are mocked and require no API keys.

### Deployment (Cloud Run)

1. Build and push the image to Artifact Registry
2. Create a Secret for `GEMINI_API_KEY` and reference it (see `src/phase5_deployment/secret_manager.py`)
3. Deploy:
   ```bash
   gcloud run deploy podcraft \
     --source . \
     --region us-central1 \
     --set-secrets GEMINI_API_KEY=gemini-key:latest \
     --min-instances=1
   ```
   `--min-instances=1` keeps one warm instance so cold starts don't stall demos, and keeps the container-local `./outputs` (generated WAVs + pack zip) available for `/download`.

### Required API Keys

- **GEMINI_API_KEY** - required for all agent reasoning, TTS, and sentiment; also powers Lyria 3 music (paid tier)
- **Google Cloud project + credentials** - Vertex AI Agent Engine, Secret Manager (optional locally)
- **PARALLEL_API_KEY** - optional; enables live market research (Parallel Search is also free via MCP with no key)

### Demo Video

[Link to YouTube/Video — _add link_]

### Live Demo

The service is deployed on Cloud Run: https://podcraft-347254432482.us-central1.run.app

### License

Apache 2.0