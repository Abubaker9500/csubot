# CSUBot

A web-based AI chatbot built for California State University Bakersfield (CSUB), powered by locally hosted large language models via [Ollama](https://ollama.com/).

---

## Overview

CSUBot is a senior project developed by students at CSUB. It provides a secure, university-hosted chat interface backed by open-source LLMs running on university HPC infrastructure — no data leaves campus.

---

## Architecture

```
User Browser
    │
    ▼
cs.csub.edu  (Frontend — NGINX)
    │  reverse proxy /ab-sayed → hpc1:5000
    ▼
hpc1.csub.edu  (Backend — Flask + Gunicorn :5000)
    │
    ▼
Ollama  (LLM inference — Qwen3 models)
```

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
# → http://localhost:5000
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

| Setting                  | Local                        | Production                          |
|--------------------------|------------------------------|-------------------------------------|
| `DEFAULT_MODEL`          | `qwen3:1.7b`                 | `qwen3:8b`                          |
| `SESSION_COOKIE_SECURE`  | `False`                      | `True`                              |
| CORS origin              | `*`                          | `https://cs.csub.edu`               |
| `API_URL` (JS)           | `http://localhost:5000/chat` | `https://hpc1.csub.edu/ab-sayed/chat` |

---

## Deployment

Deployment requires the following sysadmin actions on `hpc1.csub.edu`:

1. Install **Miniconda** (or `python3-venv`) — no sudo required with Miniconda
2. Configure **NGINX** to reverse proxy `/ab-sayed` → `127.0.0.1:5000`

Once those are in place, activate the conda environment and start Gunicorn:

```bash
conda activate csubot
gunicorn -w 2 -b 127.0.0.1:5000 app:app
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
