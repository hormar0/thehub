"""Import real program files (Deliverables Master xlsx, Decision Register xlsx) into the Hub DB.

Usage:  python3 import_files.py /path/to/upload/dir
Run once after first start (the DB is seeded on first run). Maps the real workbook
columns onto the Hub schema:
  Deliverables Master 'Milestones'  -> gates (M11, M12, ... M17 ... as real gate ids, with plan dates)
  Deliverables Master 'Deliverables'-> deliverables (ID, Milestone, Description, Status,
      Evidence, Responsible, Program/Project, Phase, planned dates)
  Decision Register 'Decisions'     -> decisions (ID, title, description, status incl.
      '03 Approved' -> decided, Responsible, target decision date, links)
"""
import os
import re
import sqlite3
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import parse_xlsx, get_db

EPOCH = date(1899, 12, 30)


def xl_date(v):
    """Excel serial date -> ISO date; pass through ISO strings."""
    if v in (None, "", "None"):
        return ""
    s = str(v).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    try:
        return (EPOCH + timedelta(days=float(s))).isoformat()
    except (ValueError, OverflowError):
        return ""


STATE_MAP = {
    "completed": "verified", "accepted": "verified",
    "in progress": "in_progress", "open": "in_progress",
    "not started": "not_started", "blocked": "blocked",
    "in review": "in_review",
}

DEC_STATUS_MAP = {
    "01 preparation": "open", "02 ready for appr": "open",
    "03 approved": "decided", "04 approved with conditions": "decided",
    "approved": "decided", "closed": "decided", "implemented": "decided",
}


def norm(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def colmap(header):
    return {norm(h): i for i, h in enumerate(header)}


def import_milestones_as_gates(db, rows):
    hdr_i = next(i for i, r in enumerate(rows) if any(norm(c) == "milestone" for c in r))
    cm = colmap(rows[hdr_i])
    n = 0
    for r in rows[hdr_i + 1:]:
        def g(*names):
            for name in names:
                if name in cm and cm[name] < len(r):
                    return str(r[cm[name]]).strip()
            return ""
        mid = g("milestone")
        if not mid or not re.match(r"^M\d+[a-z]?$", mid, re.I):
            continue
        gid = mid.upper()
        d = xl_date(g("date"))
        what = g("what_it_marks", "what")
        db.execute(
            "INSERT OR IGNORE INTO gates VALUES (?,?,?,?,?,?,?,?,?,?)",
            (gid, f"Milestone {gid}", "Milestone", d or date.today().isoformat(), "upcoming",
             "R. Castellanos", what, "Gate passes on assembled evidence", None, None))
        n += 1
    db.commit()
    return n


def import_deliverables(db, rows):
    hdr_i = next(i for i, r in enumerate(rows) if norm(r[0]) == "id")
    cm = colmap(rows[hdr_i])
    n = skipped = 0
    for r in rows[hdr_i + 1:]:
        def g(*names):
            for name in names:
                if name in cm and cm[name] < len(r):
                    return str(r[cm[name]]).strip()
            return ""
        did = g("id")
        desc = g("description")
        if not did and not desc:
            skipped += 1
            continue
        if not did:
            did = f"DEL-IMP-{n + skipped + 1:04d}"
        gate = g("milestone")
        gate_id = gate.upper() if gate and re.match(r"^M\d+", gate.upper()) else "E-030"
        if not db.execute("SELECT id FROM gates WHERE id=?", (gate_id,)).fetchone():
            gate_id = db.execute("SELECT id FROM gates ORDER BY scheduled_date LIMIT 1").fetchone()["id"]
        status = STATE_MAP.get(norm(g("status")), "not_started")
        review = norm(g("milestone_review_status"))
        if review == "1_accepted":
            status = "verified"
        elif review == "3_not_accepted":
            status = "blocked"
        elif review == "2_conditionally_accepted":
            status = "in_review"
        owner = g("responsible") or "unassigned"
        ev = g("evidence_in_place", "evidence_file", "evidence_folder")
        ev_ref = ("Y" if ev.upper() == "Y" else ev) if ev else ""
        proj_name = g("program_project", "program")
        proj_id = ""
        if proj_name and norm(proj_name) != "program":
            m = db.execute("SELECT id FROM projects WHERE name LIKE ?", (f"%{proj_name}%",)).fetchone()
            proj_id = m["id"] if m else ""
        due = xl_date(g("planned_end", "milestone_date")) or date.today().isoformat()
        existing = db.execute("SELECT id FROM deliverables WHERE id=?", (did,)).fetchone()
        if existing:
            db.execute("UPDATE deliverables SET title=?, description=?, owner=?, gate_id=?, state=?, due_date=?, evidence_ref=?, project_id=? WHERE id=?",
                       (desc[:200], desc, owner, gate_id, status, due, ev_ref, proj_id, did))
        else:
            db.execute("INSERT INTO deliverables VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (did, desc[:200], desc, "WS-CORE", owner, gate_id, status, due, None, None, ev_ref, "[]", "", "", proj_id))
        n += 1
    db.commit()
    return n, skipped


def import_decisions(db, rows):
    hdr_i = next(i for i, r in enumerate(rows) if norm(r[0]) == "id")
    cm = colmap(rows[hdr_i])
    n = skipped = 0
    for r in rows[hdr_i + 1:]:
        def g(*names):
            for name in names:
                if name in cm and cm[name] < len(r):
                    return str(r[cm[name]]).strip()
            return ""
        did = g("id")
        title = g("decisions")
        if not did and not title:
            skipped += 1
            continue
        if not did:
            did = f"DEC-IMP-{n + skipped + 1:04d}"
        raw_status = norm(g("status"))
        status = DEC_STATUS_MAP.get(raw_status, "open")
        if "approved" in raw_status:
            status = "decided"
        owner = g("responsible") or "unassigned"
        needed = xl_date(g("target_decision_date", "appr_date")) or date.today().isoformat()
        raised = xl_date(g("created_date", "decision_raised_date")) or date.today().isoformat()
        desc = g("description")[:1000]
        links = g("links")
        existing = db.execute("SELECT id FROM decisions WHERE id=?", (did,)).fetchone()
        if existing:
            db.execute("UPDATE decisions SET title=?, description=?, owner=?, needed_by=?, status=?, blocks=? WHERE id=?",
                       (title[:200], desc, owner, needed, status, links, did))
        else:
            db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (did, title[:200], desc, owner, raised, needed, status, links,
                        "Approved" if status == "decided" else None, needed if status == "decided" else None))
        n += 1
    db.commit()
    return n, skipped


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "/mnt/vibefs/uploads"
    db = get_db()
    for fn in sorted(os.listdir(folder)):
        path = os.path.join(folder, fn)
        low = fn.lower()
        if low.endswith(".xlsx") and "deliverables master" in low:
            sheets = parse_xlsx(open(path, "rb").read())
            g = import_milestones_as_gates(db, sheets["Milestones"])
            d = import_deliverables(db, sheets["Deliverables"])
            print(f"{fn}: milestone gates +{g}, deliverables +{d[0]} (skipped {d[1]})")
        elif low.endswith(".xlsx") and "decision" in low:
            sheets = parse_xlsx(open(path, "rb").read())
            d = import_decisions(db, sheets["Decisions"])
            print(f"{fn}: decisions +{d[0]} (skipped {d[1]})")
    db.close()
    print("done")


if __name__ == "__main__":
    main()
