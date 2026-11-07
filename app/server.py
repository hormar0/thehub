"""Milestone Hub control center - zero-dependency API + static server (Python stdlib)."""
import base64
import io
import json
import os
import re
import sqlite3
import traceback
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


def log_error(db, level, source, message, detail=""):
    db.execute("INSERT INTO error_log (ts, level, source, message, detail) VALUES (?,?,?,?,?)",
               (date.today().isoformat(), level, source, str(message)[:500], str(detail)[:4000]))
    db.commit()


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
    # migrate program phases to the standard five on every start (existing DBs keep old rows otherwise)
    db.executemany("INSERT OR REPLACE INTO program_phases VALUES (?,?,?,?,?)", [
        ("PH-FORMULATE", "Program Formulation", "2025-10-01", "2026-01-31", 0),
        ("PH-ORGANIZE", "Organization", "2026-02-01", "2026-05-31", 1),
        ("PH-DEPLOY", "Deployment", "2026-06-01", "2026-12-31", 2),
        ("PH-APPRAISE", "Appraisal", "2027-01-01", "2027-03-31", 3),
        ("PH-DISSOLVE", "Dissolution", "2027-04-01", "2027-06-30", 4),
    ])
    db.execute("DELETE FROM program_phases WHERE id NOT IN ('PH-FORMULATE','PH-ORGANIZE','PH-DEPLOY','PH-APPRAISE','PH-DISSOLVE')")
    # allow project-only time entries (deliverable_id nullable) on existing DBs
    cols = [r[1] for r in db.execute("PRAGMA table_info(time_entries)")]
    if cols and "deliverable_id" in cols:
        db.execute("CREATE TABLE IF NOT EXISTS time_entries_new (id TEXT PRIMARY KEY, deliverable_id TEXT REFERENCES deliverables(id), owner TEXT NOT NULL, hours REAL NOT NULL, week TEXT NOT NULL, project_id TEXT NOT NULL DEFAULT '')")
        db.execute("INSERT OR IGNORE INTO time_entries_new SELECT id, deliverable_id, owner, hours, week, project_id FROM time_entries")
        db.execute("DROP TABLE time_entries")
        db.execute("ALTER TABLE time_entries_new RENAME TO time_entries")
    # migrate projects to the rollout/cell set on every start
    db.executemany("INSERT OR REPLACE INTO projects VALUES (?,?,?,?,?,?,?,?,?)", [
        ("PRJ-R1", "Factory China", "PH-FORMULATE", "Explore", "2026-02-01", "2026-08-31", "active", "green", "rollout"),
        ("PRJ-R2", "Planning Gallin", "PH-ORGANIZE", "Realize", "2026-03-01", "2026-10-30", "active", "amber", "rollout"),
        ("PRJ-R3", "Market Western Europe", "PH-DEPLOY", "Deploy", "2026-07-01", "2026-12-31", "planned", "green", "rollout"),
        ("PRJ-R4", "Version 2 North America", "PH-DEPLOY", "Deploy", "2026-09-01", "2027-02-28", "planned", "amber", "rollout"),
        ("PRJ-C1", "Data Migration", "PH-ORGANIZE", "Realize", "2026-02-15", "2026-06-30", "active", "green", "cell"),
        ("PRJ-C2", "Testing", "PH-DEPLOY", "Realize", "2026-06-01", "2026-11-30", "planned", "amber", "cell"),
        ("PRJ-C3", "Cut over", "PH-DEPLOY", "Deploy", "2026-11-01", "2027-01-31", "planned", "red", "cell"),
        ("PRJ-C4", "Hypercare", "PH-APPRAISE", "Deploy", "2027-02-01", "2027-03-31", "planned", "green", "cell"),
        ("PRJ-C5", "Authorization", "PH-ORGANIZE", "Explore", "2026-03-01", "2026-07-31", "planned", "green", "cell"),
        ("PRJ-C6", "Training", "PH-DEPLOY", "Realize", "2026-08-01", "2026-12-15", "planned", "green", "cell"),
        ("PRJ-C7", "Business Realizing", "PH-DEPLOY", "Realize", "2026-07-15", "2026-12-31", "planned", "amber", "cell"),
        ("PRJ-V1", "Version 1", "PH-FORMULATE", "Explore", "2026-02-01", "2026-08-31", "active", "green", "rollout"),
        ("PRJ-V2", "Version 2", "PH-DEPLOY", "Realize", "2026-06-01", "2026-12-31", "planned", "amber", "rollout"),
        ("PRJ-V3", "Version 3", "PH-APPRAISE", "Deploy", "2027-01-01", "2027-04-30", "planned", "green", "rollout"),
    ])
    old_ids = [r["id"] for r in db.execute("SELECT id FROM projects WHERE id LIKE 'PRJ-0%' OR id = 'PRJ-T1'")]
    if old_ids:
        q = ",".join("?" * len(old_ids))
        db.execute(f"UPDATE deliverables SET project_id='' WHERE project_id IN ({q})", old_ids)
        db.execute(f"UPDATE users SET project_id='' WHERE project_id IN ({q})", old_ids)
        db.execute(f"UPDATE time_entries SET project_id='' WHERE project_id IN ({q})", old_ids)
        db.execute(f"DELETE FROM wbs WHERE project_id IN ({q})", old_ids)
        db.execute(f"DELETE FROM projects WHERE id IN ({q})", old_ids)
    db.commit()
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


