"""Milestone Hub control center - zero-dependency API + static server (Python stdlib)."""
import base64
import io
import json
import os
import re
import sqlite3
import urllib.request
import urllib.error
import zipfile
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from xml.etree import ElementTree as ET

from schema import SCHEMA, seed, seed_columns

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "milestonehub.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    seed(db)
    seed_columns(db)
    db.close()


def rows(cur):
    return [dict(r) for r in cur.fetchall()]


def gate_readiness(db, gate_id):
    dels = db.execute("SELECT * FROM deliverables WHERE gate_id = ?", (gate_id,)).fetchall()
    if not dels:
        return {"gate_id": gate_id, "total": 0, "verified": 0, "pct": 100, "items": []}
    items = []
    verified = 0
    for d in dels:
        evs = db.execute("SELECT status FROM evidence WHERE deliverable_id = ?", (d["id"],)).fetchall()
        if not evs:
            ev_status = "missing"
        elif any(e["status"] == "missing" for e in evs):
            ev_status = "missing"
        elif any(e["status"] == "partial" for e in evs):
            ev_status = "partial"
        else:
            ev_status = "present"
        state_ok = d["state"] == "verified"
        if state_ok:
            verified += 1
        items.append({"id": d["id"], "title": d["title"], "owner": d["owner"], "state": d["state"], "due": d["due_date"], "evidence": ev_status, "grade": d["grade"], "evidence_ref": d["evidence_ref"], "ready": state_ok and ev_status == "present"})
    pct = round(100 * sum(1 for i in items if i["ready"]) / len(items))
    return {"gate_id": gate_id, "total": len(items), "verified": verified, "pct": pct, "items": items}


def build_dashboard(db):
    today = date.today().isoformat()
    next_gate = db.execute("SELECT * FROM gates WHERE status IN ('upcoming','in_progress') ORDER BY scheduled_date LIMIT 1").fetchone()
    readiness = gate_readiness(db, next_gate["id"]) if next_gate else None
    open_conditions = db.execute("SELECT COUNT(*) c FROM conditions WHERE status = 'open'").fetchone()["c"]
    overdue_conditions = db.execute("SELECT COUNT(*) c FROM conditions WHERE status='open' AND due_date < ?", (today,)).fetchone()["c"]
    open_decisions = db.execute("SELECT COUNT(*) c FROM decisions WHERE status IN ('open','escalated')").fetchone()["c"]
    blocked = db.execute("SELECT COUNT(*) c FROM deliverables WHERE state = 'blocked'").fetchone()["c"]
    vh = db.execute("SELECT * FROM raid WHERE severity='very_high' AND status != 'closed' ORDER BY raised_date").fetchall()
    attention = []
    for r in vh:
        attention.append(f"{r['type'].title()}: {r['title']} (owner: {r['owner']})")
    for c in db.execute("SELECT * FROM conditions WHERE status='open' AND due_date < ?", (today,)).fetchall():
        attention.append(f"Overdue gate condition {c['id']}: {c['text']} (owner: {c['owner']})")
    for d in db.execute("SELECT * FROM decisions WHERE status='escalated'").fetchall():
        attention.append(f"Escalated decision {d['id']}: {d['title']} (owner: {d['owner']})")
    for d in db.execute("SELECT * FROM deliverables WHERE state='blocked'").fetchall():
        attention.append(f"Blocked deliverable {d['id']}: {d['title']} (owner: {d['owner']})")
    return {"today": today, "next_gate": dict(next_gate) if next_gate else None, "next_gate_readiness": readiness,
            "counts": {"open_conditions": open_conditions, "overdue_conditions": overdue_conditions, "open_decisions": open_decisions, "blocked_deliverables": blocked},
            "attention": attention[:6]}


def build_briefing(db):
    dash = build_dashboard(db)
    g = dash["next_gate"]
    conditions = rows(db.execute("SELECT * FROM conditions WHERE status='open' ORDER BY due_date"))
    decisions = rows(db.execute("SELECT * FROM decisions WHERE status IN ('open','escalated') ORDER BY needed_by"))
    raid_movement = rows(db.execute("SELECT * FROM raid WHERE movement IN ('new','up') ORDER BY raised_date DESC"))
    forecast = []
    if g:
        r = dash["next_gate_readiness"]
        if r["pct"] < 50:
            forecast.append(f"{g['id']} ({g['name']}) at {r['pct']}% evidence readiness - high risk of hold unless gaps close")
        elif r["pct"] < 85:
            forecast.append(f"{g['id']} ({g['name']}) at {r['pct']}% evidence readiness - on track with conditions")
        else:
            forecast.append(f"{g['id']} ({g['name']}) at {r['pct']}% evidence readiness - gate-ready")
    return {"generated": dash["today"], "next_gate": g, "readiness": dash["next_gate_readiness"], "attention": dash["attention"],
            "open_conditions": conditions, "open_decisions": decisions, "raid_movement": raid_movement, "forecast": forecast}


NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _col_to_idx(ref):
    m = re.match(r"([A-Z]+)", ref)
    n = 0
    for ch in m.group(1):
        n = n * 26 + ord(ch) - 64
    return n - 1


def parse_xlsx(data: bytes):
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {r.get("Id"): r.get("Target") for r in rels}
    sheets = {}
    for sh in wb.iter(f"{NS}sheet"):
        rid = sh.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = relmap[rid]
        path = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
        root = ET.fromstring(z.read(path))
        rows_out = []
        for row in root.iter(f"{NS}row"):
            cells = {}
            for c in row.findall(f"{NS}c"):
                idx = _col_to_idx(c.get("r", "A1"))
                v = c.find(f"{NS}v")
                if c.get("t") == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(f"{NS}t"))
                elif v is None:
                    val = ""
                elif c.get("t") == "s":
                    val = shared[int(v.text)]
                else:
                    val = v.text
                cells[idx] = val
            if cells:
                rows_out.append([cells.get(i, "") for i in range(max(cells) + 1)])
            else:
                rows_out.append([])
        sheets[sh.get("name")] = rows_out
    return sheets


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def import_rows(db, kind: str, rows_in):
    header = [_norm(h) for h in rows_in[0]]
    col = {name: i for i, name in enumerate(header)}

    def get(r, *names):
        for n in names:
            if n in col and col[n] < len(r):
                return str(r[col[n]]).strip()
        return ""

    imported = skipped = 0
    if kind == "deliverables":
        for r in rows_in[1:]:
            title = get(r, "title", "deliverable")
            if not title:
                skipped += 1
                continue
            did = get(r, "id") or f"DEL-IMP-{imported + skipped + 1:03d}"
            existing = db.execute("SELECT id FROM deliverables WHERE id=?", (did,)).fetchone()
            ws = get(r, "workstream_id", "workstream") or "WS-CORE"
            if not db.execute("SELECT id FROM workstreams WHERE id=?", (ws,)).fetchone():
                db.execute("INSERT OR IGNORE INTO workstreams VALUES (?,?,?)", (ws, ws.title(), "unassigned"))
            gate = get(r, "gate_id", "gate") or "E-030"
            if not db.execute("SELECT id FROM gates WHERE id=?", (gate,)).fetchone():
                gate = db.execute("SELECT id FROM gates ORDER BY scheduled_date LIMIT 1").fetchone()["id"]
            state = get(r, "state", "status") or "not_started"
            if state not in ("not_started", "in_progress", "in_review", "blocked", "verified") and \
               not db.execute("SELECT id FROM kanban_columns WHERE id=?", (state,)).fetchone():
                state = "not_started"
            due = get(r, "due_date", "due") or date.today().isoformat()
            deps = get(r, "dependency_ids", "depends_on")
            grade = get(r, "grade")
            if existing:
                db.execute("UPDATE deliverables SET title=?, description=?, workstream_id=?, owner=?, gate_id=?, state=?, due_date=?, evidence_ref=?, dependency_ids=?, grade=? WHERE id=?",
                           (title, get(r, "description"), ws, get(r, "owner") or "unassigned", gate, state, due, get(r, "evidence_ref", "evidence"), deps or "[]", grade, did))
            else:
                db.execute("INSERT INTO deliverables VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (did, title, get(r, "description"), ws, get(r, "owner") or "unassigned", gate, state, due, None, None, get(r, "evidence_ref", "evidence"), deps or "[]", grade))
            imported += 1
    elif kind == "decisions":
        for r in rows_in[1:]:
            title = get(r, "title", "decision")
            if not title:
                skipped += 1
                continue
            did = get(r, "id") or f"DEC-IMP-{imported + skipped + 1:03d}"
            existing = db.execute("SELECT id FROM decisions WHERE id=?", (did,)).fetchone()
            status = get(r, "status") or "open"
            if status not in ("open", "decided", "escalated"):
                status = "open"
            if existing:
                db.execute("UPDATE decisions SET title=?, description=?, owner=?, needed_by=?, status=?, blocks=? WHERE id=?",
                           (title, get(r, "description"), get(r, "owner") or "unassigned", get(r, "needed_by", "needed") or date.today().isoformat(), status, get(r, "blocks"), did))
            else:
                db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (did, title, get(r, "description"), get(r, "owner") or "unassigned", get(r, "raised_date") or date.today().isoformat(), get(r, "needed_by", "needed") or date.today().isoformat(), status, get(r, "blocks"), None, None))
            imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped}


