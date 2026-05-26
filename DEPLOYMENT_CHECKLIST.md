# 🚀 Production Deployment Checklist

This checklist contains important security configurations, reverse proxy settings, and browser considerations needed to deploy the **Future Classroom Simulator** to a production environment.

---

## 🔒 1. SSL/HTTPS & Microphone Permissions

Modern browsers strictly restrict microphone access (`navigator.mediaDevices.getUserMedia`) to secure contexts.
- **Requirement**: The application **MUST** be served over HTTPS in production.
- **Local Dev Exception**: Browsers permit HTTP only for `localhost` or `127.0.0.1`.
- **Action**: Provision an SSL certificate using Let's Encrypt, Cloudflare, or AWS ACM for your domain name.

---

## 🔌 2. Nginx WebSocket Reverse Proxy Configuration

FastAPI handles real-time transcribing audio streams via WebSockets (`/api/ws`). If your deployment is behind Nginx, you must explicitly enable connection upgrades. Add the following to your Nginx site configuration:

```nginx
server {
    listen 443 ssl;
    server_name classroom.yourdomain.com;

    # SSL configuration...

    # Frontend Static Files
    location / {
        root /var/www/future-classroom-simulator/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend HTTP Endpoints
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend WebSocket Route
    location /api/ws {
        proxy_pass http://127.0.0.1:8000/api/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

*Note: For Render or Heroku, WebSocket upgrades are handled automatically. For AWS ALB, ensure Sticky Sessions are configured or WebSockets support is enabled on the target group.*

---

## 🔊 3. Browser Autoplay & Audio Context Unlocking

Modern browsers block audio playback (e.g. TTS speech files) unless there has been a preceding user interaction on the page.
- **Mechanics**: The frontend uses standard Web Audio API and HTML5 Audio objects.
- **Handling**: The simulator dashboard includes a starting user interaction block (e.g., clicking the "Start Session" or "Unlock Sound" button) which initializes and unlocks the `AudioContext` thread.
- **Troubleshooting**: If sound is not playing, instruct users to click anywhere on the page to manually activate the audio context.

---

## 🗄️ 4. Database Setup & Persistent Volume Claims

By default, the backend uses SQLite (`classroom.db`) stored locally.
- **Containerized Deployments (Docker/Kubernetes)**: SQLite files inside containers are ephemeral. You must attach a **Persistent Volume Claim (PVC)** mapped to `/app/backend/classroom.db`.
- **Database Engine Swap**: For heavy concurrent usage, switch to a managed PostgreSQL cluster by overriding the `DATABASE_URL` environment variable:
  ```bash
  DATABASE_URL="postgresql://db_user:db_password@postgres-host:5432/classroom_db"
  ```
- **Pruning Job**: Set up a cron task or background worker to delete old sessions/transcripts if database size becomes a concern.

---

## 🩺 5. Health Check & Live Monitoring

The backend exposes a health check endpoint at `/api/health`.
- **Endpoint**: `GET https://classroom.yourdomain.com/api/health`
- **Behavior**: Returns a `200 OK` status with database connectivity checks. Integrate this route into target group health checks (e.g. AWS Route53, Render HTTP Health Probe, or Kubernetes Liveness/Readiness probes).
- **Latency Monitoring**: Monitor telemetry metrics exposed via logs to keep track of LLM/TTS duration.
