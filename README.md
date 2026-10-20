# AFSAR — Personal AI Assistant

> **JARVIS-style personal AI** — local LLM via Ollama, voice TTS, persistent memory, news briefings, web search, and a polished desktop app powered by Tauri 2.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Requirements](#requirements)
4. [Quick Start](#quick-start)
5. [Configuration](#configuration)
6. [Running in Development](#running-in-development)
7. [Running in Production / Desktop](#running-in-production--desktop)
8. [API Reference](#api-reference)
9. [Testing](#testing)
10. [Project Structure](#project-structure)

---

## Overview

AFSAR is a **fully local, self-hosted** personal AI assistant:

- **Local LLM** — runs any Ollama model (default: `llama3.2:3b`)
- **Voice TTS** — Microsoft Edge TTS via `edge-tts`
- **Voice input** — browser Web Speech API
- **Persistent memory** — profile + memories stored in JSON; conversations in SQLite
- **News briefings** — Google News RSS, personalised to your interests
- **Web search** — DuckDuckGo scraping with cache and fallback
- **Desktop app** — Tauri 2 wrapper (system tray, global shortcut `Ctrl+Shift+Space`, autostart)

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  Tauri 2 Desktop Shell (Rust)               │
│  • System tray + global shortcut            │
│  • Spawns & kills uvicorn backend           │
│  • Webview → Next.js frontend               │
└───────────────┬─────────────────────────────┘
                │ http://127.0.0.1:3000 (dev)
                │ file://out (production)
┌───────────────▼─────────────────────────────┐
│  Next.js 16 Frontend (TypeScript)           │
│  • Conversation sidebar                     │
│  • Streaming chat (SSE)                     │
│  • TTS audio pipeline                       │
│  • Settings drawer                          │
└───────────────┬─────────────────────────────┘
                │ http://127.0.0.1:8000
┌───────────────▼─────────────────────────────┐
│  FastAPI Backend (Python)                   │
│  • /generate/stream  (LLM via Ollama)       │
│  • /tts/stream       (Edge TTS)             │
│  • /conversations    (SQLite CRUD)          │
│  • /synthesize       (profile extraction)  │
│  • /news, /search    (external data)        │
│  • /health, /health/ready                  │
└───────────────┬─────────────────────────────┘
                │
        ┌───────▼────────┐
        │  Ollama (local) │
        │  llama3.2:3b   │
        └────────────────┘
```

---

## Requirements

| Dependency | Minimum | Notes |
|---|---|---|
| Python | 3.11+ | 3.13 tested |
| Node.js | 18+ | 20+ recommended |
| Rust + Cargo | 1.90+ | For Tauri build |
| Ollama | latest | Must be running |
| Windows | 10/11 | macOS/Linux also supported |

Install Ollama and pull the model:

```bash
# Install Ollama from https://ollama.ai
ollama pull llama3.2:3b
```

---

## Quick Start

### 1. Clone and set up the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Optional: copy and edit config
copy .env.example .env
```

### 2. Set up the frontend

```bash
cd frontend
npm install
```

### 3. Start everything

```powershell
# From the repo root:
.\start.ps1

# Options:
.\start.ps1 -BackendOnly       # only the FastAPI server
.\start.ps1 -FrontendOnly      # only Next.js (assumes backend is running)
.\start.ps1 -NoTauri           # Next.js web mode instead of Tauri desktop
```

Then open **http://localhost:3000** (web mode) or wait for the Tauri window (desktop mode).

---

## Configuration

All backend settings can be overridden via environment variables or a `backend/.env` file:

| Variable | Default | Description |
|---|---|---|
| `AFSAR_HOST` | `127.0.0.1` | Bind address |
| `AFSAR_PORT` | `8000` | HTTP port |
| `AFSAR_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama base URL |
| `AFSAR_MODEL_NAME` | `llama3.2:3b` | Model to use |
| `AFSAR_MODEL_KEEP_ALIVE` | `30m` | Keep model in VRAM |
| `AFSAR_TTS_VOICE` | `en-US-AriaNeural` | Edge TTS voice |
| `AFSAR_TTS_RATE` | `-8%` | Speech rate |
| `AFSAR_TTS_PITCH` | `-4Hz` | Speech pitch |
| `AFSAR_LOG_LEVEL` | `INFO` | Logging verbosity |
| `AFSAR_DATA_DIR` | `../data` | Profile/memory/DB directory |
| `AFSAR_CORS_ORIGINS` | `http://localhost:3000,...` | Allowed CORS origins |
| `AFSAR_REQUEST_TIMEOUT` | `60.0` | HTTP request timeout (s) |

Frontend variables (`frontend/.env.local`):

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `http://127.0.0.1:8000` | Backend URL |

---

## Running in Development

Two terminals:

```bash
# Terminal 1 — Backend
cd backend
.venv\Scripts\activate
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — Frontend (web browser)
cd frontend
npm run dev
```

Or use the launcher:

```powershell
.\start.ps1 -NoTauri
```

### Tauri desktop dev mode

```bash
cd frontend
npm run tauri dev
```

This opens the Tauri window with hot-reload.

---

## Running in Production / Desktop

### Build the frontend static export

```bash
cd frontend
npm run build        # outputs to frontend/out/
```

### Package the Tauri app

```bash
cd frontend
npm run tauri build  # creates installer in src-tauri/target/release/bundle/
```

The installer bundles the Next.js output as the webview. The Python backend must be running separately (either installed as a service or launched by the user via `start.ps1`).

---

## API Reference

### Health

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness — always 200 if process is up |
| `/health/ready` | GET | Readiness — checks Ollama + storage |

### Chat

| Endpoint | Method | Body | Description |
|---|---|---|---|
| `/generate` | POST | `{input, history?, conversation_id?}` | Full response |
| `/generate/stream` | POST | `{input, history?, conversation_id?}` | SSE token stream |

### Conversations

| Endpoint | Method | Description |
|---|---|---|
| `/conversations` | GET | List all (paginated) |
| `/conversations` | POST | Create new |
| `/conversations/{id}` | GET | Get with messages |
| `/conversations/{id}` | PATCH | Rename |
| `/conversations/{id}` | DELETE | Delete |

### Data & Features

| Endpoint | Method | Description |
|---|---|---|
| `/data` | GET | Profile + memories |
| `/synthesize` | POST | Extract & save new facts |
| `/tts` | GET | `?text=...` — streaming MP3 |
| `/tts/stream` | POST | SSE base64 audio segments |
| `/news` | GET | Latest headlines |
| `/search` | GET | `?q=...` — web search context |

---

## Testing

```bash
cd backend
.venv\Scripts\activate
pytest tests/ -v
```

33 tests covering: config validation, DB CRUD, conversation routes, chat + streaming, health endpoints, TTS, news, synthesize, web search.

---

## Project Structure

```
AFSAR/
├── backend/
│   ├── main.py           # FastAPI app + routes
│   ├── config.py         # Centralized settings (Pydantic)
│   ├── assistant.py      # Conversation service layer
│   ├── db.py             # SQLite CRUD + migrations
│   ├── llm.py            # Ollama integration + system prompt
│   ├── tts.py            # Edge TTS streaming
│   ├── synthesize.py     # Profile/memory extraction
│   ├── news.py           # News RSS fetcher + cache
│   ├── websearch.py      # DuckDuckGo search
│   ├── profile.py        # Profile JSON loader
│   ├── memory.py         # Memory JSON loader/formatter
│   ├── knowledge.py      # Knowledge base loader
│   ├── requirements.txt
│   ├── .env.example
│   └── tests/            # 33 pytest tests
├── frontend/
│   ├── app/
│   │   ├── page.tsx      # Main UI (sidebar, chat, settings)
│   │   ├── page.module.css
│   │   ├── globals.css   # Design system
│   │   └── layout.tsx
│   ├── src-tauri/
│   │   ├── src/
│   │   │   ├── lib.rs    # Tauri shell (tray, shortcut, backend spawn)
│   │   │   └── main.rs
│   │   ├── tauri.conf.json
│   │   └── Cargo.toml
│   ├── .env.example
│   └── package.json
├── data/
│   ├── profile.json      # User profile
│   ├── memories.json     # Long-term memories
│   └── knowledge_base/   # Knowledge documents
├── scripts/              # Task capture, gcal integration
├── start.ps1             # Dev launcher (Windows)
└── README.md
```

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+Space` | Show/hide AFSAR window (global, works when minimized) |
| `Enter` | Send message |
| `Shift+Enter` | New line in message input |

---

## Tray Menu

Right-click the AFSAR tray icon:

- **Open AFSAR** — show and focus the window
- **Hide** — minimize to tray
- **Settings** — open the settings drawer
- **Exit AFSAR** — quit completely

---

## Troubleshooting

**Backend offline (red dot in UI)**
- Check Ollama is running: `ollama serve`
- Check the backend is running: `curl http://127.0.0.1:8000/health`

**No TTS audio**
- Edge TTS requires internet access on first use
- Toggle the 🔊 button in the top bar to re-enable

**Model not found**
- Run `ollama pull llama3.2:3b`
- Or set `AFSAR_MODEL_NAME` to a model you have installed

**CORS errors in browser**
- Add `http://localhost:3000` to `AFSAR_CORS_ORIGINS` in `.env`
