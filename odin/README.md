# Odin public frontend (talks to HPC1)

HPC1 can run Ollama + Flask, but it is not reachable on HTTPS from a browser
(`ERR_CONNECTION_TIMED_OUT`). Odin’s `public_html` is the public site.

Do **not** copy `csubot.js` as a second app. The browser must stay on Odin so
login cookies work. These PHP files reverse-proxy to Flask on HPC1:

```
Browser
    │
    ▼
https://cs.csub.edu/~sayed/csubot/     (Odin public_html + PHP proxy)
    │
    ▼
http://hpc1.csub.edu:5000/ab-sayed/    (Flask + Ollama on HPC1)
```

## 1. HPC1 (keep gunicorn running)

Restart with a campus bind so Odin can connect (localhost-only is invisible to Odin):

```bash
# stop the old ./run_hpc.sh with Ctrl+C, then:
cd ~/csubot
git pull
source .venv/bin/activate
./run_hpc.sh
```

On HPC1:

```bash
curl -sS http://127.0.0.1:5000/ab-sayed/health
```

## 2. Can Odin reach Flask?

SSH to Odin and run:

```bash
curl -sS http://hpc1.csub.edu:5000/ab-sayed/health
```

**If that returns JSON:** you are done with networking. Copy the PHP files (step 3).

**If it times out:** Flask is up but port 5000 is blocked. From HPC1 open a reverse tunnel, then in `config.php` set `upstream` to `http://127.0.0.1:5000`:

```bash
# on HPC1, leave this running
ssh -N -R 5000:127.0.0.1:5000 sayed@odin.cs.csub.edu
```

## 3. Copy this folder to Odin public_html

```bash
scp odin/config.php odin/proxy.php odin/index.php odin/.htaccess \
  sayed@odin.cs.csub.edu:~/public_html/csubot/
```

Edit `~/public_html/csubot/config.php` if your Odin username is not `sayed` or if you need the tunnel upstream.

Then open:

https://cs.csub.edu/~sayed/csubot/

If that 404s, try `https://odin.cs.csub.edu/~sayed/csubot/` — CS uses one of those two hosts.
