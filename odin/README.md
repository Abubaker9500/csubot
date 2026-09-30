# Odin public page → CSUBot on HPC1

Confirmed working from a campus computer:

**https://hpc1.csub.edu/ab-sayed/**

Alberto's NGINX on HPC1 is the reverse proxy. It serves that path straight to
Flask on the same machine, so there is no tunnel and no PHP in the request path.

```
Browser (on campus)
    → https://hpc1.csub.edu/ab-sayed/   (NGINX on HPC1)
    → Flask on HPC1 127.0.0.1:5000      (CSUBOT_PREFIX=/ab-sayed)
    → Ollama on HPC1 127.0.0.1:11434
```

Odin's only job is a public door: `index.html` links to that URL.

## Start it

On HPC1, with Ollama already running:

```bash
cd ~/csubot
source .venv/bin/activate
./run_hpc.sh
```

That is the whole startup. Nothing to run on Odin.

## Odin public_html

```bash
mkdir -p ~/public_html/csubot
cp ~/SeniorProject2/csubot/odin/index.html ~/public_html/csubot/
```

Then https://cs.csub.edu/~ssayedmnasim/csubot/ sends visitors to the HPC1 app.

If you previously deployed the PHP proxy, move it aside so `.htaccess` stops
routing everything through it:

```bash
mkdir -p ~/csubot-proxy-backup
mv ~/public_html/csubot/{proxy.php,index.php,config.php,.htaccess} ~/csubot-proxy-backup/
```

Stop the old tunnel too:

```bash
pkill -f 'ssh -N.*-L 5000:'
crontab -l | grep -v csubot-tunnel | crontab -   # if you added the cron line
```

## Known limit

`hpc1.csub.edu` answers on campus but **times out off-campus**. Remote users
need the campus VPN. If you need true off-campus access, ask the admin for one
of these and then use the PHP proxy again:

- allow **Odin → HPC1 TCP 5000**, or
- proxy `cs.csub.edu/~ssayedmnasim/csubot/` → `hpc1.csub.edu:5000/ab-sayed/` in Odin's own web server config

## Fallback: the PHP reverse proxy

`proxy.php`, `config.php`, `index.php`, and `.htaccess` are kept in this folder
for that case. `config.php` probes both the SSH tunnel (`127.0.0.1:5000`) and the
direct address (`hpc1.csub.edu:5000`) and uses whichever answers. `tunnel.sh`
keeps a tunnel alive from cron or tmux. None of it is needed while NGINX works.

## Troubleshooting

| Symptom | Fix |
|---|---|
| 502 at `/ab-sayed/` | gunicorn is down — `./run_hpc.sh` on HPC1 |
| Times out | You are off-campus, or NGINX is down — use VPN |
| Login works, chat errors 404 | Model name mismatch — `ollama list`, then check `CSUBOT_MODEL` in `run_hpc.sh` |
