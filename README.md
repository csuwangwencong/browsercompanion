# BrowserCompanion

基于 `architecture.md` 的 MVP 实现。

## 组件说明

- `extension/`：Chrome MV3 扩展，包含侧边栏面板、后台浏览器网关和媒体内容适配器。
- `main_agent/`：FastAPI 编排服务，运行在 `127.0.0.1:8000`。
- `music_agent/`：FastAPI 音乐领域智能体，运行在 `127.0.0.1:8001`。
- `video_agent/`：FastAPI 视频领域智能体（Bilibili），运行在 `127.0.0.1:8002`。
- `reading_agent/`：FastAPI 阅读领域智能体，用于浏览器页面理解，运行在 `127.0.0.1:8003`。

## 本地开发启动

安装各 Python 服务的依赖：

```bash
pip install -r main_agent/requirements.txt
pip install -r music_agent/requirements.txt
pip install -r video_agent/requirements.txt
pip install -r reading_agent/requirements.txt
```

启动音乐智能体：

```bash
cd music_agent
uvicorn main:app --host 127.0.0.1 --port 8001
```

启动主智能体：

```bash
cd main_agent
uvicorn main:app --host 127.0.0.1 --port 8000
```

启动视频智能体：

```bash
cd video_agent
uvicorn main:app --host 127.0.0.1 --port 8002
```

启动阅读智能体：

```bash
cd reading_agent
uvicorn main:app --host 127.0.0.1 --port 8003
```

在 Chrome 开发者模式中加载 `extension/` 目录。如需音乐控制，打开 `https://music.163.com/st/webplayer`；如需 Bilibili 控制，打开 `https://www.bilibili.com`。

## 本地配置

本地手动启动使用 `.env.local` 进行开发者配置覆盖。旧版 `.env` 仍会首先加载作为后备，然后 `.env.local` 会覆盖其中的值。Docker Compose 使用 `.env.docker`。

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

## Docker 部署

Windows 上的 Docker Desktop 可以同时运行所有 Python 智能体和 Ollama。Chrome 扩展仍在本地 Chrome 浏览器中运行，通过发布的主机端口 `127.0.0.1:8000` 连接到 `main_agent`。

Docker 服务布局：

```text
Chrome 扩展 -> http/ws://127.0.0.1:8000

docker compose
  main_agent      :8000
  music_agent     :8001
  video_agent     :8002
  reading_agent   :8003
  ollama          :11434
```

启动前，如需使用 MiMo 功能，请编辑 `.env.docker` 并设置 `MIMO_API_KEY`。在 Docker 中，服务间 URL 使用 Compose 服务名称：

```env
MUSIC_AGENT_URL=http://music_agent:8001
VIDEO_AGENT_URL=http://video_agent:8002
READING_AGENT_URL=http://reading_agent:8003
BROWSER_EXECUTION_URL=http://main_agent:8000/internal/browser/execute
BROWSER_READ_URL=http://main_agent:8000/internal/browser/read
OLLAMA_BASE_URL=http://ollama:11434
```

构建并启动：

```powershell
docker compose up --build
```

后台运行：

```powershell
docker compose up -d --build
```

在 Ollama 容器内拉取模型：

```powershell
docker compose exec ollama ollama pull qwen2.5:7b-instruct
```

检查服务健康状态：

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8003/health
```

查看日志：

```powershell
docker compose logs -f main_agent
docker compose logs -f music_agent
docker compose logs -f video_agent
docker compose logs -f reading_agent
docker compose logs -f ollama
```

停止服务：

```powershell
docker compose down
```

Docker 服务运行后，在 `chrome://extensions` 中重新加载 `extension/`，使扩展重新连接到 `127.0.0.1:8000`。

## 意图分类器

`main_agent/intent/` 模块从两个维度对每个查询进行分类：

- 领域（domain）：`music`、`video`、`reading`、`other` 或 `ambiguous`
- 动作（action）：`play`、`pause`、`volume`、`seek`、`rate`、`next`、`previous`、`status`、`info`、`other` 或 `ambiguous`

规则引擎优先处理明确的指令。当配置了 `MIMO_API_KEY` 时，模糊或隐式请求会回退到 MiMo 进行分类。分类器维护独立的 `domainConfidence` 和 `actionConfidence` 置信度；只有当领域和动作都足够明确时才会进行路由。
