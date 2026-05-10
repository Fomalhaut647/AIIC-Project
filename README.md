# AIIC-Project — AI 模拟面试官（16h Challenge）

> **Status (2026-05-10)**: 主办方挑战题目「**AI 模拟面试官·16 小时项目挑战**」已于 08:00 公布，
> 截止 5/10 24:00。题目原文：[`2026-05-09_项目挑战说明.md`](./2026-05-09_项目挑战说明.md)。
>
> 当前 `main` 上仍是 v1（MiMo web chat，赛前热身），新挑战实现尚未开始。
> v1 已归档到分支 `archive/web-chat-v1`，迁移到独立仓库后会从 `main` 移除。

## v1 — MiMo Web Chat（current `main` contents, 即将被替换）

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
