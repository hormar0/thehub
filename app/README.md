# Milestone Hub — Program Control Center

Zero-dependency Python stdlib + SQLite backend and a Liquid Glass SPA.

## Run on Termux (Android)

```bash
pkg update -y && pkg install -y git python
git clone https://github.com/hormar0/thehub.git
cd thehub
git checkout vibe/milestone-hub-c4557a
bash install.sh
# then open http://127.0.0.1:8080 in your browser
```

`install.sh` installs python3 if missing, starts the server, and opens the URL via `termux-open-url` when available.

## Run anywhere else

```
python3 app/server.py          # http://127.0.0.1:8080
PORT=9000 python3 app/server.py
```
The SQLite DB (app/milestonehub.db) is created and seeded on first run; delete it to reset.

## Views
Dashboard · Gates (evidence contracts + Gate Chair decisions) · Register · Kanban (custom columns, drag-and-drop) · Decisions & Conditions · RAID · Briefing Pack.

## API
GET /api/dashboard · /api/briefing · /api/gates · /api/gates/{id} · /api/deliverables · /api/conditions · /api/decisions · /api/raid · /api/workstreams · /api/evidence · /api/kanban/columns
POST /api/gates/decision · /api/deliverables/update · /api/conditions/update · /api/decisions/update · /api/kanban/columns/add · /api/kanban/columns/delete

## PR
Draft PR: https://github.com/hormar0/thehub/pull/1
