# AGENTS.md — PodCraft Memory / Context

Session memory for AI coding agents working on this repo. Rebuilds context lost between sessions (agent context was cleared).

## What this project is

**PodCraft** — a multi-agent podcast production system for the **Google Cloud Agentic Cinema Hackathon** (Devpost submission, see `docs/devpost.md`). Upload a podcast script PDF → get a full production pack: parsed script, director notes, market research, per-speaker TTS audio files, mood-matched background music, sentiment analysis, and recommendations — plus an optional video episode (MP4/MP3/SRT) via a Streamlit web UI.

Built exclusively on Google Cloud AI at runtime:
- **Gemini** (`gemini-3.5-flash`) — agent reasoning + sentiment
- **Gemini TTS** (`gemini-2.5-flash-preview-tts`) — multi-voice speech
- **Lyria 3** (`lyria-3-clip-preview`) — background music (paid tier; falls back to a synth WAV otherwise)
- **Parallel Search API** — market research (free via MCP, optional key)
- **Vertex Agent Engine / ADK** — multi-agent orchestration
- **FastAPI + Docker** — API / deployment
- **Cloud Run + Secret Manager** — deployment (phase5)

## Environment & Setup (Windows 11, PowerShell)

- **Repo root**: `C:\Victor\Projects\Agentic Cinema\podcraft`
- **Python venv**: `.venv` exists. Use `.venv\Scripts\python.exe` (NOT bare `python`) for everything.
- **Env file**: `.env` (gitignored) + `.env.example`. Loaded via `python-dotenv` in `src/config.py` (auto `load_dotenv()`).
- **Verified working (2026-08-20)**:
  - ADK installed: `google-cloud-aiplatform` 1.163.0, `google-genai` 2.17.0, `import google.adk` → v2.6.3
  - Install cmd: `.venv\Scripts\python.exe -m pip install "google-cloud-aiplatform[agent_engines,adk]>=1.101.0"`
  - `GEMINI_API_KEY` set in `.env` (len 53, prefix `AQ.`). **NOT** set as a shell env var — always load `.env` (dotenv) before live calls.
  - **Key history**: old `AQ.Ab8RN6KUPMf...` → 401 UNAUTHENTICATED (invalid). `AQ.Ab8RN6KKe3M8s6Z...Tepg` → authenticates but 429 "prepayment credits are depleted" (was on project `podcraft-505309`, Tier 1 Postpay). Current `AQ.Ab8RN6KgXI...` → **WORKS and is on the FREE TIER** (per user, confirmed 2026-08-20). Free tier: RPD resets **midnight Pacific**; limits per project, not per key; TTS (`gemini-2.5-flash-preview-tts`) hard-caps at **10 req/day**; **Lyria has NO free tier** (placeholder music fallback stays). Failed/429 requests count toward daily quota — be economical.
  - Free-tier facts (in case of new project): RPD resets **midnight Pacific**; limits are per project, not per key; TTS (`gemini-2.5-flash-preview-tts`) caps at **10 req/day** on free tier; **Lyria has NO free tier** (paid only, $0.04/song). Failed requests count toward quota.
  - Live Gemini call verified: `from google import genai; genai.Client().models.generate_content(model='gemini-3.5-flash', contents='Hello')` works.
  - `GOOGLE_CLOUD_PROJECT` is **NOT** set in `.env` → `uses_agent_engine` is False → agents run in heuristic **fallback** mode. This is intentional/graceful.

### Useful commands
```powershell
.venv\Scripts\python.exe -m pytest -q                          # tests (16 pass, all mocked, no keys needed)
.venv\Scripts\python.exe -m scripts.make_demo_pdf              # regenerate static\demo_script.pdf
.venv\Scripts\python.exe -m uvicorn src.main:app --reload      # run API locally
powershell -ExecutionPolicy Bypass -File scripts\test_api.ps1  # full API smoke test (starts/stops server)
```

## Architecture

