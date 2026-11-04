# Milestone Hub — Program Control Center

Zero-dependency Python stdlib + SQLite backend and a Liquid Glass SPA for large Business Transformation programs: evidence-based gates, deliverables register, Kanban, decisions & conditions, RAID, briefing pack, Gantt, time reporting, AI agents, task-app integrations, share links.

## Install on a NEW device (Android tablet / Termux) — installation pack

One file does everything (clone, branch, deps, start, open browser):

```bash
pkg update -y && pkg install -y git python wget
wget https://raw.githubusercontent.com/hormar0/thehub/vibe/milestone-hub-c4557a/install-pack.sh
bash install-pack.sh
# open http://127.0.0.1:8080 — landscape layout is tablet-optimised
```

Manual equivalent:

## Run on Termux (Android) — install

```bash
pkg update -y && pkg install -y git python
git clone https://github.com/hormar0/thehub.git
cd thehub
git checkout vibe/milestone-hub-c4557a
bash install.sh
# open http://127.0.0.1:8080 in your browser
```

## Run on Termux — ONE-COMMAND UPDATE

```bash
bash ~/thehub/update.sh
```

That single command fetches the latest code, pulls the branch, restarts the server, and re-opens the app. (Optional arg: `bash ~/thehub/update.sh main` after the PR is merged.)

Long form, if you prefer:
```bash
cd ~/thehub && git fetch origin && git checkout vibe/milestone-hub-c4557a && git pull origin vibe/milestone-hub-c4557a && pkill -f "python3 server.py" 2>/dev/null; sleep 1; bash install.sh
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
