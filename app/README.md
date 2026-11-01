# Milestone Hub — Program Control Center

Zero-dependency Python stdlib + SQLite backend and a Liquid Glass SPA for large Business Transformation programs: evidence-based gates, deliverables register, Kanban, decisions & conditions, RAID, briefing pack, Gantt, time reporting, AI agents, task-app integrations, share links.

## Run on Termux (Android) — install

```bash
pkg update -y && pkg install -y git python
git clone https://github.com/hormar0/thehub.git
cd thehub
git checkout vibe/milestone-hub-c4557a
bash install.sh
# open http://127.0.0.1:8080 in your browser
```

`install.sh` installs python3 if missing, starts the server, and opens the URL via `termux-open-url` when available.

## Run on Termux — update to latest

```bash
cd ~/thehub
git fetch origin
git checkout vibe/milestone-hub-c4557a
git pull origin vibe/milestone-hub-c4557a
# restart the server:
pkill -f "python3 server.py" 2>/dev/null; sleep 1
bash install.sh
```

Or in one line:
```bash
cd ~/thehub && git fetch origin && git checkout vibe/milestone-hub-c4557a && git pull origin vibe/milestone-hub-c4557a && pkill -f "python3 server.py" 2>/dev/null; sleep 1; bash install.sh
```

If the app was merged to `main`, switch to that instead:
```bash
cd ~/thehub && git checkout main && git pull origin main && pkill -f "python3 server.py" 2>/dev/null; sleep 1; bash install.sh
```

## Run anywhere else

```
python3 app/server.py          # http://127.0.0.1:8080
PORT=9000 python3 app/server.py
```
The SQLite DB (app/milestonehub.db) is created and seeded on first run; delete it to reset the demo data.

## Views & settings
Dashboard · Gates (evidence contracts + Gate Chair decisions) · Register (⋮ row menu: send to Google Tasks / MS To Do / Todoist, share link) · Kanban (custom columns, drag-and-drop) · Decisions & Conditions · RAID · Gantt · Time Report · AI Agents · Briefing Pack. All settings live under the ☰ hamburger menu: App store, Excel import, Program & projects (SAP Activate phases), Document repository (Teams/SharePoint), AI agents, Task apps.

## PR
Draft PR: https://github.com/hormar0/thehub/pull/1