def _http_json(method, url, token, payload):
    req = urllib.request.Request(url, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read().decode()
        return json.loads(body) if body else {}


def _todoist_create(token, project_id, title, notes, due_date):
    payload = {"content": title, "description": notes}
    if due_date:
        payload["due_date"] = due_date
    if project_id:
        payload["project_id"] = project_id
    res = _http_json("POST", "https://api.todoist.com/api/v1/tasks", token, payload)
    return {"id": res.get("id"), "url": res.get("url")}


def _google_tasks_create(token, list_id, title, notes, due_date):
    tasklist = list_id or "default"
    payload = {"title": title, "notes": notes}
    if due_date:
        payload["due"] = f"{due_date}T00:00:00.000Z"
    res = _http_json("POST", f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist}/tasks", token, payload)
    return {"id": res.get("id"), "selfLink": res.get("selfLink")}


def _ms_todo_create(token, list_id, title, notes, due_date):
    if not list_id:
        list_id = "default"
    payload = {"title": title, "body": {"content": notes, "contentType": "text"}}
    if due_date:
        payload["dueDateTime"] = {"dateTime": f"{due_date}T00:00:00.0", "timeZone": "UTC"}
    res = _http_json("POST", f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks", token, payload)
    return {"id": res.get("id"), "webUrl": res.get("webUrl")}


REPORT_PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gate report — Milestone Hub</title>
<style>
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; color: #f2f5fa; margin: 0; min-height: 100vh;
    background: radial-gradient(900px 600px at 20% 0%, rgba(110,140,255,.3), transparent 60%), radial-gradient(800px 600px at 90% 100%, rgba(160,90,255,.25), transparent 60%), #0a0e1a; padding: 32px; }
  .doc { max-width: 860px; margin: 0 auto; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.14); border-radius: 18px; padding: 32px; box-shadow: 0 20px 60px rgba(0,0,0,.45); backdrop-filter: blur(20px); }
  h1 { font-size: 24px; margin: 0 0 4px; }
  h2 { font-size: 16px; margin: 24px 0 8px; color: #8ab8ff; }
  .muted { color: rgba(235,242,255,.6); font-size: 13px; }
  table { width: 100%; border-collapse: collapse; font-size: 13.5px; margin-top: 8px; }
  th { text-align: left; color: rgba(235,242,255,.6); font-size: 11.5px; text-transform: uppercase; padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,.15); }
  td { padding: 8px; border-bottom: 1px solid rgba(255,255,255,.08); vertical-align: top; }
  .pill { display:inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 600; border: 1px solid; }
  .grade { font-weight: 700; }
  .gA { color:#5ee38a; } .gB { color:#ffcf6e; } .gC { color:#ff9d5c; } .gD { color:#ff7d78; }
  .bar { height: 8px; background: rgba(255,255,255,.1); border-radius: 99px; overflow: hidden; }
  .bar > div { height: 100%; background: linear-gradient(90deg,#6ea8ff,#cfa9ff); }
  @media print { body { background: #fff; color: #111; } .doc { box-shadow: none; border-color: #ccc; background: #fff; } }
</style></head>
<body>
<div class="doc" id="d">Loading…</div>
<script>
const gid = location.pathname.split('/').pop();
const GRADE_CLS = { A: 'gA', B: 'gB', C: 'gC', D: 'gD', F: 'gD' };
fetch('/api/gates/' + gid + '/report').then(r => r.json()).then(g => {
  if (g.error) { document.getElementById('d').textContent = g.error; return; }
  const ev = s => s === 'present' ? '<span class="pill" style="color:#5ee38a;border-color:#5ee38a55">present</span>'
    : s === 'partial' ? '<span class="pill" style="color:#ffcf6e;border-color:#ffcf6e55">partial</span>'
    : '<span class="pill" style="color:#ff7d78;border-color:#ff7d7855">missing</span>';
  const st = s => '<span class="pill" style="color:#cfa9ff;border-color:#cfa9ff55">' + s + '</span>';
  const rc = g.report_config || {};
  const front = (rc.logo || rc.front_title || rc.front_description) ? `
    <div style="text-align:center;padding:40px 0;border-bottom:1px solid rgba(255,255,255,.12);margin-bottom:24px;page-break-after:always">
      ${rc.logo ? `<img src="${rc.logo}" alt="logo" style="max-height:90px;max-width:260px;margin-bottom:20px">` : ''}
      <h1 style="font-size:30px">${rc.front_title || (g.id + ' — ' + g.name)}</h1>
      <p class="muted" style="max-width:560px;margin:12px auto 0;font-size:14px;line-height:1.6">${(rc.front_description || '').replace(/\\n/g,'<br>')}</p>
      <p class="muted" style="margin-top:18px">Milestone Hub · Gate report · generated ${new Date().toISOString().slice(0,10)}</p>
    </div>` : '';
  document.getElementById('d').innerHTML = front + `
    <div class="muted">Milestone Hub · Gate report · generated ${new Date().toISOString().slice(0,10)}</div>
    <h1>${g.id} — ${g.name}</h1>
    <div class="muted">${g.phase} phase · scheduled ${g.scheduled_date} · Gate Chair: ${g.chair} · status: <b>${g.status}</b>${g.outcome ? ' · ' + g.outcome : ''}</div>
    <h2>Entry / exit criteria</h2>
    <p><b>Entry:</b> ${g.entry_criteria}</p>
    <p><b>Exit:</b> ${g.exit_criteria}</p>
    <h2>Evidence readiness: ${g.readiness.pct}%</h2>
    <div class="bar"><div style="width:${g.readiness.pct}%"></div></div>
    <h2>Deliverables in the evidence contract</h2>
    <table><tr><th>ID</th><th>Deliverable</th><th>Owner</th><th>State</th><th>Evidence</th><th>Evidence link</th><th>Grade</th></tr>
    ${g.readiness.items.map(i => `<tr><td>${i.id}</td><td>${i.title}</td><td>${i.owner}</td><td>${st(i.state)}</td><td>${ev(i.evidence)}</td>
      <td class="muted">${i.evidence_ref || '—'}</td>
      <td class="grade ${GRADE_CLS[i.grade] || ''}">${i.grade || '—'}</td></tr>`).join('')}
    </table>
    <h2>Conditions from this gate</h2>
    <table><tr><th>ID</th><th>Condition</th><th>Owner</th><th>Due</th><th>Status</th></tr>
    ${g.conditions.map(c => `<tr><td>${c.id}</td><td>${c.text}</td><td>${c.owner}</td><td>${c.due_date}</td><td>${c.status}</td></tr>`).join('') || '<tr><td colspan="5" class="muted">None</td></tr>'}
    </table>
    <p class="muted" style="margin-top:24px">Print this page (Ctrl+P) for the gate record.</p>`;
});
</script>
</body></html>"""


SHARE_PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shared deliverable — Milestone Hub</title>
<style>
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; color: #f2f5fa; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: radial-gradient(900px 600px at 20% 0%, rgba(110,140,255,.3), transparent 60%), radial-gradient(800px 600px at 90% 100%, rgba(160,90,255,.25), transparent 60%), #0a0e1a; }
  .card { background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.16); border-radius: 18px; padding: 28px; max-width: 520px; width: 92vw; box-shadow: 0 20px 60px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.2); backdrop-filter: blur(24px); }
  h1 { font-size: 20px; margin: 0 0 6px; }
  .muted { color: rgba(235,242,255,.6); font-size: 13px; }
  .pill { display:inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; border: 1px solid; }
</style></head>
<body>
<div class="card" id="c">Loading…</div>
<script>
const token = location.pathname.split('/').pop();
fetch('/api/share/' + token).then(r => r.json()).then(res => {
  if (res.error) { document.getElementById('c').textContent = res.error; return; }
  const d = res.deliverable;
  document.getElementById('c').innerHTML = `
    <div class="muted" style="margin-bottom:8px">Shared from Milestone Hub · ${res.created} · viewed ${res.views}×</div>
    <h1>${d.id} — ${d.title}</h1>
    <p style="margin:10px 0">${d.description || ''}</p>
    <p class="muted">Owner: ${d.owner} · Gate: ${d.gate_id} · Due: ${d.due_date} · Evidence: ${d.evidence_ref || 'none cited'}</p>
    <p style="margin-top:14px"><span class="pill" style="background:rgba(94,227,138,.14);color:#5ee38a;border-color:rgba(94,227,138,.35)">${d.state}</span></p>`;
});
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, content_type="application/json"):
        if isinstance(body, bytes):
            data = body
        elif isinstance(body, str):
            data = body.encode()
        else:
            data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def do_GET(self):
        path = urlparse(self.path).path
        db = get_db()
        try:
            if path == "/api/dashboard":
                return self._send(200, build_dashboard(db))
            if path == "/api/briefing":
                return self._send(200, build_briefing(db))
            if path == "/api/gates":
                gates = rows(db.execute("SELECT * FROM gates"))
                for g in gates:
                    g["readiness"] = gate_readiness(db, g["id"])
                return self._send(200, gates)
            if path.startswith("/api/gates/") and path.endswith("/report"):
                gid = path.split("/")[3]
                g = db.execute("SELECT * FROM gates WHERE id=?", (gid,)).fetchone()
                if not g:
                    return self._send(404, {"error": "gate not found"})
                out = dict(g)
                out["readiness"] = gate_readiness(db, gid)
                out["conditions"] = rows(db.execute("SELECT * FROM conditions WHERE gate_id=? ORDER BY due_date", (gid,)))
                rep = db.execute("SELECT * FROM gate_reports WHERE gate_id=?", (gid,)).fetchone()
                out["report_config"] = dict(rep) if rep else {"gate_id": gid, "logo": "", "logo_name": "", "front_title": "", "front_description": ""}
                return self._send(200, out)
            if path.startswith("/api/gates/"):
                gid = path.split("/")[-1]
                g = db.execute("SELECT * FROM gates WHERE id=?", (gid,)).fetchone()
                if not g:
                    return self._send(404, {"error": "gate not found"})
                out = dict(g)
                out["readiness"] = gate_readiness(db, gid)
                out["conditions"] = rows(db.execute("SELECT * FROM conditions WHERE gate_id=?", (gid,)))
                return self._send(200, out)
            if path == "/api/deliverables":
                return self._send(200, rows(db.execute("SELECT * FROM deliverables ORDER BY due_date")))
            if path == "/api/conditions":
                return self._send(200, rows(db.execute("SELECT * FROM conditions ORDER BY due_date")))
            if path == "/api/decisions":
                return self._send(200, rows(db.execute("SELECT * FROM decisions ORDER BY needed_by")))
            if path == "/api/raid":
                return self._send(200, rows(db.execute("SELECT * FROM raid ORDER BY raised_date DESC")))
            if path == "/api/workstreams":
                return self._send(200, rows(db.execute("SELECT * FROM workstreams")))
            if path == "/api/evidence":
                return self._send(200, rows(db.execute("SELECT * FROM evidence")))
            if path == "/api/kanban/columns":
                return self._send(200, rows(db.execute("SELECT * FROM kanban_columns ORDER BY position")))
            if path == "/api/modules":
                return self._send(200, rows(db.execute("SELECT * FROM app_modules ORDER BY label")))
            if path == "/api/timereport":
                entries = rows(db.execute("SELECT t.*, d.title AS deliverable_title, d.gate_id FROM time_entries t LEFT JOIN deliverables d ON d.id = t.deliverable_id ORDER BY t.week, t.owner"))
                by_owner = {}
                for e in entries:
                    by_owner.setdefault(e["owner"], {"hours": 0, "items": 0})
                    by_owner[e["owner"]]["hours"] += e["hours"]
                    by_owner[e["owner"]]["items"] += 1
                return self._send(200, {"entries": entries, "by_owner": by_owner})
            if path == "/api/gantt":
                dels = rows(db.execute("SELECT id, title, owner, gate_id, state, due_date, dependency_ids FROM deliverables ORDER BY due_date"))
                gates = rows(db.execute("SELECT id, name, scheduled_date, status FROM gates ORDER BY scheduled_date"))
                return self._send(200, {"deliverables": dels, "gates": gates})
            if path == "/api/program":
                phases = rows(db.execute("SELECT * FROM program_phases ORDER BY position"))
                projects = rows(db.execute("SELECT p.*, ph.name AS phase_name FROM projects p LEFT JOIN program_phases ph ON ph.id = p.program_phase_id ORDER BY p.start_date"))
                repo = db.execute("SELECT * FROM doc_repo WHERE id=1").fetchone()
                return self._send(200, {"phases": phases, "projects": projects, "doc_repo": dict(repo) if repo else None})
            if path == "/api/roadmap":
                return self._send(200, {
                    "workstreams": rows(db.execute("SELECT * FROM workstreams ORDER BY id")),
                    "phases": rows(db.execute("SELECT * FROM program_phases ORDER BY position")),
                    "milestones": rows(db.execute("SELECT * FROM milestones ORDER BY sort_key")),
                    "gates": rows(db.execute("SELECT * FROM gates ORDER BY scheduled_date")),
                    "projects": rows(db.execute("SELECT * FROM projects ORDER BY start_date")),
                })
            if path == "/api/agents":
                return self._send(200, rows(db.execute("SELECT * FROM ai_agents ORDER BY position")))
            if path == "/api/taskapps":
                return self._send(200, rows(db.execute("SELECT provider, enabled, list_id FROM task_integrations")))
            if path.startswith("/api/share/"):
                token = path.split("/")[-1]
                sh = db.execute("SELECT * FROM shares WHERE token=?", (token,)).fetchone()
                if not sh:
                    return self._send(404, {"error": "share link not found"})
                d = db.execute("SELECT * FROM deliverables WHERE id=?", (sh["deliverable_id"],)).fetchone()
                db.execute("UPDATE shares SET views = views + 1 WHERE token=?", (token,))
                db.commit()
                return self._send(200, {"deliverable": dict(d), "views": sh["views"] + 1, "created": sh["created"]})
            self._serve_static(path)
        finally:
            db.close()

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._json_body()
        db = get_db()
        try:
            if path == "/api/gates/decision":
                gid = body.get("gate_id")
                outcome = body.get("outcome")
                valid = {"passed", "passed_with_conditions", "failed", "held"}
                if outcome not in valid:
                    return self._send(400, {"error": "outcome must be one of passed, passed_with_conditions, failed, held"})
                today = date.today().isoformat()
                db.execute("UPDATE gates SET status=?, outcome=?, decided_date=? WHERE id=?", (outcome, body.get("note", outcome.replace("_", " ")), today, gid))
                if outcome == "passed_with_conditions":
                    for c in body.get("conditions", []):
                        cid = f"COND-{db.execute('SELECT COUNT(*) c FROM conditions').fetchone()['c'] + 1:02d}"
                        db.execute("INSERT INTO conditions VALUES (?,?,?,?,?,?,?,?)", (cid, gid, c["text"], c["owner"], c["due_date"], "open", today, None))
                db.commit()
                return self._send(200, {"ok": True, "gate_id": gid, "outcome": outcome})
            if path == "/api/conditions/update":
                db.execute("UPDATE conditions SET status=? WHERE id=?", (body.get("status", "open"), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/decisions/update":
                db.execute("UPDATE decisions SET status=?, decision=?, decided_date=? WHERE id=?", (body.get("status", "open"), body.get("decision"), date.today().isoformat(), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/deliverables/update":
                db.execute("UPDATE deliverables SET state=? WHERE id=?", (body.get("state", "not_started"), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/deliverables/grade":
                db.execute("UPDATE deliverables SET grade=? WHERE id=?", (body.get("grade", ""), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/gates/report/save":
                gid = body.get("gate_id")
                g = db.execute("SELECT id FROM gates WHERE id=?", (gid,)).fetchone()
                if not g:
                    return self._send(404, {"error": "gate not found"})
                logo = body.get("logo", "")
                if logo and not logo.startswith("data:image/"):
                    return self._send(400, {"error": "logo must be a data:image/* URL"})
                if len(logo) > 400000:
                    return self._send(400, {"error": "logo too large (max ~300KB)"})
                db.execute("INSERT INTO gate_reports (gate_id, logo, logo_name, front_title, front_description) VALUES (?,?,?,?,?) ON CONFLICT(gate_id) DO UPDATE SET logo=excluded.logo, logo_name=excluded.logo_name, front_title=excluded.front_title, front_description=excluded.front_description",
                           (gid, logo, body.get("logo_name", ""), body.get("front_title", ""), body.get("front_description", "")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/kanban/columns/add":
                label = (body.get("label") or "").strip()
                if not label:
                    return self._send(400, {"error": "label required"})
                cid = "col-" + label.lower().replace(" ", "_")[:24] + "-" + str(db.execute("SELECT COUNT(*) c FROM kanban_columns").fetchone()["c"])
                pos = db.execute("SELECT COALESCE(MAX(position), -1) + 1 m FROM kanban_columns").fetchone()["m"]
                db.execute("INSERT INTO kanban_columns VALUES (?,?,?,0)", (cid, label, pos))
                db.commit()
                return self._send(200, {"ok": True, "id": cid, "label": label, "position": pos})
            if path == "/api/kanban/columns/delete":
                cid = body.get("id")
                col = db.execute("SELECT * FROM kanban_columns WHERE id=?", (cid,)).fetchone()
                if not col or col["is_default"]:
                    return self._send(400, {"error": "cannot delete a default column"})
                fallback = "not_started"
                db.execute("UPDATE deliverables SET state=? WHERE state=?", (fallback, cid))
                db.execute("DELETE FROM kanban_columns WHERE id=?", (cid,))
                db.commit()
                return self._send(200, {"ok": True, "moved_to": fallback})
            if path == "/api/import":
                kind = body.get("kind")
                if kind not in ("deliverables", "decisions"):
                    return self._send(400, {"error": "kind must be deliverables or decisions"})
                b64 = (body.get("file") or "").split(",")[-1]
                try:
                    sheets = parse_xlsx(base64.b64decode(b64))
                except Exception as e:
                    return self._send(400, {"error": f"could not parse xlsx: {e}"})
                sheet_name = body.get("sheet") or list(sheets.keys())[0]
                if sheet_name not in sheets:
                    return self._send(400, {"error": f"sheet '{sheet_name}' not found; sheets: {list(sheets.keys())}"})
                result = import_rows(db, kind, sheets[sheet_name])
                result["sheet"] = sheet_name
                return self._send(200, result)
            if path == "/api/modules/toggle":
                name = body.get("name")
                enabled = 1 if body.get("enabled") else 0
                mod = db.execute("SELECT name FROM app_modules WHERE name=?", (name,)).fetchone()
                if not mod:
                    return self._send(404, {"error": "unknown module"})
                db.execute("UPDATE app_modules SET enabled=? WHERE name=?", (enabled, name))
                db.commit()
                return self._send(200, {"ok": True, "name": name, "enabled": enabled})
            if path == "/api/timereport/add":
                tid = f"TE-{db.execute('SELECT COUNT(*) c FROM time_entries').fetchone()['c'] + 1:02d}"
                db.execute("INSERT INTO time_entries VALUES (?,?,?,?,?)", (tid, body.get("deliverable_id"), body.get("owner"), float(body.get("hours", 0)), body.get("week")))
                db.commit()
                return self._send(200, {"ok": True, "id": tid})
            if path == "/api/program/phases/add":
                pid = f"PH-{str(body.get('name','phase')).upper().replace(' ','-')[:12]}-{db.execute('SELECT COUNT(*) c FROM program_phases').fetchone()['c'] + 1}"
                pos = db.execute("SELECT COALESCE(MAX(position), -1) + 1 m FROM program_phases").fetchone()["m"]
                db.execute("INSERT INTO program_phases VALUES (?,?,?,?,?)", (pid, body.get("name"), body.get("start_date"), body.get("end_date"), pos))
                db.commit()
                return self._send(200, {"ok": True, "id": pid})
            if path == "/api/program/phases/update":
                db.execute("UPDATE program_phases SET name=?, start_date=?, end_date=? WHERE id=?",
                           (body.get("name"), body.get("start_date"), body.get("end_date"), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/program/projects/add":
                pid = f"PRJ-{db.execute('SELECT COUNT(*) c FROM projects').fetchone()['c'] + 1:02d}"
                db.execute("INSERT INTO projects VALUES (?,?,?,?,?,?,?)",
                           (pid, body.get("name"), body.get("program_phase_id"), body.get("sap_phase") or "Discover",
                            body.get("start_date"), body.get("end_date"), body.get("status") or "planned"))
                db.commit()
                return self._send(200, {"ok": True, "id": pid})
            if path == "/api/program/projects/update":
                db.execute("UPDATE projects SET name=?, program_phase_id=?, sap_phase=?, start_date=?, end_date=?, status=? WHERE id=?",
                           (body.get("name"), body.get("program_phase_id"), body.get("sap_phase"), body.get("start_date"), body.get("end_date"), body.get("status"), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/program/docrepo":
                db.execute("INSERT INTO doc_repo (id, provider, webhook_url, enabled) VALUES (1,?,?,?) ON CONFLICT(id) DO UPDATE SET provider=excluded.provider, webhook_url=excluded.webhook_url, enabled=excluded.enabled",
                           (body.get("provider", "teams"), body.get("webhook_url", ""), 1 if body.get("enabled") else 0))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/agents/update":
                name = body.get("name")
                agent = db.execute("SELECT name FROM ai_agents WHERE name=?", (name,)).fetchone()
                if not agent:
                    return self._send(404, {"error": "unknown agent"})
                db.execute("UPDATE ai_agents SET role=?, owner=?, grounding=?, accuracy_gate=?, enabled=? WHERE name=?",
                           (body.get("role"), body.get("owner"), body.get("grounding"),
                            float(body.get("accuracy_gate", 90)), 1 if body.get("enabled") else 0, name))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/agents/add":
                name = (body.get("name") or "").strip()
                if not name:
                    return self._send(400, {"error": "name required"})
                if db.execute("SELECT name FROM ai_agents WHERE name=?", (name,)).fetchone():
                    return self._send(400, {"error": "agent already exists"})
                pos = db.execute("SELECT COALESCE(MAX(position), -1) + 1 m FROM ai_agents").fetchone()["m"]
                db.execute("INSERT INTO ai_agents VALUES (?,?,?,?,?,?,?)",
                           (name, body.get("role") or "custom", body.get("owner") or "unassigned",
                            body.get("grounding") or "", float(body.get("accuracy_gate", 90)),
                            1 if body.get("enabled", True) else 0, pos))
                db.commit()
                return self._send(200, {"ok": True, "name": name})
            if path == "/api/taskapps/save":
                provider = body.get("provider")
                row = db.execute("SELECT provider FROM task_integrations WHERE provider=?", (provider,)).fetchone()
                if not row:
                    return self._send(404, {"error": "unknown provider"})
                db.execute("UPDATE task_integrations SET enabled=?, token=?, list_id=? WHERE provider=?",
                           (1 if body.get("enabled") else 0, body.get("token", ""), body.get("list_id", ""), provider))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/taskapps/send":
                provider = body.get("provider")
                did = body.get("deliverable_id")
                d = db.execute("SELECT * FROM deliverables WHERE id=?", (did,)).fetchone()
                if not d:
                    return self._send(404, {"error": "deliverable not found"})
                integ = db.execute("SELECT * FROM task_integrations WHERE provider=?", (provider,)).fetchone()
                if not integ or not integ["enabled"] or not integ["token"]:
                    return self._send(400, {"error": f"{provider} not configured (enable + token required in settings)"})
                title = f"[{d['id']}] {d['title']} (gate {d['gate_id']}, due {d['due_date']})"
                notes = f"Owner: {d['owner']}. {d['description']}"
                try:
                    if provider == "todoist":
                        result = _todoist_create(integ["token"], integ["list_id"], title, notes, d["due_date"])
                    elif provider == "google_tasks":
                        result = _google_tasks_create(integ["token"], integ["list_id"], title, notes, d["due_date"])
                    elif provider == "ms_todo":
                        result = _ms_todo_create(integ["token"], integ["list_id"], title, notes, d["due_date"])
                    else:
                        return self._send(400, {"error": "unknown provider"})
                except urllib.error.HTTPError as e:
                    return self._send(502, {"error": f"{provider} API error {e.code}: {e.read().decode()[:200]}"})
                except Exception as e:
                    return self._send(502, {"error": f"{provider} call failed: {e}"})
                return self._send(200, {"ok": True, "provider": provider, "deliverable_id": did, "remote": result})
            if path == "/api/share/create":
                did = body.get("deliverable_id")
                d = db.execute("SELECT id FROM deliverables WHERE id=?", (did,)).fetchone()
                if not d:
                    return self._send(404, {"error": "deliverable not found"})
                token = base64.urlsafe_b64encode(os.urandom(9)).decode().rstrip("=")
                db.execute("INSERT INTO shares VALUES (?,?,?,0)", (token, did, date.today().isoformat()))
                db.commit()
                return self._send(200, {"ok": True, "token": token, "url": f"/share/{token}"})
            return self._send(404, {"error": "not found"})
        finally:
            db.close()

    def _serve_static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        if path.startswith("/report/"):
            return self._send(200, REPORT_PAGE, "text/html")
        if path.startswith("/share/"):
            return self._send(200, SHARE_PAGE, "text/html")
        safe = os.path.normpath(path).lstrip("/")
        full = os.path.join(STATIC_DIR, safe)
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            return self._send(404, {"error": "not found"})
        ctype = {".html": "text/html", ".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png"}.get(os.path.splitext(full)[1], "application/octet-stream")
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def main():
    init_db()
    port = int(os.environ.get("PORT", 8080))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Milestone Hub control center on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
