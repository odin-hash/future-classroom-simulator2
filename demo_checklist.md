# 📋 SkillX Public Demonstration Checklist

Perform these checks step-by-step prior to starting public presentations to ensure maximum reliability and latency optimization.

### 📡 1. Network & Connectivity
- [ ] **Internet Access**: Verify active internet connection (required for LLM/Edge TTS API endpoints).
- [ ] **WS Protocol Proxies**: Ensure WebSockets are allowed through local/corporate proxy configurations.

### 🎙️ 2. Audio & Microphone Permissions
- [ ] **Microphone Permission**: Allow browser microphone usage on load when prompted by the Startup Diagnostics widget.
- [ ] **Browser Autoplay Permission**: Click anywhere on the dashboard to unlock browser Web Audio contexts.

### 🔑 3. API Keys & Credentials
- [ ] **Gemini API Key**: Ensure `GEMINI_API_KEY` is exported or configured in the environment.
- [ ] **Google Credentials**: (Optional) Check Google Cloud Speech JSON credentials if using premium streaming STT.

### 💾 4. Cache & Warmups
- [ ] **Presets Configured**: Verify `demo_presets.json` is loaded in the backend folder.
- [ ] **Prebuilt Demo Mode**: Toggle "Demo Mode" on the dashboard for latency-free cached runs.

### 🛡️ 5. Backup & Recovery
- [ ] **Backup TTS ready**: Verify browser native `SpeechSynthesis` is functional as fallback.
- [ ] **REST Failovers**: Confirm that server uploads can bypass WebSockets if connection drops.
- [ ] **State Endpoint**: Test browser refreshes to ensure simulation recovers from SQLite checkpoints.
