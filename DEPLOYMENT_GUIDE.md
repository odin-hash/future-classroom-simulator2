# 🌐 Render & Railway Deployment Guide

This guide provides step-by-step instructions for deploying the **Future Classroom Simulator** backend to production hosting environments like **Render** or **Railway**.

---

## 🔑 1. Environment Variables Checklist

Configure these exact keys in your Render Web Service or Railway Service environment settings:

| Variable Name | Required | Example / Recommended Value | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | **Yes** | `AIzaSyA...` | Google Gemini API key. Enables student agents responses. |
| `DATABASE_URL` | **Yes** | `postgresql://user:pass@host:5432/dbname` | PostgreSQL database connection string. SQLite is disabled in prod. |
| `GOOGLE_CREDENTIALS_JSON` | No | `'{"type": "service_account", "project_id": ...}'` | Stringified Google Cloud Speech-to-Text service account JSON credentials. |
| `ALLOW_MOCK_LLM` | No | `false` | Set to `true` only if you want to bypass startup checks for offline test mode. |
| `ALLOWED_ORIGINS` | No | `https://future-classroom-simulator.vercel.app` | Comma-separated CORS allowed domains (e.g. Vercel production frontend domain). |

---

## 🗄️ 2. PostgreSQL Setup

1.  **Render**:
    *   Click **New** → **PostgreSQL**.
    *   Name the database, select a region, and click **Create Database**.
    *   Once active, copy the **Internal Database URL** (if deploying backend on Render) or **External Database URL** (for remote connections).
2.  **Railway**:
    *   Click **New** → **Database** → **Add PostgreSQL**.
    *   Once deployed, click on the PostgreSQL card and copy the connection string under the **Variables** tab (`DATABASE_URL`).
3.  **Auto-migrations**:
    *   The backend automatically applies SQLAlchemy schema definitions and auto-migration columns (`curiosity_level`, `scenario`, `language`, etc.) on start. No manual migrations are required.

---

## ⚙️ 3. Deployment Configuration

### 3.1 Render Web Service Setup
1.  Click **New** → **Web Service** and connect your GitHub repository.
2.  Set these configurations:
    *   **Runtime**: `Python`
    *   **Build Command**: `pip install -r backend/requirements.txt`
    *   **Start Command**: `python3 -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
3.  Expand **Advanced** and add the environment variables defined in Section 1.
4.  Click **Create Web Service**.

### 3.2 Railway Service Setup
1.  Click **New** → **Deploy from GitHub repo** and select your repository.
2.  In the service configuration:
    *   Ensure the directory is set to project root.
    *   Under **Variables**, reference your PostgreSQL database: `DATABASE_URL` = `${{PostgreSQL.DATABASE_URL}}`
    *   Add other environment variables (e.g., `GEMINI_API_KEY`).
3.  Railway automatically detects the requirements file and starts the uvicorn process. If needed, configure the start command explicitly:
    `python3 -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT`

---

## 🔌 4. Production WebSockets & HTTPS Compatibility

*   **HTTPS Requirement**: Production browsers block microphone access (`navigator.mediaDevices.getUserMedia`) unless the frontend is served over HTTPS. Both Render and Railway automatically provision SSL certificates for custom domains.
*   **WebSocket Upgrades**: The real-time speech stream route `/api/stream-stt` requires active WebSocket connection upgrade rules.
    - Render and Railway handle WebSocket connection upgrades automatically.
    - If you place a reverse-proxy (e.g. Nginx or Cloudflare) in front of your container, ensure you allow HTTP Connection upgrade headers:
      ```nginx
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "Upgrade";
      ```

---

## 🔄 5. Redeploying & Validation

1.  **Code Updates**: Any push to the designated repository branch will trigger a build and rolling redeploy.
2.  **Diagnostics Review**: When the container boots, inspect the logs. The **Startup Self-Test Diagnostics** will print out a structured checklist. If any configuration is missing or invalid, the boot will fail-fast with a non-zero exit code.
3.  **Health Check Probe**: Render and Railway check `/api/health` to confirm container readiness. If the self-test reports `failed` status, the deploy is marked as unhealthy and rolled back.