```
src/
├── main.py                        # FastAPI app: / , /upload, /analyze, /download/{f}, /health
├── config.py                      # Config class; reads .env (PROJECT_ID, GEMINI_API_KEY, GEMINI_MODEL,
│                                  #   GEMINI_TTS_MODEL, LYRIA_MODEL, PARALLEL_API_KEY, DEFAULT/SECONDARY_TTS_VOICE)
├── phase2_document_processing/
│   ├── pdf_parser.py              # PDFScriptParser: extracts full_text, speakers (regex "SPEAKER:"), dialogue_segments,
│   │                              #   topics (word freq), mood (keyword counts), scene_breaks, estimated_duration (words//150)
│   ├── script_analyzer.py         # ScriptAnalyzer: structure (intro/segment/middle/outro hints), production_cues, tone_profile
│   └── speaker_identifier.py      # SpeakerIdentifier: role inference + voice assignment (voice pool Puck/Charon/Kore/Fenrir/Aoede/Zephyr)
├── phase3_partner_integration/
│   └── parallel_search.py         # ParallelResearchTool: SDK or HTTP client for search.parallel.ai; .configured; graceful error dicts
├── phase4_adk_agents/             # ★ the agent layer
│   ├── base_agent.py              # BaseAgent(ABC): lazy Vertex init (_init_vertex), uses_agent_engine, create_agent(),
│   │                              #   _coerce_config (Builds ReasoningEngine.from_config first, falls back to google.adk Agent)
│   ├── director_agent.py          # DirectorAgent: analyzes structure/tone/pacing (_analyze_structure tool)
│   ├── researcher_agent.py        # ResearcherAgent: market research (_search_podcast_market -> ParallelResearchTool)
│   ├── audio_producer_agent.py    # AudioProducerAgent: TTS + Lyria + sentiment (_produce_audio), max_segments lite mode
│   └── orchestrator.py            # PodcastOrchestrator.process_script(pdf_path, genre, max_segments)
├── phase5_deployment/
│   ├── secret_manager.py          # SecretManagerClient: env var first, then Secret Manager
│   └── cloud_run.py               # service_yaml() / image_tag() / deploy_cmd()
├── streamlit_app.py               # Web UI: upload/demo, previews, video gen, downloads (API_BASE env)
├── video_generator.py             # MoviePy 2.x: waveform MP4 + combined MP3 + SRT from a pack ZIP
├── episode_meta.py                # Gemini episode title (cached) + PIL cover art
├── tools/
│   ├── gemini_tts.py              # GeminiTTSTool.generate_speech(text, voice) -> WAV path; PCM->WAV wrapping; disk cache
│   ├── lyria_music.py             # LyriaMusicTool.generate_music(mood, duration) -> path; placeholder fallback
│   ├── sentiment_analyzer.py      # SentimentAnalyzerTool.analyze_sentiment(text) -> dict; lexical fallback
│   └── audio_utils.py             # audio_duration, read_wav_signal, synth_placeholder_wav (mood-tinted), add_silence
├── models/schemas.py              # Pydantic: ScriptRequest, UploadResponse, AnalyzeResponse, ProcessResponse, HealthResponse…
└── utils/
    ├── api_retry.py               # call_with_retry(fn, retries=4, backoff+jitter); is_rate_limit() detects 429/RESOURCE_EXHAUSTED
    └── file_handlers.py           # stable_token (md5, deterministic), safe_filename, ensure_dirs, safe_join (path traversal guard)
```

### Key patterns / conventions
- **Lazy clients everywhere**: `_get_client()` creates the `genai.Client` on first use; `_init_vertex()` for Vertex. App must boot without keys.
- **Graceful fallbacks everywhere**: every agent's `run()` catches exceptions and falls back to a deterministic local `_fallback()`; tools return `None`/error dicts instead of raising when keys are missing.
- **`call_with_retry` around every live API call** (TTS, Lyria, sentiment) — free-tier Gemini quota resets per minute and 429s are hit regularly.
- **TTS disk caching** in `gemini_tts.py`: cache key `stable_token(text, voice)` → `outputs\speech_{token}.wav`. Re-running consumes zero quota. Verified: repeated runs return "TTS: using cached audio".
- **Agent fallback chain**: `uses_agent_engine` is False when `GOOGLE_CLOUD_PROJECT` missing. Agents then call `self._fallback(payload)` which runs the registered tool function directly (web/API calls still work via the tools).
- Pipeline dict contract (see `orchestrator.process_script` return): `script_analysis`, `speaker_profiles`, `director_notes`, `market_research`, `audio_production`, `recommendations`, `status`.
- Output files go to `./outputs`; uploads to `./uploads` (both gitignored). WAV wrapping: Gemini TTS returns `audio/L16` PCM → wrapped to mono 16-bit WAV at 24kHz.

