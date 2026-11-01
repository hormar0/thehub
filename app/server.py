"""Milestone Hub control center - zero-dependency API + static server (Python stdlib)."""
import json
import os
import sqlite3
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from schema import SCHEMA, seed, seed_columns

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "milestonehub.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")

GATE_ORDER = ["E-010", "E-020", "E-030", "D-010", "B-010", "T-010", "C-005"]


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
    """Evidence-contract readiness for a gate, per the Hub's evidence model."""
    dels = db.execute(
        "SELECT * FROM deliverables WHERE gate_id = ?", (gate_id,)
    ).fetchall()
    if not dels:
        return {"gate_id": gate_id, "total": 0, "verified": 0, "pct": 100, "items": []}
    items = []
    verified = 0
    for d in dels:
        evs = db.execute(
            "SELECT status FROM evidence WHERE deliverable_id = ?", (d["id"],)
        ).fetchall()
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
        items.append({
            "id": d["id"], "title": d["title"], "owner": d["owner"],
            "state": d["state"], "due": d["due_date"], "evidence": ev_status,
            "ready": state_ok and ev_status == "present",
        })
    pct = round(100 * sum(1 for i in items if i["ready"]) / len(items))
    return {"gate_id": gate_id, "total": len(items), "verified": verified, "pct": pct, "items": items}


def build_dashboard(db):
    today = date.today().isoformat()
    next_gate = db.execute(
        "SELECT * FROM gates WHERE status IN ('upcoming','in_progress') ORDER BY scheduled_date LIMIT 1"
    ).fetchone()
    readiness = gate_readiness(db, next_gate["id"]) if next_gate else None

    open_conditions = db.execute(
        "SELECT COUNT(*) c FROM conditions WHERE status = 'open'").fetchone()["c"]
    overdue_conditions = db.execute(
        "SELECT COUNT(*) c FROM conditions WHERE status='open' AND due_date < ?", (today,)).fetchone()["c"]
    open_decisions = db.execute(
        "SELECT COUNT(*) c FROM decisions WHERE status IN ('open','escalated')").fetchone()["c"]
    blocked = db.execute(
        "SELECT COUNT(*) c FROM deliverables WHERE state = 'blocked'").fetchone()["c"]
    vh = db.execute(
        "SELECT * FROM raid WHERE severity='very_high' AND status != 'closed' ORDER BY raised_date").fetchall()
    attention = []
    for r in vh:
        attention.append(f"{r['type'].title()}: {r['title']} (owner: {r['owner']})")
    for c in db.execute(
        "SELECT * FROM conditions WHERE status='open' AND due_date < ?", (today,)
    ).fetchall():
        attention.append(f"Overdue gate condition {c['id']}: {c['text']} (owner: {c['owner']})")
    for d in db.execute(
        "SELECT * FROM decisions WHERE status='escalated'").fetchall():
        attention.append(f"Escalated decision {d['id']}: {d['title']} (owner: {d['owner']})")
    for d in db.execute(
        "SELECT * FROM deliverables WHERE state='blocked'").fetchall():
        attention.append(f"Blocked deliverable {d['id']}: {d['title']} (owner: {d['owner']})")

    return {
        "today": today,
        "next_gate": dict(next_gate) if next_gate else None,
        "next_gate_readiness": readiness,
        "counts": {
            "open_conditions": open_conditions,
            "overdue_conditions": overdue_conditions,
            "open_decisions": open_decisions,
            "blocked_deliverables": blocked,
        },
        "attention": attention[:6],
    }


def build_briefing(db):
    dash = build_dashboard(db)
    g = dash["next_gate"]
    conditions = rows(db.execute("SELECT * FROM conditions WHERE status='open' ORDER BY due_date"))
    decisions = rows(db.execute(
        "SELECT * FROM decisions WHERE status IN ('open','escalated') ORDER BY needed_by"))
    raid_movement = rows(db.execute(
        "SELECT * FROM raid WHERE movement IN ('new','up') ORDER BY raised_date DESC"))
    forecast = []
    if g:
        r = dash["next_gate_readiness"]
        if r["pct"] < 50:
            forecast.append(f"{g['id']} ({g['name']}) at {r['pct']}% evidence readiness - high risk of hold unless gaps close")
        elif r["pct"] < 85:
            forecast.append(f"{g['id']} ({g['name']}) at {r['pct']}% evidence readiness - on track with conditions")
        else:
            forecast.append(f"{g['id']} ({g['name']}) at {r['pct']}% evidence readiness - gate-ready")
    return {
        "generated": dash["today"],
        "next_gate": g,
        "readiness": dash["next_gate_readiness"],
        "attention": dash["attention"],
        "open_conditions": conditions,
        "open_decisions": decisions,
        "raid_movement": raid_movement,
        "forecast": forecast,
    }


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
            if path.startswith("/api/gates/"):
                gid = path.split("/")[-1]
                g = db.execute("SELECT * FROM gates WHERE id=?", (gid,)).fetchone()
                if not g:
                    return self._send(404, {"error": "gate not found"})
                out = dict(g)
                out["readiness"] = gate_readiness(db, gid)
                out["conditions"] = rows(db.execute(
                    "SELECT * FROM conditions WHERE gate_id=?", (gid,)))
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
                return self._send(200, rows(db.execute(
                    "SELECT * FROM kanban_columns ORDER BY position")))
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
                db.execute(
                    "UPDATE gates SET status=?, outcome=?, decided_date=? WHERE id=?",
                    (outcome, body.get("note", outcome.replace("_", " ")), today, gid))
                if outcome == "passed_with_conditions":
                    for c in body.get("conditions", []):
                        cid = f"COND-{db.execute('SELECT COUNT(*) c FROM conditions').fetchone()['c'] + 1:02d}"
                        db.execute(
                            "INSERT INTO conditions VALUES (?,?,?,?,?,?,?,?)",
                            (cid, gid, c["text"], c["owner"], c["due_date"], "open", today, None))
                db.commit()
                return self._send(200, {"ok": True, "gate_id": gid, "outcome": outcome})
            if path == "/api/conditions/update":
                db.execute("UPDATE conditions SET status=? WHERE id=?",
                           (body.get("status", "open"), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/decisions/update":
                db.execute(
                    "UPDATE decisions SET status=?, decision=?, decided_date=? WHERE id=?",
                    (body.get("status", "open"), body.get("decision"), date.today().isoformat(), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/deliverables/update":
                db.execute("UPDATE deliverables SET state=? WHERE id=?",
                           (body.get("state", "not_started"), body.get("id")))
                db.commit()
                return self._send(200, {"ok": True})
            if path == "/api/kanban/columns/add":
                label = (body.get("label") or "").strip()
                if not label:
                    return self._send(400, {"error": "label required"})
                cid = "col-" + label.lower().replace(" ", "_")[:24] + "-" + str(
                    db.execute("SELECT COUNT(*) c FROM kanban_columns").fetchone()["c"])
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
            return self._send(404, {"error": "not found"})
        finally:
            db.close()

    def _serve_static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        safe = os.path.normpath(path).lstrip("/")
        full = os.path.join(STATIC_DIR, safe)
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            return self._send(404, {"error": "not found"})
        ctype = {
            ".html": "text/html", ".js": "application/javascript",
            ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png",
        }.get(os.path.splitext(full)[1], "application/octet-stream")
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
