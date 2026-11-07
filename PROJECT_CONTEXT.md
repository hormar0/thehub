# The Hub — project context for any new chat

If you are a new chat session working on this project, read this file first.

## Where the code lives
- **Repo**: `hormar0/thehub` on GitHub — https://github.com/hormar0/thehub
- **Working branch**: `vibe/milestone-hub-c4557a`
- **Pull request**: https://github.com/hormar0/thehub/pull/1 (all work goes there; never open a replacement PR, never push to main)
- **The Hub home page (external URL)**: http://127.0.0.1:8080 on the host device (tablet) — open in the browser there. There is no public internet URL yet; to expose one, run a tunnel (e.g. `cloudflared tunnel` / ngrok) pointing at port 8080 and put that URL here.
- **App code**: `app/` — `server.py` (stdlib HTTP+SQLite API), `schema.py` (schema+seed+migrations), `static/index.html` (single-page UI), `import_files.py` (xlsx importer), `install-pack.sh` / `install.sh` / `update.sh`

## How to continue in a new chat
Tell the assistant: **"use repo hormar0/thehub, branch vibe/milestone-hub-c4557a, PR #1"** (or paste the PR URL). Then it can clone/push as needed. New chats have no memory — this file is the memory.

## Run / update on the tablet (Termux)
```bash
bash ~/thehub/update.sh     # one-command pull + restart
```
Install on a new device: `install-pack.sh` (see app/README.md). Server: `python3 app/server.py` → http://127.0.0.1:8080

## What the app is
Zero-dependency Python+SQLite program control center ("The Hub"): gates with evidence contracts + MRF computed readiness, deliverables register/kanban/calendar/draggable Gantt, roadmap (program phases Formulation→Organization→Deployment→Appraisal→Dissolution; projects with SAP Activate segmented bars, draggable on touch), decisions/conditions ledger, RAID, time reporting (week × project grid), WBS, project detail pages with charter scope + draggable org chart, AI agents registry (+ Mistral connection, export for Le Chat), task-app sends (Google Tasks/To Do/Todoist), share links, Excel import, error log with optional Google Drive sync, app-store module toggles, user-customizable main tabs (localStorage `hub_tabs`).

## Data import
Place the real xlsx files in a folder and run: `python3 app/import_files.py /path/to/uploads` (Deliverables Master → M-gates + deliverables; Decision Register → decisions; Risk Register → RAID).

## Conventions
- Commits land on the PR branch via the GitHub App; the tablet only pulls (no push credentials there).
- Runtime files (`app/milestonehub.db`, `server.log`, `__pycache__`) are gitignored; migrations run in `init_db()` on every start.
- Every assistant reply that mentions the update command puts it in its own fenced code block for easy copying.
- This chat has no image/paste upload — screenshots never arrive; files are referenced by sandbox path or imported via import_files.py.