### Lite demo mode (`max_segments`) — NEW, in-progress feature
`process_script(pdf_path, genre, max_segments=None)` → `AudioProducerAgent.run(..., max_segments)` → `_produce_audio` calls `_pick_segments(segments, max_segments)`:
- `None` or `>= len(segments)` → use all segments.
- Otherwise picks `n` evenly-spaced segments, ALWAYS including first + last, preserving speaker diversity.
- Returns `original_indices` so audio entries keep their true segment index.
- Adds `lite_mode: bool` to production output (True when truncated).

Purpose: preserve free-tier daily TTS quota during demos (Lyria is hard-quota'd at 0 on free tier → ALWAYS falls back to `synth_placeholder_wav`; verified live).

### Video generation (`src/video_generator.py`) — v2, added 2026-08-19
`PodCraftVideoGenerator(pack_path, output_path=None, title=None)` + `generate_video_from_pack()`:
- Consumes the `/upload` pack ZIP (`production_manifest.json` + WAVs).
- MoviePy **2.x** imports (`from moviepy import AudioFileClip, ...`) — do NOT use `moviepy.editor` (removed in 2.x). `TextClip` needs ImageMagick → all text is rendered with **PIL** on numpy frames.
- Per-segment timing from real WAV durations (`audio_duration`); concatenated speech + low-volume (0.15) music bed → drives MP4 length and the combined MP3.
- **Perf (important)**: per-frame `CompositeVideoClip` compositing was ~400–600s for a 38s episode. Fix: pre-render ONE static frame per segment (background + speaker banner + intro title) then `concatenate_videoclips` → ~70s. Frame is 960x540 @ 15fps.
- Outputs `outputs/podcast_video_<token>.mp4/.mp3/.srt` (token = `stable_token(pack_basename)`).
- `burn_subtitles=True` (default): renders each segment's text (wrapped, up to 3 lines) above the speaker banner via `_subtitle_frame`.
- `POST /video?token=<pack_token>` in `main.py` runs it and appends MP4/MP3/SRT back into the pack; `GET /pack/{token}` downloads a pack; `GET /rss` serves an RSS feed of latest packs (`PUBLIC_BASE_URL` env for enclosure URLs). `_add_to_pack()` appends artifacts to an existing zip.
- `scripts/make_reel.ps1` renders a reel from the latest (or a given) pack WITHOUT a server, zero TTS quota (cached audio).

### Background jobs & blocking endpoints (added 2026-08-19)
- `/upload`, `/video`, `/analyze` are **sync `def`** (FastAPI runs them in a threadpool) — they were `async def` calling blocking code, which stalled the event loop. Light endpoints (`/`, `/health`, `/download`, `/pack`) stay `async`.
- `_process_pipeline(upload_path, genre, max_segments)` and `_run_video_job(token, title)` are the shared core functions used by both the sync endpoints and the background jobs.
- `POST /jobs/upload` + `POST /jobs/video` start work on a daemon thread via `_submit_job`; `GET /jobs/{id}` returns `{status: running|done|error, result, error, token}`. In-memory `_JOBS` dict guarded by `_JOBS_LOCK`. Streamlit UI polls these instead of holding a single long request.
- `_JOBS` is in-memory → job state does not survive a restart (fine for a demo; GCS + a real queue is the post-hackathon upgrade).

### Episode metadata (`src/episode_meta.py`) — v2, added 2026-08-19
- `generate_episode_title(script_analysis, genre)` — one Gemini call, cached at `outputs/title_<token>.txt`; falls back to a heuristic title without keys.
- `generate_cover_art(title, mood, output_dir)` — 1400x1400 mood-tinted PNG via PIL; no external art API.
- `/upload` stores this under `result["episode_meta"]` and adds the cover to the pack.

### Per-speaker voice selection + animated video (added 2026-08-20)
- **Voice overrides**: `POST /upload` + `POST /jobs/upload` accept a `voice_overrides` query param — JSON object mapping speaker names (case-insensitive) to a voice from `Config.VOICE_POOL` (`["Puck","Charon","Kore","Fenrir","Aoede","Zephyr"]`). `_parse_voice_overrides()` validates it (400 on bad JSON/unknown voice). Threaded through `_process_pipeline` → `process_script` → `AudioProducerAgent.run/_produce_audio` → `SpeakerIdentifier.identify()/assign_voice()` (override wins over auto-assignment). Streamlit UI: "Analyze script & pick voices" step lists detected speakers with a voice dropdown each, sends `voice_overrides` on Create Podcast.
- **Animated video** (`video_generator.py`): the background waveform now has a **time-synced playhead** (white vertical line) + a translucent **band highlight over the currently-speaking segment**, and the speaker banner is **color-coded per speaker** (`_speaker_color`, deterministic hash of name). Pre-renders all overlays once (`_segment_plan`) then composes per-frame with pure numpy (`_frame_at` via MoviePy `VideoClip(make_frame)`) — no per-frame matplotlib/text rendering, so render stays fast. `_waveform_frame` now uses zero-margin axes so x-axis maps linearly to time (playhead accuracy).
- **Tests (42 pass)**: override-aware identify/assign_voice, producer honors overrides, endpoint accepts/rejects overrides, playhead position + segment plan x-mapping. Verified live: playhead tracks HOST→GUEST→OUTRO across the 76.8s reel.

### Web UI (`src/streamlit_app.py`) — v2, added 2026-08-19
- `API_BASE` env (default `http://localhost:8080`) — prod Cloud Run URL is an override, never hardcoded.
- Controls: genre select, `max_segments` slider (1–10, default 3), "Try the Demo" (bundled `static/demo_script.pdf`, cached TTS), upload PDF, "Create Podcast", results with metrics/audio previews/market research/manifest, video generation, download links, Start Over.
- Config in `.streamlit/config.toml` (dark theme, headless). Local run: `streamlit run src/streamlit_app.py`.
- docker-compose has TWO services: `api` (8080) + `ui` (8501, `API_BASE=http://api:8080`). Cloud Run: separate `podcraft-api` + `podcraft-ui` services.

## Tests (all mocked, no keys)
- `tests/test_pdf_parser.py` — parsing, dialogue segments, duration, ScriptAnalyzer, SpeakerIdentifier voice/role assignment
- `tests/test_agents.py` — Director/Researcher/Producer fallbacks, orchestration E2E via `build_pdf`, placeholder WAV
- `tests/test_parallel_api.py` — Parallel tool configured/not-configured, query building, result normalization
- `tests/test_video_generator.py` — pack manifest parsing, episode title fallback, cover art, moviepy-missing ImportError guard
- `tests/test_api_endpoints.py` — TestClient tests: health/root, non-PDF rejection, analyze, background job upload+poll, job 404, RSS well-formedness + escaping, pack download
- **32 pass, 2 deprecation warnings** (PyPDF2 → pypdf; Starlette TestClient httpx — both not urgent). Some tests write real WAVs to `./outputs`.
- **42 tests pass** as of 2026-08-20 (voice-override + animated-video tests added).
- `scripts/check_key.py` (committed `2222d15`) — one-command live Gemini key validator: `.venv\Scripts\python.exe scripts\check_key.py [KEY]` (or reads `GEMINI_API_KEY` from `.env`), exits 0/1.
- **Live end-to-end verified 2026-08-20**: `test_api.ps1 -Port 8001` full pipeline with real TTS (7 segments, Puck/Kore/Aoede), real sentiment, real market research; jobs, `/download`, `/rss` all pass. Reel generated via `scripts\make_reel.ps1` → `podcast_video_e5405ce1f64067a4f558a33665e62d77.mp4/.mp3/.srt` (76.8s, 27 SRT lines, zero new TTS quota — cached audio).

## Current git state
- Branch `main`. Latest commit pending — working tree has: per-speaker voice overrides (API + orchestrator + UI), animated playhead/color-coded video, 42 tests. Prior commits: `e3c0636` (AGENTS.md key/billing state), `2222d15` (check_key.py), `3b8381d` (harden API), `b390f40` (v2 UI/video).
- **Live Cloud Run** (verified 2026-08-13, all working):
  - Service `podcraft` region `us-central1`, project `podcraft-505309` (num `347254432482`). Current revision `podcraft-00012-k2p`, serving 100%.
  - `/health` → `{"Gemini/TTS": true, "Lyria": true, "Sentiment": true, "Parallel": true}`.
  - Secrets: `gemini-api-key` AND `parallel-api-key` (both `:latest`), IAM `roles/secretmanager.secretAccessor` granted to `347254432482-compute@developer.gserviceaccount.com`.
  - Deploy uses `--min-instances=1` (warm instance keeps `./outputs` for `/download`, avoids cold-start stalls).
  - GOTCHA: `PARALLEL_API_KEY` is deployed as a **secret ref** (not env var). `gcloud run deploy` refuses to flip a var between literal↔secret in one command — to change its type you must `--remove-env-vars` first, then set (two deploys), and `gcloud` forbids combining `--remove-env-vars` with `--set-env-vars`. `gcloud secrets versions add` adds a version to an EXISTING secret — use `gcloud secrets create` to make a new one.
- `/upload` accepts optional `?max_segments=N` **query param** (FastAPI `Query`, so curl must send it in the URL string, NOT as `-F` form field) → wires the existing lite-mode from the API so demos render only N segments. Verified: `?max_segments=3` → segs 0/3/6, `lite_mode=True`.
- `/upload` now also builds a downloadable **audio pack**: `outputs/podcraft_pack_<token>.zip` (manifest `production_manifest.json` + all speech/music WAVs) and returns `download_url` pointing at it. Each `audio_files[]` entry gets its own `download_url` too. `GET /download/{name}` serves any file in `./outputs` with `Content-Disposition: attachment`. Note: Cloud Run is stateless across instances, so `/download` for files generated by a *different* request/instance may 404 — for the demo video run everything in one session.
- `.env` is gitignored; don't commit it. Never log `GEMINI_API_KEY`.

## Gotchas / notes
- Python `hash()` is randomized → always use `stable_token()` for reproducible filenames (already used everywhere).
- On Windows, `orchestrator.py` reconfigures stdout to UTF-8 `errors="replace"` for emoji prints.
- `SMOKE TEST` script: `scripts/test_api.ps1` — starts uvicorn, hits `/health`, `/analyze`, `/upload`, `/download`, then stops server. The README mentions a "smoke-test script" in the Docker section — that's what it refers to.
- Model names in `.env.example`: `GEMINI_MODEL=gemini-3.5-flash` and `GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts`. Older check snippets online reference `gemini-2.0-flash-exp` — use the project config instead.
- `parallel_web` SDK is imported optionally in `parallel_search.py`; falls back to `requests` HTTP if absent. SDK v1.2.0 exposes module `parallel` (class `Parallel`), NOT `parallel_web.ParallelSearch` — code imports both. Neither key is needed for tests. Verified live: with `PARALLEL_API_KEY` set, `market_research.comparable_podcasts` returns 5+ real results (Nielsen, etc.).
- Deployment files: `Dockerfile` (python:3.11-slim + ffmpeg/libsndfile), `docker-compose.yml`, `src/phase5_deployment/*`. Deploy with `--min-instances=1` so one warm instance keeps `./outputs` (WAVs + pack) available for `/download` and avoids cold-start stalls in the demo; `cloud_run.py` `deploy_cmd()` already includes it.

## OpenCode config for this repo (ADDED 2026-08-13)

`opencode.json` + `.opencode/agent/bob.md` wire the hackathon platform requirements into OpenCode itself:
- **Gemini Enterprise**: default model `google/gemini-3.5-flash`; `provider.google` (uses `{env:GEMINI_API_KEY}`) and `provider.google-vertex` (uses `{env:GOOGLE_CLOUD_PROJECT}` + ADC/GAC) both configured.
- **IBM Bob**: `.opencode/agent/bob.md` is a `subagent` that drives BobShell (`bob -p "<task>"` / `--yolo`) as an SDLC partner. BobShell NOT installed — user decided NOT to use Bob (2026-08-13), do not install.
- **Grafana MCP**: remote server `https://mcp.grafana.com/mcp` (hosted, OAuth browser auth; `X-Grafana-URL` header set from `{env:GRAFANA_STACK_URL}`).
- **Parallel Search MCP**: remote server `https://search.parallel.ai/mcp`, keyless free tier (no Authorization header).
- `opencode.json` validated against the published schema (2026-08-13).

Gotchas:
- opencode reads **shell env vars only** — the `.env` file is invisible to it. Set `$env:GEMINI_API_KEY` (and others) in the shell before launching, or use `/connect` in the TUI.
- Config + agents load **only at startup** — quit and restart opencode after editing `opencode.json` or `.opencode/agent/*`.
- Schema (already validated): `model` must be `provider/model`; remote MCP servers need `type: "remote"` + `url`; `{env:VAR}` interpolation in header/option strings.