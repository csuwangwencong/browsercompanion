# BrowserCompanion

MVP implementation based on `architecture.md`.

## Components

- `extension/`: Chrome MV3 extension with side panel, background Browser Gateway, and media content adapter.
- `main_agent/`: FastAPI orchestration service on `127.0.0.1:8000`.
- `music_agent/`: FastAPI music domain agent on `127.0.0.1:8001`.
- `video_agent/`: FastAPI video domain agent for Bilibili on `127.0.0.1:8002`.
- `reading_agent/`: FastAPI reading domain agent for browser page understanding on `127.0.0.1:8003`.

## Development Startup

Install dependencies for each Python service:

```bash
pip install -r main_agent/requirements.txt
pip install -r music_agent/requirements.txt
pip install -r video_agent/requirements.txt
pip install -r reading_agent/requirements.txt
```

Start Music Agent:

```bash
cd music_agent
uvicorn main:app --host 127.0.0.1 --port 8001
```

Start Main Agent:

```bash
cd main_agent
uvicorn main:app --host 127.0.0.1 --port 8000
```

Start Video Agent:

```bash
cd video_agent
uvicorn main:app --host 127.0.0.1 --port 8002
```

Start Reading Agent:

```bash
cd reading_agent
uvicorn main:app --host 127.0.0.1 --port 8003
```

Load `extension/` in Chrome developer mode. For music control, open `https://music.163.com/st/webplayer`. For Bilibili control, open `https://www.bilibili.com`.

## Local Configuration

Local manual startup uses `.env.local` for developer overrides. The legacy `.env` is still loaded first as a fallback, then `.env.local` overrides it. Docker Compose uses `.env.docker`.

```env
MIMO_ENDPOINT=https://api.xiaomimimo.com/v1/chat/completions
MIMO_API_KEY=your_api_key_here
MIMO_MODEL=mimo-v1

MUSIC_AGENT_URL=http://127.0.0.1:8001
VIDEO_AGENT_URL=http://127.0.0.1:8002
READING_AGENT_URL=http://127.0.0.1:8003
BROWSER_EXECUTION_URL=http://127.0.0.1:8000/internal/browser/execute
BROWSER_READ_URL=http://127.0.0.1:8000/internal/browser/read

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
```

## Docker Deployment

Docker Desktop on Windows can run all Python agents and Ollama together. The Chrome extension still runs in the local Chrome browser and connects to `main_agent` through the published host port `127.0.0.1:8000`.

Docker service layout:

```text
Chrome extension -> http/ws://127.0.0.1:8000

docker compose
  main_agent      :8000
  music_agent     :8001
  video_agent     :8002
  reading_agent   :8003
  ollama          :11434
```

Before starting, edit `.env.docker` and set `MIMO_API_KEY` if MiMo features are needed. In Docker, service-to-service URLs use Compose service names:

```env
MUSIC_AGENT_URL=http://music_agent:8001
VIDEO_AGENT_URL=http://video_agent:8002
READING_AGENT_URL=http://reading_agent:8003
BROWSER_EXECUTION_URL=http://main_agent:8000/internal/browser/execute
BROWSER_READ_URL=http://main_agent:8000/internal/browser/read
OLLAMA_BASE_URL=http://ollama:11434
```

Build and start:

```powershell
docker compose up --build
```

Run in the background:

```powershell
docker compose up -d --build
```

Pull the Ollama model inside the Ollama container:

```powershell
docker compose exec ollama ollama pull qwen2.5:7b-instruct
```

Check service health:

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8003/health
```

View logs:

```powershell
docker compose logs -f main_agent
docker compose logs -f music_agent
docker compose logs -f video_agent
docker compose logs -f reading_agent
docker compose logs -f ollama
```

Stop services:

```powershell
docker compose down
```

After Docker services are running, reload `extension/` in `chrome://extensions` so the extension reconnects to `127.0.0.1:8000`.

## Intent Classifier

`main_agent/intent/` classifies each query across two axes:

- domain: `music`, `video`, `reading`, `other`, or `ambiguous`
- action: `play`, `pause`, `volume`, `seek`, `rate`, `next`, `previous`, `status`, `info`, `other`, or `ambiguous`

Rules handle clear commands first. Weak or implicit requests can fall back to MiMo classification when `MIMO_API_KEY` is configured. The classifier keeps separate `domainConfidence` and `actionConfidence`; routing only proceeds when the domain and action are clear enough.