BAND_SCORE = {"green": 100, "amber": 60, "red": 20}
BAND_ORDER = ["green", "amber", "red"]

def _eval_thresholds(measure_type, value, thresholds):
    if value in (None, ""):
        return "red"
    th = json.loads(thresholds) if isinstance(thresholds, str) else thresholds
    def num(v):
        try: return float(v)
        except Exception: return None
    v = num(value)
    bool_val = str(value).strip().lower() in ("true", "yes", "1")
    if measure_type == "boolean":
        return "green" if bool_val else "red"
    if v is None:
        return "red"
    for band in ("green", "amber", "red"):
        expr = th.get(band)
        if not expr:
            continue
        m = re.match(r"(==|>=|<=|>|<|=)\s*(.+)", expr.strip())
        if not m:
            continue
        op, rhs = m.group(1), m.group(2)
        r = num(rhs)
        if r is None:
            continue
        ok = {"==": v == r, "=": v == r, ">=": v >= r, "<=": v <= r, ">": v > r, "<": v < r}[op]
        if ok:
            return band
    return "red"


def mrf_compute(db, gate_id, stale_days=7):
    dims = rows(db.execute("SELECT * FROM mrf_dimensions ORDER BY position"))
    crits = rows(db.execute("SELECT * FROM mrf_criteria ORDER BY id"))
    ev = {r["criterion_id"]: dict(r) for r in db.execute("SELECT * FROM mrf_evidence WHERE gate_id=?", (gate_id,))}
    today = date.today()
    dim_out = []
    for d in dims:
        crit_out = []
        for c in [x for x in crits if x["dimension_id"] == d["id"]]:
            e = ev.get(c["id"], {})
            value, as_at, source = e.get("value", ""), e.get("as_at", ""), e.get("source", "")
            band = _eval_thresholds(c["measure_type"], value, c["thresholds"]) if value else "red"
            if not source:
                band = "red"
            stale = False
            if as_at:
                try:
                    stale = (today - date.fromisoformat(as_at)).days > stale_days
                except ValueError:
                    stale = True
            if stale and band in BAND_ORDER:
                band = BAND_ORDER[min(BAND_ORDER.index(band) + 1, 2)]
            crit_out.append({"id": c["id"], "statement": c["statement"], "measure_type": c["measure_type"],
                             "target": c["target"], "value": value, "as_at": as_at, "source": source or c["source"],
                             "band": band, "score": BAND_SCORE[band], "stale": stale, "override": e.get("override", "")})
        dim_score = round(sum(c["score"] for c in crit_out) / len(crit_out)) if crit_out else 20
        dim_band = "green" if dim_score >= 85 else "amber" if dim_score >= 55 else "red"
        dim_out.append({"id": d["id"], "name": d["name"], "weight": d["weight"], "score": dim_score,
                        "band": dim_band, "criteria": crit_out})
    score = round(sum(d["score"] * d["weight"] for d in dim_out) / 100) if dim_out else 0
    band = "green" if score >= 85 else "amber" if score >= 55 else "red"
    all_green = all(d["band"] == "green" for d in dim_out)
    no_red = all(d["band"] != "red" for d in dim_out)
    high_open = sum(1 for d in dim_out for c in d["criteria"] if c["id"].startswith("D8") and c["band"] == "red")
    acceptance = next((c for d in dim_out if d["id"] == "D6" for c in d["criteria"]), None)
    accepted = bool(acceptance and acceptance["band"] == "green")
    if score >= 85 and all_green and high_open == 0 and accepted:
        outcome = "READY"
    elif score >= 75 and no_red:
        outcome = "CONDITIONAL"
    else:
        outcome = "NOT READY"
    stale_count = sum(1 for d in dim_out for c in d["criteria"] if c["stale"] or (not c["value"]))
    oldest = min((c["as_at"] for d in dim_out for c in d["criteria"] if c["as_at"]), default="")
    return {"gate_id": gate_id, "score": score, "band": band, "outcome": outcome,
            "dimensions": dim_out, "stale_count": stale_count, "oldest_as_at": oldest,
            "computed_at": today.isoformat()}


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
    projects = rows(db.execute("SELECT p.*, (SELECT COUNT(*) FROM deliverables d WHERE d.project_id = p.id) AS deliverable_count FROM projects p ORDER BY p.start_date"))
    pl = db.execute("SELECT light FROM program_settings WHERE id=1").fetchone()
    mrf_next = mrf_compute(db, next_gate["id"]) if next_gate else None
    return {
        "today": today,
        "program_light": pl["light"] if pl else "green",
        "mrf": mrf_next,
        "projects": projects,
        "next_gate": dict(next_gate) if next_gate else None,
        "next_gate_readiness": readiness,
        "counts": {"open_conditions": open_conditions, "overdue_conditions": overdue_conditions, "open_decisions": open_decisions, "blocked_deliverables": blocked},
        "attention": attention[:6],
    }


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
        if dash["mrf"]:
            forecast.append(f"MRF computed readiness {dash['mrf']['score']}/100 ({dash['mrf']['band']}) -> recommended outcome {dash['mrf']['outcome']}")
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
            resp = get(r, "responsible_user")
            proj = get(r, "project_id", "project")
            if existing:
                db.execute("UPDATE deliverables SET title=?, description=?, workstream_id=?, owner=?, gate_id=?, state=?, due_date=?, evidence_ref=?, dependency_ids=?, grade=?, responsible_user=?, project_id=? WHERE id=?",
                           (title, get(r, "description"), ws, get(r, "owner") or "unassigned", gate, state, due, get(r, "evidence_ref", "evidence"), deps or "[]", grade, resp, proj, did))
            else:
                db.execute("INSERT INTO deliverables VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (did, title, get(r, "description"), ws, get(r, "owner") or "unassigned", gate, state, due, None, None, get(r, "evidence_ref", "evidence"), deps or "[]", grade, resp, proj, "medium", "", 0, "task"))
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



def local_chat_answer(ctx, msg):
    m = msg.lower()
    if "my" in m and "deliverable" in m:
        items = ctx["my_deliverables"]
        return ("You have %d deliverables: " % len(items)) + (", ".join(f"{d['id']} {d['title']} ({d['state']}, due {d['due_date']})" for d in items[:8]) or "none") if items else "No deliverables found under your name — tell me your name in the chat header."
    if "my" in m and ("risk" in m or "raid" in m):
        items = ctx["my_risks"]
        return ("Your risks: " + ", ".join(f"{r['id']} {r['title']} [{r['severity']}/{r['status']}]" for r in items[:8])) if items else "No RAID items under your name."
    if "milestone" in m or "gate" in m or "status" in m:
        g = ctx["next_gate"]
        scores = ", ".join(f"{k}:{v['score']}{v['band'][0].upper()}" for k, v in list(ctx["mrf_scores"].items())[:8])
        return (f"Next gate: {g['id']} {g['name']} on {g['scheduled_date']} ({g['status']}). "
                f"Program light: {ctx['program_light']}. Open conditions: {ctx['counts']['open_conditions']}, open decisions: {ctx['counts']['open_decisions']}, blocked deliverables: {ctx['counts']['blocked_deliverables']}. MRF scores: {scores}. Attention: {'; '.join(ctx['attention'][:3]) or 'none'}.")
    if "deliver" in m or "readiness" in m:
        by = {}
        for d in ctx["deliverables"]:
            by[d["state"]] = by.get(d["state"], 0) + 1
        return "Deliverables by state: " + ", ".join(f"{k}: {v}" for k, v in by.items()) + f". Total {len(ctx['deliverables'])}."
    if "risk" in m or "raid" in m:
        hi = [r for r in ctx["raid"] if r["severity"] in ("high", "very_high")]
        return f"{len(ctx['raid'])} RAID items, {len(hi)} high/very-high: " + "; ".join(f"{r['id']} {r['title']}" for r in hi[:5])
    if "project" in m:
        return "Projects: " + "; ".join(f"{p['id']} {p['name']} [{p['project_type']}, SAP {p['sap_phase']}, {p['light']}]" for p in ctx["projects"])
    return (f"The Hub today ({ctx['today']}): program light {ctx['program_light']}, next gate {ctx['next_gate']['id']} ({ctx['next_gate']['status']}), "
            f"{len(ctx['deliverables'])} deliverables, {len(ctx['raid'])} RAID items, {len(ctx['open_decisions'])} open decisions, {len(ctx['projects'])} projects. Ask about milestones, deliverables, risks, projects, or 'my deliverables'.")


def _mistral_chat(api_key, base_url, model, system, user):
    payload = {"model": model, "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user}]}
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.loads(r.read().decode())
    return res["choices"][0]["message"]["content"]


def _gdrive_upload(token, filename, text):
    meta = json.dumps({"name": filename, "mimeType": "text/plain"}).encode()
    boundary = "----thehubboundary"
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta.decode()}\r\n"
            f"--{boundary}\r\nContent-Type: text/plain\r\n\r\n{text}\r\n--{boundary}--").encode()
    req = urllib.request.Request("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/related; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode()).get("id")


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
<title>Gate report — The Hub</title>
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
      <p class="muted" style="margin-top:18px">The Hub · Gate report · generated ${new Date().toISOString().slice(0,10)}</p>
    </div>` : '';
  document.getElementById('d').innerHTML = front + `
    <div class="muted">The Hub · Gate report · generated ${new Date().toISOString().slice(0,10)}</div>
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
<title>Shared deliverable — The Hub</title>
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
    <div class="muted" style="margin-bottom:8px">Shared from The Hub · ${res.created} · viewed ${res.views}×</div>
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
            return self._do_get(path, db)
        except Exception as e:
            log_error(db, "ERROR", "GET " + path, e, traceback.format_exc())
            self._send(500, {"error": str(e)})
        finally:
            db.close()

    def _do_get(self, path, db):
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
                out["mrf"] = mrf_compute(db, gid)
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
                by_project = {}
                for e in entries:
                    pid = e.get("project_id") or "(unassigned)"
                    by_project.setdefault(pid, {"hours": 0, "items": 0})
                    by_project[pid]["hours"] += e["hours"]
                    by_project[pid]["items"] += 1
                ps = db.execute("SELECT report_on FROM program_settings WHERE id=1").fetchone()
                return self._send(200, {"entries": entries, "by_owner": by_owner, "by_project": by_project, "report_on": ps["report_on"] if ps else "deliverables"})
            if path == "/api/calendar":
                dels = rows(db.execute("SELECT id, title, due_date, state, priority, gate_id, dtype, project_id FROM deliverables WHERE due_date != ''"))
                gates = rows(db.execute("SELECT id, name, scheduled_date, status FROM gates"))
                wbs = rows(db.execute("SELECT id, name, start_date, end_date, project_id FROM wbs WHERE start_date != ''"))
                return self._send(200, {"deliverables": dels, "gates": [{**g, "due_date": g["scheduled_date"]} for g in gates], "wbs": wbs})
            if path == "/api/gantt":
                dels = rows(db.execute("SELECT id, title, owner, gate_id, state, due_date, dependency_ids, priority, tags, planned_hours, project_id, dtype FROM deliverables ORDER BY due_date"))
                gates = rows(db.execute("SELECT id, name, scheduled_date, status FROM gates ORDER BY scheduled_date"))
                return self._send(200, {"deliverables": dels, "gates": gates})
            if path == "/api/program":
                phases = rows(db.execute("SELECT * FROM program_phases ORDER BY position"))
                projects = rows(db.execute("SELECT p.*, ph.name AS phase_name FROM projects p LEFT JOIN program_phases ph ON ph.id = p.program_phase_id ORDER BY p.start_date"))
                repo = db.execute("SELECT * FROM doc_repo WHERE id=1").fetchone()
                ps = db.execute("SELECT light FROM program_settings WHERE id=1").fetchone()
                rps = db.execute("SELECT report_on FROM program_settings WHERE id=1").fetchone()
                return self._send(200, {"phases": phases, "projects": projects, "doc_repo": dict(repo) if repo else None, "program_light": ps["light"] if ps else "green", "report_on": rps["report_on"] if rps else "deliverables"})
            if path == "/api/users":
                return self._send(200, rows(db.execute("SELECT u.*, p.name AS project_name FROM users u LEFT JOIN projects p ON p.id = u.project_id ORDER BY u.username")))
            if path == "/api/roadmap":
                return self._send(200, {
                    "workstreams": rows(db.execute("SELECT * FROM workstreams ORDER BY id")),
                    "phases": rows(db.execute("SELECT * FROM program_phases ORDER BY position")),
                    "milestones": rows(db.execute("SELECT * FROM milestones ORDER BY sort_key")),
                    "gates": rows(db.execute("SELECT * FROM gates ORDER BY scheduled_date")),
                    "projects": rows(db.execute("SELECT * FROM projects ORDER BY start_date")),
                    "program_light": db.execute("SELECT light FROM program_settings WHERE id=1").fetchone()["light"],
                })
            if path == "/api/readiness":
                out = {}
                for g in db.execute("SELECT id FROM gates"):
                    out[g["id"]] = mrf_compute(db, g["id"])
                return self._send(200, out)
            if path.startswith("/api/readiness/"):
                gid = path.split("/")[-1]
                if not db.execute("SELECT id FROM gates WHERE id=?", (gid,)).fetchone():
                    return self._send(404, {"error": "gate not found"})
                return self._send(200, mrf_compute(db, gid))
            if path == "/api/mistral":
                cfg = db.execute("SELECT * FROM mistral_config WHERE id=1").fetchone()
                out = dict(cfg) if cfg else {}
                out["api_key"] = ("•••" + out["api_key"][-4:]) if out.get("api_key") else ""
                return self._send(200, out)
            if path == "/api/allocation":
                users = rows(db.execute("SELECT u.*, p.name AS project_name FROM users u LEFT JOIN projects p ON p.id = u.project_id ORDER BY u.username"))
                hours = {}
                for e in db.execute("SELECT owner, project_id, SUM(hours) h FROM time_entries GROUP BY owner, project_id"):
                    hours[(e["owner"], e["project_id"])] = e["h"]
                projects = rows(db.execute("SELECT * FROM projects ORDER BY id"))
                return self._send(200, {"users": users, "projects": projects, "hours": {f"{k[0]}|{k[1]}": v for k, v in hours.items()}})
            if path == "/api/wbs":
                return self._send(200, rows(db.execute("SELECT * FROM wbs ORDER BY project_id, code")))
            if path == "/api/reportmode":
                ps = db.execute("SELECT report_on FROM program_settings WHERE id=1").fetchone()
                return self._send(200, {"report_on": ps["report_on"] if ps else "deliverables"})
            if path == "/api/errors":
                return self._send(200, rows(db.execute("SELECT * FROM error_log ORDER BY id DESC LIMIT 200")))
            if path == "/api/agents/export":
                agents = rows(db.execute("SELECT * FROM ai_agents WHERE enabled=1 ORDER BY position"))
                payload = {"source": "The Hub ai_agents registry", "exported": date.today().isoformat(),
                           "agents": [{"name": a["name"], "role": a["role"], "owner": a["owner"],
                                       "system_prompt": f"You are '{a['name']}' in The Hub. Role: {a['role']}. Owner: {a['owner']}. Grounding — only use: {a['grounding']}. Accuracy gate >= {a['accuracy_gate']}%. If evidence is insufficient, say so instead of inventing.",
                                       "accuracy_gate": a["accuracy_gate"]} for a in agents]}
                return self._send(200, payload, "application/json")
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
            pass

    def do_POST(self):
        path = urlparse(self.path).path
        db = get_db()
        try:
            body = self._json_body()
            return self._do_post(path, body, db)
        except Exception as e:
            log_error(db, "ERROR", "POST " + path, e, traceback.format_exc())
            self._send(500, {"error": str(e)})
        finally:
            db.close()

    def _do_post(self, path, body, db):
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
                d = db.execute("SELECT * FROM deliverables WHERE id=?", (body.get("id"),)).fetchone()
                if not d:
                    return self._send(404, {"error": "deliverable not found"})
                db.execute("UPDATE deliverables SET state=?, due_date=?, priority=?, tags=?, planned_hours=?, dtype=? WHERE id=?",
                           (body.get("state", d["state"]), body.get("due_date", d["due_date"]), body.get("priority", d["priority"]),
                            body.get("tags", d["tags"]), float(body.get("planned_hours", d["planned_hours"])), body.get("dtype", d["dtype"]), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/deliverables/assign":
                db.execute("UPDATE deliverables SET responsible_user=?, project_id=? WHERE id=?",
                           (body.get("responsible_user", ""), body.get("project_id", ""), body.get("id")))
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
            if path == "/api/wbs/add":
                wid = f"WBS-{db.execute('SELECT COUNT(*) c FROM wbs').fetchone()['c'] + 1:03d}"
                db.execute("INSERT INTO wbs VALUES (?,?,?,?,?,?,?)", (wid, body.get("project_id"), body.get("parent_id", ""), body.get("code", ""), body.get("name"), body.get("start_date", ""), body.get("end_date", "")))
                db.commit()
                return self._send(200, {"ok": True, "id": wid})
            if path == "/api/wbs/update":
                db.execute("UPDATE wbs SET project_id=?, parent_id=?, code=?, name=?, start_date=?, end_date=? WHERE id=?",
                           (body.get("project_id"), body.get("parent_id", ""), body.get("code", ""), body.get("name"), body.get("start_date", ""), body.get("end_date", ""), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/reportmode":
                mode = body.get("report_on", "deliverables")
                if mode not in ("deliverables", "projects"):
                    return self._send(400, {"error": "report_on must be deliverables or projects"})
                db.execute("INSERT INTO program_settings (id, light, report_on) VALUES (1, 'green', ?) ON CONFLICT(id) DO UPDATE SET report_on=excluded.report_on", (mode,))
                db.commit()
                return self._send(200, {"ok": True, "report_on": mode})
            if path == "/api/mistral/save":
                db.execute("INSERT INTO mistral_config (id, api_key, model, base_url, enabled) VALUES (1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET api_key=excluded.api_key, model=excluded.model, base_url=excluded.base_url, enabled=excluded.enabled",
                           (body.get("api_key", ""), body.get("model", "mistral-large-latest"), body.get("base_url", "https://api.mistral.ai/v1"), 1 if body.get("enabled") else 0))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/mistral/test":
                cfg = db.execute("SELECT * FROM mistral_config WHERE id=1").fetchone()
                if not cfg or not cfg["api_key"]:
                    return self._send(400, {"error": "save an API key first"})
                try:
                    reply = _mistral_chat(cfg["api_key"], cfg["base_url"], cfg["model"], "You are a connectivity test. Reply exactly: OK", "ping")
                except urllib.error.HTTPError as e:
                    return self._send(502, {"error": f"Mistral API {e.code}: {e.read().decode()[:200]}"})
                except Exception as e:
                    log_error(db, "ERROR", "mistral/test", e, traceback.format_exc())
                    return self._send(502, {"error": str(e)})
                return self._send(200, {"ok": True, "model": cfg["model"], "reply": reply[:300]})
            if path == "/api/agents/run":
                name = body.get("name")
                prompt = body.get("prompt", "Summarize the current program status from the Hub.")
                agent = db.execute("SELECT * FROM ai_agents WHERE name=?", (name,)).fetchone()
                if not agent:
                    return self._send(404, {"error": "unknown agent"})
                if not agent["enabled"]:
                    return self._send(400, {"error": "agent is disabled in settings"})
                cfg = db.execute("SELECT * FROM mistral_config WHERE id=1").fetchone()
                if not cfg or not cfg["api_key"]:
                    return self._send(400, {"error": "connect Mistral first (☰ → Mistral)"})
                dash = build_dashboard(db)
                ctx = json.dumps({"dashboard": {k: dash[k] for k in ("today", "program_light", "counts", "attention")},
                                  "next_gate": dash["next_gate"], "mrf": dash["mrf"]["score"] if dash.get("mrf") else None}, ensure_ascii=False)
                system = (f"You are the '{agent['name']}' agent in The Hub (role: {agent['role']}; owner: {agent['owner']}). "
                          f"Grounding contract — only use these sources: {agent['grounding']}. Accuracy gate: >= {agent['accuracy_gate']}%. "
                          f"If the evidence is insufficient, say so instead of inventing. Hub context: {ctx}")
                try:
                    reply = _mistral_chat(cfg["api_key"], cfg["base_url"], cfg["model"], system, prompt)
                except urllib.error.HTTPError as e:
                    return self._send(502, {"error": f"Mistral API {e.code}: {e.read().decode()[:200]}"})
                except Exception as e:
                    log_error(db, "ERROR", "agents/run", e, traceback.format_exc())
                    return self._send(502, {"error": str(e)})
                return self._send(200, {"ok": True, "agent": name, "model": cfg["model"], "reply": reply})
            if path == "/api/chat":
                msg = (body.get("message") or "").strip()
                user = (body.get("user") or "").strip()
                if not msg:
                    return self._send(400, {"error": "empty message"})
                dash = build_dashboard(db)
                gates = rows(db.execute("SELECT id, name, status, scheduled_date FROM gates ORDER BY scheduled_date"))
                mrf = {g["id"]: mrf_compute(db, g["id"]) for g in db.execute("SELECT id FROM gates")}
                dels = rows(db.execute("SELECT id, title, owner, gate_id, state, due_date, dtype, priority, project_id FROM deliverables ORDER BY due_date"))
                raid = rows(db.execute("SELECT id, type, title, severity, status, owner FROM raid ORDER BY raised_date DESC"))
                decs = rows(db.execute("SELECT id, title, status, owner, needed_by FROM decisions WHERE status IN ('open','escalated')"))
                projects = rows(db.execute("SELECT id, name, project_type, sap_phase, start_date, end_date, status, light FROM projects ORDER BY start_date"))
                mine_dels = [d for d in dels if user and user.lower() in d["owner"].lower()]
                mine_risks = [r for r in raid if user and user.lower() in r["owner"].lower()]
                ctx = {"today": dash["today"], "program_light": dash["program_light"], "counts": dash["counts"],
                       "attention": dash["attention"], "next_gate": dash["next_gate"],
                       "gates": gates, "mrf_scores": {k: {"score": v["score"], "band": v["band"], "outcome": v["outcome"]} for k, v in mrf.items()},
                       "projects": projects, "deliverables": dels, "raid": raid, "open_decisions": decs,
                       "my_deliverables": mine_dels, "my_risks": mine_risks, "asked_by": user}
                cfg = db.execute("SELECT * FROM mistral_config WHERE id=1").fetchone()
                if cfg and cfg["api_key"]:
                    system = ("You are the assistant inside The Hub, a program control center. Answer questions about milestones/gates, "
                              "deliverables, risks, decisions, projects and time reporting using ONLY the Hub context JSON provided. "
                              "Be concise, cite ids (DEL-, M-, RAID-, DEC-). If asked 'my' items, use my_deliverables/my_risks. If data is missing, say so. Hub context: " + json.dumps(ctx, ensure_ascii=False)[:6000])
                    try:
                        reply = _mistral_chat(cfg["api_key"], cfg["base_url"], cfg["model"], system, msg)
                        return self._send(200, {"ok": True, "reply": reply, "via": cfg["model"]})
                    except Exception as e:
                        log_error(db, "ERROR", "chat", e, traceback.format_exc())
                        return self._send(200, {"ok": True, "reply": local_chat_answer(ctx, msg), "via": "local-fallback (Mistral error: %s)" % str(e)[:80]})
                return self._send(200, {"ok": True, "reply": local_chat_answer(ctx, msg), "via": "local (connect Mistral in ☰ → Mistral for AI answers)"})
            if path == "/api/gates/delete":
                gid = body.get("id")
                g = db.execute("SELECT id FROM gates WHERE id=?", (gid,)).fetchone()
                if not g:
                    return self._send(404, {"error": "gate not found"})
                db.execute("DELETE FROM conditions WHERE gate_id=?", (gid,))
                db.execute("DELETE FROM mrf_evidence WHERE gate_id=?", (gid,))
                db.execute("DELETE FROM gate_reports WHERE gate_id=?", (gid,))
                dels = rows(db.execute("SELECT id FROM deliverables WHERE gate_id=?", (gid,)))
                for d in dels:
                    db.execute("DELETE FROM evidence WHERE deliverable_id=?", (d["id"],))
                    db.execute("DELETE FROM shares WHERE deliverable_id=?", (d["id"],))
                    db.execute("DELETE FROM time_entries WHERE deliverable_id=?", (d["id"],))
                db.execute("DELETE FROM deliverables WHERE gate_id=?", (gid,))
                db.execute("DELETE FROM gates WHERE id=?", (gid,))
                db.commit()
                return self._send(200, {"ok": True, "id": gid, "deliverables_deleted": len(dels)})
            if path == "/api/deliverables/delete":
                did = body.get("id")
                d = db.execute("SELECT id FROM deliverables WHERE id=?", (did,)).fetchone()
                if not d:
                    return self._send(404, {"error": "deliverable not found"})
                db.execute("DELETE FROM evidence WHERE deliverable_id=?", (did,))
                db.execute("DELETE FROM shares WHERE deliverable_id=?", (did,))
                db.execute("DELETE FROM time_entries WHERE deliverable_id=?", (did,))
                db.execute("DELETE FROM deliverables WHERE id=?", (did,))
                db.commit()
                return self._send(200, {"ok": True, "id": did})
            if path == "/api/errors/log":
                log_error(db, body.get("level", "ERROR"), body.get("source", "client"), body.get("message", ""), body.get("detail", ""))
                return self._send(200, {"ok": True})
            if path == "/api/errors/sync":
                token = body.get("token", "")
                if not token:
                    return self._send(400, {"error": "google drive token required (settings)"})
                pend = rows(db.execute("SELECT * FROM error_log WHERE synced=0 ORDER BY id"))
                if not pend:
                    return self._send(200, {"ok": True, "synced": 0, "note": "nothing pending"})
                text = "\n".join(f"[{r['ts']}] {r['level']} {r['source']}: {r['message']} | {r['detail'][:200]}" for r in pend)
                fname = f"thehub-error-log-{date.today().isoformat()}.txt"
                res = _gdrive_upload(token, fname, text)
                db.execute("UPDATE error_log SET synced=1 WHERE synced=0")
                db.commit()
                return self._send(200, {"ok": True, "synced": len(pend), "file": res})
            if path == "/api/readiness/evidence":
                db.execute("INSERT INTO mrf_evidence (gate_id, criterion_id, value, as_at, source, override) VALUES (?,?,?,?,?,?) ON CONFLICT(gate_id, criterion_id) DO UPDATE SET value=excluded.value, as_at=excluded.as_at, source=excluded.source, override=excluded.override",
                           (body.get("gate_id"), body.get("criterion_id"), str(body.get("value", "")), body.get("as_at", date.today().isoformat()), body.get("source", ""), body.get("override", "")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/light/project":
                db.execute("UPDATE projects SET light=? WHERE id=?", (body.get("light", "green"), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/light/program":
                db.execute("INSERT INTO program_settings (id, light) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET light=excluded.light", (body.get("light", "green"),))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/users/add":
                un = (body.get("username") or "").strip().lower()
                if not un:
                    return self._send(400, {"error": "username required"})
                if db.execute("SELECT username FROM users WHERE username=?", (un,)).fetchone():
                    return self._send(400, {"error": "username taken"})
                db.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (un, body.get("name"), body.get("email", ""), body.get("phone", ""), body.get("project_id", ""), body.get("skills", "")))
                db.commit()
                return self._send(200, {"ok": True, "username": un})
            if path == "/api/users/update":
                un = body.get("username")
                if not db.execute("SELECT username FROM users WHERE username=?", (un,)).fetchone():
                    return self._send(404, {"error": "user not found"})
                db.execute("UPDATE users SET name=?, email=?, phone=?, project_id=?, skills=? WHERE username=?",
                           (body.get("name"), body.get("email", ""), body.get("phone", ""), body.get("project_id", ""), body.get("skills", ""), un))
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
                db.execute("INSERT INTO time_entries VALUES (?,?,?,?,?,?)", (tid, body.get("deliverable_id") or None, body.get("owner"), float(body.get("hours", 0)), body.get("week"), body.get("project_id", "")))
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
                db.execute("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?)",
                           (pid, body.get("name"), body.get("program_phase_id"), body.get("sap_phase") or "Discover",
                            body.get("start_date"), body.get("end_date"), body.get("status") or "planned", body.get("light") or "green", body.get("project_type") or "template"))
                db.commit()
                return self._send(200, {"ok": True, "id": pid})
            if path == "/api/program/projects/update":
                db.execute("UPDATE projects SET name=?, program_phase_id=?, sap_phase=?, start_date=?, end_date=?, status=?, light=?, project_type=? WHERE id=?",
                           (body.get("name"), body.get("program_phase_id"), body.get("sap_phase"), body.get("start_date"), body.get("end_date"), body.get("status"), body.get("light", "green"), body.get("project_type", "template"), body.get("id")))
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
            pass

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
    print(f"The Hub on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
