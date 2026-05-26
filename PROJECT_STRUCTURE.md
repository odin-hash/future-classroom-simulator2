# 📁 Project Structure

This document details the file-by-file directory layout of the **Future Classroom Simulator** repository, explaining the key modules, engines, and components that make up the system.

---

## 🏗️ Overview

The project is split into a Python FastAPI backend and a React/TypeScript frontend.

```
future-classroom-simulator/
├── backend/                  # FastAPI web server and classroom engines
│   ├── audio_cache/          # Disk cache storing generated TTS audio clips
│   ├── ai.py                 # LLM client handling API cascades (Gemini/Groq/Ollama)
│   ├── database.py           # SQLAlchemy setup and SQLite connection configuration
│   ├── demo_presets.json     # Cached preset scenarios for latency-free runs
│   ├── error_handler.py      # Exception handlers for HTTP and WebSockets
│   ├── main.py               # API endpoints, WebSocket streams, and core coordinator
│   ├── models.py             # SQLAlchemy models (sessions, states, logs)
│   ├── personality.py        # Indian student character definitions and static attributes
│   ├── requirements.txt      # Python dependencies
│   ├── schemas.py            # Pydantic validation schemas
│   ├── simulation.py         # Pedagogical scoring, turning mechanics, and ambient decay
│   ├── stress_test.py        # 60-turn classroom validation testing suite
│   ├── test_scenarios.py     # Unit tests verifying scenario initial state overrides
│   ├── validation.py         # Repetition engine (Jaccard similarity) and state clampers
│   └── voice.py              # Microsoft Edge TTS integration and Pitch/Rate alterations
│
├── frontend/                 # React 18, Vite, and TypeScript SPA
│   ├── public/               # Public assets and favicon
│   ├── src/
│   │   ├── components/       # Reusable user interface components
│   │   │   ├── Avatar.tsx       # Animated SVGs depicting student micro-expressions
│   │   │   ├── Blackboard.tsx   # Core teaching canvas and lecture dashboard
│   │   │   ├── EventPopup.tsx   # Modal for emergent classroom events (e.g. power cuts)
│   │   │   ├── StudentCard.tsx  # Student desk displaying individual attributes (Attention, Confidence)
│   │   │   ├── ThemeToggle.tsx  # Dynamic dark/light mode context toggle
│   │   │   └── VolumeControl.tsx# Volume settings and TTS speed overrides
│   │   ├── pages/            # App view assemblies
│   │   │   ├── Dashboard.tsx    # Session launcher and scenario Selector
│   │   │   ├── Classroom.tsx    # Live desks grid, voice stream controller, telemetry logs
│   │   │   └── Analytics.tsx    # Pedagogical assessment score cards and transcripts review
│   │   ├── assets/           # Client-side style overrides and vector graphics
│   │   ├── App.css           # Global layout adjustments
│   │   ├── index.css         # Glassmorphic color tokens, scrollbars, and HSL themes
│   │   ├── config.ts         # Endpoint routing mappings
│   │   ├── localization.ts   # Multi-language string tables (English, Hindi, etc.)
│   │   ├── syllabus.ts       # Structured syllabus units (Science, Math, History, Geography)
│   │   └── main.tsx          # React application bootstrapping
│   │
│   ├── tsconfig.json         # TypeScript configuration
│   └── vite.config.ts        # Vite compiler parameters
│
├── .env.example              # Sample environment configuration template
├── .gitignore                # Release-hardened repository exclusions
├── LICENSE                   # Open-source MIT License terms
├── README.md                 # Public documentation and startup instructions
├── CLEANUP_REPORT.md         # Documented file deletions and git-tracked files list
└── SECURITY_AUDIT.md         # Auditing report for keys, tokens, and credentials safety
```

---

## ⚙️ Key Subsystems Detail

### 1. Emergent Classroom Engine (ECE)
Implemented in [simulation.py](file:///Users/govind/.gemini/antigravity/scratch/future-classroom-simulator/backend/simulation.py) and [main.py](file:///Users/govind/.gemini/antigravity/scratch/future-classroom-simulator/backend/main.py). 
- **Momentum Updates**: Rather than raw overrides, student parameters (attention, understanding, confusion) evolve via a weighted momentum function:
  $$S_{t+1} = \alpha S_t + (1 - \alpha) \Delta S_{action}$$
- **Affinity Matrix**: Tracks how much each student likes or dislikes the teacher based on turn responses. Higher affinity improves attention maintenance.
- **Ambient Decay**: Updates overall classroom metrics (e.g. Noise increases if attention drops, and stress increases during exam topic lectures).

### 2. Validation & Self-Healing Engine
Implemented in [validation.py](file:///Users/govind/.gemini/antigravity/scratch/future-classroom-simulator/backend/validation.py).
- **Repetitive Detection**: Runs a Jaccard similarity distance check on the last 3 responses of a student.
- **Answer Healing**: If an answer falls below the threshold (resembling a loop or repeating words), the engine re-routes prompts to regenerate responses with custom variation parameters.
- **State Clamping**: Ensures values remain strictly between `0` and `100` and fixes logical anomalies (e.g., student understanding cannot exceed attention boundaries).

### 3. Speech & Audio Resiliency
- **STT Draft Cascade**: Handles incoming WebM/Opus audio streams via FastAPI WebSockets. If WebSocket frames fail or disconnect, the client automatically falls back to standard HTTP POST binary uploads.
- **TTS Synthesis Failover**: Connects backend speech queries to Microsoft Edge Neural voice synthesizer. In the event of network timeouts, the frontend intercepts the error and routes the text through the client browser's native `SpeechSynthesis` Web Speech API.
