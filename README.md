# AIIC-Project — MiMo Web Chat

A simple multi-conversation streaming chat web app talking to Xiaomi MiMo via the
OpenAI-compatible endpoint. Deployed at <https://aiic.fomalhaut647.com>.

## Stack

- Backend: FastAPI + httpx (async SSE proxy)
- Frontend: single-page vanilla HTML/CSS/JS (no build step)
- Auth: Nginx HTTP Basic Auth
- Env: Pixi-managed Python

## Quick start (local dev)

```bash
# Put MIMO_API_KEY into .env first
pixi install
pixi run serve   # http://127.0.0.1:8000
pixi run test
```

## Layout

```
server/   FastAPI app + MiMo upstream constants
web/      index.html, app.js, styles.css
tests/    pytest suite
deploy/   systemd unit + nginx location snippet
docs/     specs/, plans/
```

## Production

Behind `aiic.fomalhaut647.com` (Nginx 1.24, TLS via TrustAsia DV, Basic Auth).
See `CLAUDE.md` for deployment details.
