# CSUBot

A web-based AI chatbot built for California State University Bakersfield (CSUB), powered by locally hosted large language models via [Ollama](https://ollama.com/).

---

## Overview

CSUBot is a senior project developed by students at CSUB. It provides a secure, university-hosted chat interface backed by open-source LLMs running on university HPC infrastructure — no data leaves campus.

---

## Architecture

Ollama and Flask stay on HPC1 (no public HTML there). The browser uses Odin’s `public_html`, which reverse-proxies to Flask so login cookies stay on `cs.csub.edu`.

```
Browser
    │
    ▼
https://cs.csub.edu/~sayed/csubot/   (Odin public_html — PHP proxy)
    │
    ▼
Flask on HPC1  0.0.0.0:5000          (CSUBOT_PREFIX=/ab-sayed)
    │
    ▼
Ollama on HPC1  127.0.0.1:11434      (qwen3:1.7b)
```

Do not copy `csubot.js` to Odin as a second frontend. See `odin/README.md`.

`https://hpc1.csub.edu/ab-sayed/` times out from off-campus; that is why Odin is the public URL.

| Layer      | Technology                        |
|------------|-----------------------------------|
| Frontend   | Plain HTML / CSS / JavaScript     |
| Backend    | Python · Flask · Gunicorn         |
| Database   | SQLite (`csubot.db`)              |
| LLM        | Ollama · Qwen3 (1.7b / 8b)       |
| Proxy      | NGINX (university-managed)        |
| Env mgmt   | Miniconda (HPC) · Homebrew (Mac)  |

---

## Features

- **Streaming chat** — responses stream token-by-token from the LLM
- **Authentication** — email/password login with bcrypt (cost 12) hashed passwords
- **Session security** — Flask signed cookies; HttpOnly, Secure, SameSite=Lax; 8-hour lifetime
- **Brute-force protection** — lockout after 5 failed attempts in 15 minutes, by email **or** IP
- **On-campus inference** — all model inference stays on university hardware
- **CSUB branding** — Pantone 661 blue (`#003087`) and Pantone 123 gold (`#FDB913`)

---

## Project Structure

```
csubot/
├── app.py              # Flask application & routes
├── add_user.py         # CLI user provisioning tool
├── csubot.db           # SQLite database (gitignored)
├── requirements.txt    # Python dependencies
├── static/
│   ├── csubot.js       # Frontend chat logic
│   ├── style.css       # Styles
│   └── ...
└── templates/
    ├── index.html      # Chat interface
    └── login.html      # Login page
```

---

## Setup

### Prerequisites

- Python 3.10+ (via Miniconda on HPC, Homebrew on Mac)
- [Ollama](https://ollama.com/) installed and running
- Qwen3 model pulled: `ollama pull qwen3:1.7b` (local) or `qwen3:8b` (production)

### Local Development

```bash
# 1. Clone the repo
git clone <repo-url>
cd csubot

# 2. Create and activate a virtual environment
conda create -n csubot python=3.11
conda activate csubot

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add a user
python add_user.py add you@csub.edu yourpassword

# 5. Run the app
python app.py
# → http://localhost:5001
```

> **Note:** For local development, `SESSION_COOKIE_SECURE` must be `False` (HTTP).

### User Management CLI

```bash
python add_user.py add <email> <password>   # Add a user
python add_user.py list                      # List all users
python add_user.py delete <email>            # Remove a user
```

---

## Configuration

Key config values that differ between environments:

| Setting                  | Local (Mac)                  | HPC1 behind Alberto’s NGINX          |
|--------------------------|------------------------------|--------------------------------------|
| `CSUBOT_PREFIX`          | *(empty)*                    | `/ab-sayed`                          |
| `CSUBOT_BIND`            | `0.0.0.0`                    | `127.0.0.1`                          |
| `CSUBOT_PORT`            | `5001`                       | `5000`                               |
| `CSUBOT_COOKIE_SECURE`   | unset / `0`                  | `1`                                  |
| `DEFAULT_MODEL`          | `qwen3:1.7b`                 | `qwen3:1.7b` (or 8b)                 |
| Public URL               | http://localhost:5001        | https://hpc1.csub.edu/ab-sayed/      |
| `API_URL` (JS)           | `/chat`                      | `/ab-sayed/chat`                     |

---

## HTTP API (Flask on HPC1, port 5000)

Campus NGINX (already configured) is:

```nginx
location /ab-sayed {
    proxy_pass http://127.0.0.1:5000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 120s;
    proxy_buffering off;
}
```

Because `proxy_pass` has **no trailing slash**, Flask receives `/ab-sayed/...`. Start the app with `CSUBOT_PREFIX=/ab-sayed` so links, cookies, and `/chat` stay under that path.

### `GET /health`

No login. Used to test the proxy.

```json
{ "status": "ok", "model": "qwen3:1.7b" }
```

### `POST /chat`

Requires an approved **student**, **staff**, or **admin** session cookie. Frontend: `fetch('/chat', { credentials: 'include' })`.

**Request** (`Content-Type: application/json`):

```json
{
  "messages": [
    { "role": "user", "content": "Where is CSUB?" },
    { "role": "assistant", "content": "…" }
  ]
}
```

- `messages` must be a JSON array.
- Each item: `role` (`user` or `assistant`; unknown roles become `user`) and `content` (string, max 4000 chars).
- Client `role: "system"` entries are **dropped**. The server injects its own RAG system prompt.
- Rate limit: 200 requests per client IP per hour.

**Success (200):** `Content-Type: application/x-ndjson`. Body is streamed Ollama `/api/chat` chunks (one JSON object per line). The UI reads `message.content` on each line.

Example line:

```json
{"model":"qwen3:1.7b","message":{"role":"assistant","content":"CSUB "},"done":false}
```

If Ollama is down, a line may be `{"error":"Could not connect to AI engine."}` still with HTTP 200.

**Errors (JSON `{"error": "…"}`):**

| Status | When |
|--------|------|
| 401 | No session (`Unauthorized. Please log in.`) |
| 403 | Account pending, denied, or banned |
| 400 | Missing/invalid `messages`, or none left after dropping system |
| 429 | Rate limit |

Also under `/ab-sayed`: `GET /`, `/login`, `/signup`, `/logout`, `/admin`, `/staff`, `/health`, `/csubot.js`, `/csubot.css`, `/panel.css`.

## Deployment

### HPC1 (Ollama + Flask — the real app)

```bash
ssh sayed@hpc1.csub.edu
cd ~/csubot          # or wherever you cloned
git pull
source .venv/bin/activate

# Ollama must already be listening on 127.0.0.1:11434
ollama serve         # if it is not already running (tmux pane 1)
ollama pull qwen3:1.7b

# Flask for Alberto's proxy (tmux pane 2)
chmod +x run_hpc.sh
./run_hpc.sh
```

Then open **https://hpc1.csub.edu/ab-sayed/**

Manual equivalent of `run_hpc.sh`:

```bash
export CSUBOT_PREFIX=/ab-sayed CSUBOT_BIND=127.0.0.1 CSUBOT_PORT=5000 CSUBOT_COOKIE_SECURE=1
gunicorn --bind 127.0.0.1:5000 --timeout 120 --worker-class gthread app:app
```

### Odin (optional public door only)

Copy `odin/index.html` into `~/public_html` if you want a cs.csub.edu link. It only redirects to HPC1. See `odin/README.md`.

### Laptop

```bash
python app.py
# http://localhost:5001  (no prefix, cookie Secure off)
```

---

## Security Notes

- Passwords are hashed with **bcrypt** (cost factor 12)
- Sessions use `session.clear()` on login to prevent session fixation
- Brute-force lockout is intentionally blunt (by email **or** IP) — documented tradeoff
- No user data or conversation history is transmitted off-campus

---

## Team

Senior project — California State University Bakersfield  
Department of Computer & Electrical Engineering & Computer Science

---

## License

For academic use. Contact the CSUB CS department for details.
